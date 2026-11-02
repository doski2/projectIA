"""Mide cómo usa los pedales el teacher en una sesión de A2.0 (V65, V66): gas, frenadas, deceleración, frenar ya girando y uso del círculo de adherencia.

Qué mide por vuelta (los criterios de F1 y de la técnica de pedales están en `circuito_virtual/docs/TECNICA_CONDUCCION.md`):
- gas: inversiones con el coche girando y frenadas con rebote de gas en los 3 s previos;
- frenadas: tiempo sin gas ni freno antes de frenar, deceleración (mediana, p90, máx., % del tiempo con ≥ 10 m/s²), pedal máximo y dónde cae el máximo;
- giro al frenar: % de la energía de frenada con más de 4 m/s² laterales y uso del círculo (√(lat² + dec²) frente a 14,6 m/s², D21).
Con `--consigna REF` mide además, sin juego, el mayor salto de la consigna de velocidad del teacher a lo largo de la línea `REF`.

Las aceleraciones salen de `local_accel` con `session_log.tick_accels`, que sirve para cualquier log (en `log_schema` 1 y 2 el campo `lat_accel` era la longitudinal, V67).

Uso (con salida por tubería, anteponer PYTHONIOENCODING=utf-8):
    python experimental/common/pedales_sesion.py <log.jsonl> [--vueltas 2,3,4] [--eventos] [--consigna <linea.json>]  (con `circuito_virtual/pistas/<pista>/curvas.json` numera las curvas, V70)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "PCARS2-AI" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from session_log import tick_accels  # noqa: E402


def _catalogo(log: Path):
    """Catálogo numerado de curvas de la pista del log o None (V70)."""
    try:
        from circuito_virtual.src.curvas import catalogo_de_log  # noqa: PLC0415

        return catalogo_de_log(log)
    except Exception:  # sin catálogo la herramienta sale igual
        return None


CURVATURA_EN_CURVA = 0.006  # |guiñada| / v por encima de la cual se considera que el coche gira
UMBRAL_INVERSION = 0.12  # cambio de tendencia del gas que cuenta
LATERAL_GIRANDO = 4.0  # m/s² laterales a partir de los cuales se considera que se frena ya girando
CIRCULO_MS2 = 14.6  # cota lateral validada (D21), radio del círculo de referencia
HZ = 60


def cargar_ticks(log: Path) -> List[Dict[str, Any]]:
    out = []
    for linea in Path(log).read_text(encoding="utf-8").splitlines():
        d = json.loads(linea)
        if d.get("type") == "tick" and d["speed_kmh"] > 5:
            out.append(d)
    return out


def inversiones(gas: np.ndarray, en_curva: np.ndarray, umbral: float = UMBRAL_INVERSION) -> int:
    """Cambios de tendencia del gas de más de `umbral` mientras el coche gira."""
    cuenta, ext, d = 0, float(gas[0]), 0
    for i in range(1, len(gas)):
        if not en_curva[i]:
            ext, d = float(gas[i]), 0
            continue
        x = float(gas[i])
        if d >= 0 and x > ext:
            ext, d = x, (1 if d != -1 else d)
        elif d <= 0 and x < ext:
            ext, d = x, (-1 if d != 1 else d)
        if d == 1 and ext - x > umbral:
            cuenta, d, ext = cuenta + 1, -1, x
        elif d == -1 and x - ext > umbral:
            cuenta, d, ext = cuenta + 1, 1, x
    return cuenta


def frenadas(freno: np.ndarray) -> List[int]:
    """Índices donde empieza una frenada de verdad (pedal > 0,05 y máximo > 0,2 en el siguiente segundo y medio)."""
    return [i for i in range(1, len(freno)) if freno[i] > 0.05 and freno[i - 1] <= 0.05 and freno[i:i + int(1.5 * HZ)].max() > 0.2]


def tiene_rebote(gas: np.ndarray, i: int) -> bool:
    """True si en los 3 s previos a `i` el gas bajó más de 0,25 y volvió a subir más de 0,25."""
    w = gas[max(0, i - 3 * HZ):i + 1]
    return any(w[:a + 1].max() - w[a] > 0.25 and w[a:].max() - w[a] > 0.25 for a in range(len(w)))


def _suavizar(x: np.ndarray, n: int = 9) -> np.ndarray:
    return np.convolve(x, np.ones(n) / n, mode="same")


def _aceleraciones(ticks: Sequence[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray]:
    """(|lateral|, deceleración positiva al frenar) suavizadas, en m/s². Ceros si el log no trae `local_accel`."""
    pares = [tick_accels(t["vehicle"]) for t in ticks]
    if any(p is None for p in pares):
        z = np.zeros(len(ticks))
        return z, z
    lat = np.array([abs(p[0]) for p in pares if p is not None])
    dec = np.array([-p[1] for p in pares if p is not None])
    return _suavizar(lat), _suavizar(dec)


def analizar_vuelta(ticks: Sequence[Dict[str, Any]], cat=None) -> Dict[str, Any]:
    gas = np.array([t["throttle"] for t in ticks], float)
    freno = np.array([t["brake"] for t in ticks], float)
    v = np.array([t["speed_kmh"] for t in ticks], float) / 3.6
    k = np.array([abs(t["vehicle"]["yaw_rate"]) / max(t["speed_kmh"] / 3.6, 1.0) for t in ticks])
    lat, dec = _aceleraciones(ticks)
    inicios = frenadas(freno)
    previo = [float(gas[max(0, i - 6):i + 1].min()) for i in inicios]

    eventos: List[Dict[str, Any]] = []
    e_total = e_girando = 0.0
    for i in inicios:
        j = i
        while j < len(freno) and freno[j] > 0.03:
            j += 1
        seg = slice(i, j)
        e = v[i:j - 1] ** 2 - v[i + 1:j] ** 2
        girando = lat[i:j - 1] > LATERAL_GIRANDO
        e_total += float(e.sum())
        e_girando += float(e[girando].sum())
        m = i - 1
        while m > 0 and gas[m] <= 0.05 and freno[m] <= 0.05:
            m -= 1
        s_ini = float(ticks[i]["lap_distance"])
        curva = cat.proxima(s_ini) if cat is not None else None
        eventos.append({
            "curva": f"C{curva.id}" if curva is not None else "", "s": round(s_ini), "v0_kmh": round(float(v[i] * 3.6)), "v1_kmh": round(float(v[j - 1] * 3.6)), "dur_s": round((j - i) / HZ, 2),
            "pedal_max": round(float(freno[seg].max()), 2), "pico_en": round(float(np.argmax(freno[seg])) / max(j - i - 1, 1), 2),
            "lat_inicio": round(float(lat[i]), 1), "lat_max": round(float(lat[seg].max()), 1),
            "dec_media": round(float(dec[seg].mean()), 1), "dec_max": round(float(dec[seg].max()), 1),
            "pct_energia_girando": round(100.0 * float(e[girando].sum()) / float(e.sum()), 0) if e.sum() > 0 else 0.0,
            "muerto_s": round((i - 1 - m) / HZ, 2), "rebote": bool(tiene_rebote(gas, i)),
        })

    con_freno = freno > 0.1
    r: Dict[str, Any] = {
        "frenadas": len(inicios),
        "gas_a_0_al_frenar": sum(p <= 0.05 for p in previo),
        "con_rebote": sum(e["rebote"] for e in eventos),
        "inversiones": inversiones(gas, k > CURVATURA_EN_CURVA),
        "posiciones_rebote": [e["s"] for e in eventos if e["rebote"]],
        "eventos": eventos,
    }
    if eventos:
        r["muerto_medio_s"] = round(float(np.mean([e["muerto_s"] for e in eventos])), 2)
        r["muerto_max_s"] = round(float(np.max([e["muerto_s"] for e in eventos])), 2)
        r["pico_medio_en"] = round(float(np.mean([e["pico_en"] for e in eventos])), 2)
    if con_freno.any():
        d = dec[con_freno]
        comb = np.sqrt(lat[con_freno] ** 2 + d ** 2)
        r.update({
            "pedal_max": round(float(freno.max()), 2),
            "dec_mediana": round(float(np.median(d)), 1), "dec_p90": round(float(np.percentile(d, 90)), 1), "dec_max": round(float(d.max()), 1),
            "pct_tiempo_dec_10": round(100.0 * float((d >= 10.0).mean()), 0),
            "pct_energia_girando": round(100.0 * e_girando / e_total, 0) if e_total > 0 else 0.0,
            "circulo_mediana_pct": round(100.0 * float(np.median(comb)) / CIRCULO_MS2, 0), "circulo_p90_pct": round(100.0 * float(np.percentile(comb, 90)) / CIRCULO_MS2, 0),
            "segundos_de_freno": round(float(con_freno.sum()) / HZ, 1),
        })
    return r


def salto_consigna(referencia: Path, lat_accel_limit: float = 9.0, brake_decel_straight: float = 8.0, speed_target_kmh: float = 125.0,
                   perfil: bool = False, brake_circle: float = 14.6) -> Dict[str, Any]:
    """Mayor salto de la consigna de velocidad del teacher a lo largo de la línea, con el CTE en 0 y la deceleración que usa el teacher.

    Devuelve la mayor caída (km/h por metro), los puntos con caída > 2 km/h por metro y la **deceleración implícita** máxima de la consigna, (v² − v'²) / 2 por metro, en m/s²: la consigna de hoy
    da un salto porque la deceleración supuesta cambia de `brake_decel_straight` a `brake_decel` cuando |κ| pasa de 0,004; el perfil continuo de F1 (`perfil=True`) no pasa de `brake_decel_straight`."""
    from reference_recorder import ReferenceLine  # noqa: PLC0415
    from teacher_controller import STRAIGHT_BRAKE_KAPPA, TeacherConfig, TeachingController  # noqa: PLC0415

    ref = ReferenceLine.load(str(referencia))
    extra = {"pedal_technique": True, "brake_profile": True, "brake_circle": brake_circle} if perfil else {}
    tc = TeachingController(ref, TeacherConfig(speed_target_kmh=speed_target_kmh, lat_accel_limit=lat_accel_limit, brake_decel_straight=brake_decel_straight, brake_overspeed_straight_ms=2.5, **extra))
    n = int(ref.track_length)
    objetivo = np.empty(n)
    for s in range(n):
        if perfil:
            objetivo[s] = min(tc.speed_target_ms, tc.profile_at(float(s))) * 3.6
        else:
            recta = abs(ref.curvature(float(s))) < STRAIGHT_BRAKE_KAPPA
            objetivo[s] = min(tc.speed_target_ms, tc.physical_curve_target(float(s), brake_decel_straight if recta else None)) * 3.6
    siguiente = np.concatenate([objetivo[1:], objetivo[:1]])
    salto = siguiente - objetivo
    i = int(np.argmin(salto))  # la mayor caída
    implicita = (objetivo ** 2 - siguiente ** 2) / (2.0 * 3.6 ** 2)
    return {"max_caida_kmh_por_m": round(float(-salto[i]), 2), "en_m": i + 1, "de_kmh": round(float(objetivo[i]), 1), "a_kmh": round(float(siguiente[i]), 1),
            "puntos_con_caida_mayor_2": int((-salto > 2.0).sum()), "decel_implicita_max": round(float(implicita.max()), 1)}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("log", type=Path)
    ap.add_argument("--vueltas", default="2,3,4", help="vueltas a analizar, separadas por comas (la 1.ª incluye la salida parada)")
    ap.add_argument("--eventos", action="store_true", help="tabla de cada frenada")
    ap.add_argument("--consigna", type=Path, default=None, help="línea de referencia (JSON) para medir el salto de la consigna del teacher sin juego")
    ap.add_argument("--perfil", action="store_true", help="con --consigna: medir el perfil continuo de F1 (--brake-profile) en vez de la consigna de siempre")
    ap.add_argument("--brake-decel", type=float, default=8.0, help="con --consigna: --brake-decel-straight del teacher (m/s²)")
    ap.add_argument("--brake-circle", type=float, default=14.6, help="con --consigna --perfil: radio del círculo de adherencia (m/s²)")
    a = ap.parse_args(argv)
    ticks = cargar_ticks(a.log)
    cat = _catalogo(a.log)
    for lap in (int(x) for x in a.vueltas.split(",")):
        tk = [t for t in ticks if t["lap"] == lap]
        if len(tk) < 600:
            print(f"vuelta {lap}: sin datos suficientes")
            continue
        r = analizar_vuelta(tk, cat)
        print(f"vuelta {lap}: {r['frenadas']} frenadas | gas a 0 al frenar {r['gas_a_0_al_frenar']} | con rebote {r['con_rebote']} {r['posiciones_rebote']} | inversiones del gas en curva {r['inversiones']}")
        if "dec_mediana" in r:
            print(f"   freno: {r['segundos_de_freno']} s | pedal máx. {r['pedal_max']} | deceleración mediana {r['dec_mediana']}, p90 {r['dec_p90']}, máx. {r['dec_max']} m/s² | con ≥ 10 m/s² el {r['pct_tiempo_dec_10']:.0f} % del tiempo")
            print(f"   tiempo muerto antes de frenar: media {r['muerto_medio_s']} s, máx. {r['muerto_max_s']} s | máximo del pedal al {r['pico_medio_en']:.0%} de la frenada")
            print(f"   frenando ya girando (> {LATERAL_GIRANDO:g} m/s² laterales): {r['pct_energia_girando']:.0f} % de la energía de frenada | círculo (√(lat²+dec²) / {CIRCULO_MS2}): mediana {r['circulo_mediana_pct']:.0f} %, p90 {r['circulo_p90_pct']:.0f} %")
        if a.eventos:
            print("  curva     s   v0   v1  dur  pedal pico  lat0 latmáx decmed decmáx %girando muerto rebote")
            for e in r["eventos"]:
                print(f"   {e['curva']:>4s} {e['s']:5d} {e['v0_kmh']:4d} {e['v1_kmh']:4d} {e['dur_s']:4.1f}  {e['pedal_max']:.2f} {e['pico_en']:.2f} {e['lat_inicio']:5.1f} {e['lat_max']:5.1f} {e['dec_media']:5.1f} {e['dec_max']:5.1f}  {e['pct_energia_girando']:5.0f}%  {e['muerto_s']:.2f}  {'sí' if e['rebote'] else ''}")
    if a.consigna:
        s = salto_consigna(a.consigna, brake_decel_straight=a.brake_decel, perfil=a.perfil, brake_circle=a.brake_circle)
        modo = f"perfil continuo (círculo {a.brake_circle:g})" if a.perfil else "consigna de siempre"
        print(f"{modo} en {a.consigna.name}: mayor caída {s['max_caida_kmh_por_m']} km/h por metro en {s['en_m']} m ({s['de_kmh']} → {s['a_kmh']} km/h); puntos con caída > 2 km/h/m: {s['puntos_con_caida_mayor_2']}; deceleración implícita máx. {s['decel_implicita_max']} m/s²")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
