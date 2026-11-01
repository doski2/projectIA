"""A2 con la IA a ritmo real (`circuito_virtual/docs/PLAN.md`, V11): ajustar el solver con 10 de las 14 vueltas y predecir las otras 4.

De `pistas/sugo_gp/ia_ritmo_real.json` (vueltas de 97,7-98,3 s, hasta 184 km/h) se saca:

- **la línea:** mediana de x, z, y por metro de las vueltas de ajuste → `Track` (curvatura y pendiente);
- **la aceleración longitudinal** a_acel(v): percentil alto de la aceleración llana en recta (|a_lat| < 2 m/s²) y sin freno, por tramos de velocidad, sin dejar que crezca con la velocidad;
- **la frenada** a_freno(v): percentil de la deceleración llana con el freno pisado a fondo (pedal ≥ 100 de 255);
- **el límite lateral** `μ + k·v²`: mínimos cuadrados sobre el percentil 99 de |a_lat| en curva, por tramos de velocidad (solo donde hay curvas a esa velocidad).

El gas de la IA vale 255 siempre, así que no se puede saber cuándo iba a fondo: lo que sale es **lo que hace la IA, no lo que puede el coche**. Predecir sus vueltas valida el
solver (mecánica, pendiente, curvatura, frenada anticipada), no los límites del coche: el coche de A1 aguanta bastante más que la IA (14,6 frente a ≈ 9,5 m/s² laterales a 85 km/h).

Uso:
    python circuito_virtual/src/ajuste_ia.py [--json salida.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "PCARS2-AI" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from circuito_virtual.src import perfil_velocidad as pv  # noqa: E402

IA = REPO / "circuito_virtual" / "pistas" / "sugo_gp" / "ia_ritmo_real.json"
G = pv.G
BIN_KMH = 15.0
MIN_PUNTOS = 30
P_ACEL = 90.0
P_FRENO = 90.0
P_LAT = 99.0
FRENO_FONDO = 100  # pedal (0-255) a partir del cual se toma como frenada fuerte
LAT_RECTA = 2.0  # |a_lat| máximo para medir aceleración y frenada sin curva
LAT_CURVA = 4.0  # |a_lat| mínimo para contar como curva
V_MAX_AJUSTE_LAT_KMH = 140.0  # por encima no hay curvas a esa velocidad en Sugo: el percentil no es un límite


def cargar(ruta: Path = IA) -> List[Dict[str, np.ndarray]]:
    """Cada vuelta remuestreada a un punto por metro (0..N-1), con la aceleración lateral real |v · guiñada| (`a_lat`) y la longitudinal de la derivada de la velocidad (`a_long`, + = acelera).

    Las `lacc` del archivo de la IA no están en m/s² (valen ≈ 0,46 de v · guiñada, V12), por eso no se usan."""
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    n = int(round(datos["longitud_m"])) - 1
    rejilla = np.arange(n, dtype=float)
    vueltas = []
    for v in datos["vueltas"]:
        d = np.array(v["d"], dtype=float)
        vuelta = {"tiempo_s": float(v["tiempo_s"]), "vuelta": int(v["vuelta"]),
                  **{k: np.interp(rejilla, d, np.array(v[k], dtype=float)) for k in ("x", "y", "z", "v_ms", "freno", "marcha", "yaw")}}
        vuelta["a_lat"] = np.abs(vuelta["v_ms"] * vuelta["yaw"])
        suave = np.convolve(np.concatenate([vuelta["v_ms"][-3:], vuelta["v_ms"], vuelta["v_ms"][:3]]), np.ones(7) / 7, mode="valid")
        vuelta["a_long"] = suave * np.gradient(suave)  # dv/dt = v · dv/ds con 1 m entre puntos
        vueltas.append(vuelta)
    return vueltas


def linea_mediana(vueltas: Sequence[Dict[str, np.ndarray]], longitud_m: float) -> pv.Track:
    x = np.median([v["x"] for v in vueltas], axis=0)
    z = np.median([v["z"] for v in vueltas], axis=0)
    y = np.median([v["y"] for v in vueltas], axis=0)
    return pv.Track.from_arrays(x, z, y, longitud_m)


def _pendiente(v: Dict[str, np.ndarray]) -> np.ndarray:
    h = np.hypot(np.gradient(v["x"]), np.gradient(v["z"]))
    return np.gradient(v["y"]) / np.maximum(h, 1e-6)


def _junta(vueltas: Sequence[Dict[str, np.ndarray]]) -> Dict[str, np.ndarray]:
    return {"v": np.concatenate([v["v_ms"] * 3.6 for v in vueltas]), "freno": np.concatenate([v["freno"] for v in vueltas]),
            "alat": np.concatenate([np.abs(v["a_lat"]) for v in vueltas]),
            "a_acel": np.concatenate([v["a_long"] + G * _pendiente(v) for v in vueltas]),  # a_llano = a_medida + g · pendiente (como A1)
            "a_freno": np.concatenate([-v["a_long"] - G * _pendiente(v) for v in vueltas])}


def ajustar(vueltas: Sequence[Dict[str, np.ndarray]], p_acel: float = P_ACEL, p_freno: float = P_FRENO, p_lat: float = P_LAT) -> pv.CarParams:
    d = _junta(vueltas)
    v, borde = d["v"], np.arange(60.0, 200.0, BIN_KMH)
    acel, freno, lat = [], [], []
    for lo in borde:
        m = (v >= lo) & (v < lo + BIN_KMH)
        centro = lo + BIN_KMH / 2
        a = m & (d["freno"] == 0) & (d["alat"] < LAT_RECTA) & (d["a_acel"] > -1.0)
        if a.sum() >= MIN_PUNTOS:
            acel.append((centro, float(np.percentile(d["a_acel"][a], p_acel))))
        f = m & (d["freno"] >= FRENO_FONDO) & (d["alat"] < 3.0)
        if f.sum() >= MIN_PUNTOS:
            freno.append((centro, float(np.percentile(d["a_freno"][f], p_freno))))
        c = m & (d["alat"] > LAT_CURVA)
        if c.sum() >= MIN_PUNTOS and centro <= V_MAX_AJUSTE_LAT_KMH:
            lat.append((centro / 3.6, float(np.percentile(d["alat"][c], p_lat))))
    if len(acel) < 3 or len(freno) < 2 or len(lat) < 1:
        raise ValueError("faltan datos para ajustar (aceleración, frenada o curvas)")
    # la capacidad de acelerar no crece con la velocidad: mínimo acumulado de baja a alta
    acel = [(vc, float(m)) for (vc, _), m in zip(acel, np.minimum.accumulate([a for _, a in acel]))]
    vs = np.array([x for x, _ in lat])
    if len(lat) == 1:  # una sola velocidad de curva: no se puede separar μ de k, todo a μ
        k, mu = 0.0, lat[0][1]
    else:
        k, mu = np.polyfit(vs ** 2, np.array([y for _, y in lat]), 1)
    return pv.CarParams(acel, freno, mu=float(mu), k=float(max(k, 0.0)), v_known_kmh=float(max(c for c, _ in acel) + BIN_KMH / 2))


def escalar(coche: pv.CarParams, f: float) -> pv.CarParams:
    """Mismo coche con aceleración, frenada y límite lateral multiplicados por `f` (el ritmo de la IA como fracción de su envolvente)."""
    return pv.CarParams([(v, a * f) for v, a in coche.accel], [(v, a * f) for v, a in coche.brake], coche.mu * f, coche.k * f,
                        coche.v_known_kmh, coche.brake_delay_s)


def calibrar_ritmo(coche: pv.CarParams, track: pv.Track, tiempo_objetivo_s: float, lo: float = 0.4, hi: float = 1.3) -> float:
    """`f` tal que la vuelta predicha dura `tiempo_objetivo_s` (bisección: más `f`, vuelta más corta)."""
    for _ in range(40):
        mid = (lo + hi) / 2
        if pv.solve(track, escalar(coche, mid)).time_s > tiempo_objetivo_s:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def predecir(coche: pv.CarParams, track: pv.Track, vueltas: Sequence[Dict[str, np.ndarray]]) -> Dict:
    """Perfil de velocidad del solver y comparación con cada vuelta real: error de tiempo, correlación y error cuadrático medio de v(s)."""
    prof = pv.solve(track, coche)
    n = min(len(prof.v_ms), len(vueltas[0]["v_ms"]))
    resultados = []
    for v in vueltas:
        real = v["v_ms"][:n] * 3.6
        pred = prof.v_ms[:n] * 3.6
        resultados.append({"vuelta": v["vuelta"], "tiempo_real_s": v["tiempo_s"], "tiempo_pred_s": prof.time_s,
                           "error_tiempo_pct": 100 * (prof.time_s - v["tiempo_s"]) / v["tiempo_s"],
                           "correlacion_v": float(np.corrcoef(real, pred)[0, 1]), "rms_v_kmh": float(np.sqrt(np.mean((real - pred) ** 2))),
                           "sesgo_v_kmh": float(np.mean(pred - real))})
    return {"perfil": prof, "vueltas": resultados}


def analizar(ruta: Path = IA, n_ajuste: int = 10) -> Dict:
    vueltas = cargar(ruta)
    longitud = float(json.loads(Path(ruta).read_text(encoding="utf-8"))["longitud_m"])
    ajuste, prueba = vueltas[:n_ajuste], vueltas[n_ajuste:]
    track = linea_mediana(ajuste, longitud)
    coche = ajustar(ajuste)
    res_prueba = predecir(coche, track, prueba)
    res_ajuste = predecir(coche, track, ajuste)
    prof = res_prueba["perfil"]
    # el ritmo de la IA como fracción de su envolvente: un solo factor ajustado al tiempo de las vueltas de ajuste, probado en las demás
    f = calibrar_ritmo(coche, track, float(np.mean([v["tiempo_s"] for v in ajuste])))
    cal = predecir(escalar(coche, f), track, prueba)
    return {"coche": coche.to_dict(), "n_ajuste": len(ajuste), "n_prueba": len(prueba),
            "vuelta_predicha_s": prof.time_s, "ajuste": res_ajuste["vueltas"], "prueba": res_prueba["vueltas"],
            "factor_ritmo": f, "calibrado": {"vuelta_predicha_s": cal["perfil"].time_s, "prueba": cal["vueltas"]},
            "reparto": {"en_el_tope": prof.share_at_cap, "limite_lateral": prof.share_lateral, "frenando": prof.share_braking, "acelerando": prof.share_accel}}


def _resumen(r: Dict) -> None:
    c = r["coche"]
    print("Parámetros ajustados a la IA (%d vueltas):" % r["n_ajuste"])
    print("  aceleración (km/h→m/s²):", ", ".join(f"{v:g}→{a:.2f}" for v, a in c["accel"]))
    print("  frenada     (km/h→m/s²):", ", ".join(f"{v:g}→{a:.2f}" for v, a in c["brake"]))
    print(f"  lateral: μ = {c['mu']:.2f} m/s², k = {c['k']:.5f} 1/m  (a 85 km/h: {c['mu'] + c['k'] * (85 / 3.6) ** 2:.1f}; a 130 km/h: {c['mu'] + c['k'] * (130 / 3.6) ** 2:.1f})")
    for nombre in ("ajuste", "prueba"):
        filas = r[nombre]
        print(f"\nVueltas de {nombre} ({len(filas)}): tiempo real {np.mean([f['tiempo_real_s'] for f in filas]):.2f} s, predicho {r['vuelta_predicha_s']:.2f} s")
        print(f"  error de tiempo {np.mean([f['error_tiempo_pct'] for f in filas]):+.1f} %, correlación de v(s) {np.mean([f['correlacion_v'] for f in filas]):.3f}, "
              f"error cuadrático de v {np.mean([f['rms_v_kmh'] for f in filas]):.1f} km/h, sesgo {np.mean([f['sesgo_v_kmh'] for f in filas]):+.1f} km/h")
    cal = r["calibrado"]
    print(f"\nCalibrando un solo factor de ritmo f = {r['factor_ritmo']:.3f} (aceleración, frenada y lateral × f) con las vueltas de ajuste:")
    filas = cal["prueba"]
    print(f"  vueltas de prueba: tiempo real {np.mean([x['tiempo_real_s'] for x in filas]):.2f} s, predicho {cal['vuelta_predicha_s']:.2f} s, error {np.mean([x['error_tiempo_pct'] for x in filas]):+.1f} %, "
          f"correlación de v(s) {np.mean([x['correlacion_v'] for x in filas]):.3f}, error cuadrático de v {np.mean([x['rms_v_kmh'] for x in filas]):.1f} km/h, sesgo {np.mean([x['sesgo_v_kmh'] for x in filas]):+.1f} km/h")
    rp = r["reparto"]
    print(f"\nReparto de la vuelta predicha: {100 * rp['en_el_tope']:.0f} % en el tope, {100 * rp['limite_lateral']:.0f} % en el límite lateral, "
          f"{100 * rp['frenando']:.0f} % frenando, {100 * rp['acelerando']:.0f} % acelerando")


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--vueltas-ajuste", type=int, default=10)
    args = ap.parse_args(argv)
    r = analizar(n_ajuste=args.vueltas_ajuste)
    _resumen(r)
    if args.json:
        args.json.write_text(json.dumps(r, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
