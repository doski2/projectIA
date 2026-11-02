"""Resumen de una sesión de A2.0 del teacher en un solo comando (V34): lo que hasta ahora se miraba con varios scripts sueltos.

Imprime, de un log de `PCARS2-AI/logs/learning/`:

1. **Vueltas:** tiempo de cada una (la 1.ª lleva la salida parada) y, si se da `--previsto`, el error frente al solver.
2. **Criterio de volante de V19** (`analisis_volante.py`): rectas y curvas contra los límites, con OK / NO por línea. Es el criterio para subir de banda: 2 vueltas seguidas.
3. **Tramos fuera de criterio** (|CTE| > `CTE_ALTO_M` o deriva > `DERIVA_ALTA_DEG`), agrupados, con velocidad, marcha y aceleración lateral.
4. **Frenos:** pedal máximo y p99, y deceleración en recta con gas a 0 según el pedal (la frenada fuerte de V31-V32 satura hacia 11,6 m/s²); razón de giro traseras/delanteras
   (un bloqueo la llevaría hacia 0) y si el indicador ABS llegó a encenderse.
5. **Cambios de marcha:** número, tiempo en punto muerto y velocidad perdida, subidas y bajadas por separado (V30).
6. **Terreno:** ticks con alguna rueda fuera de la superficie de carrera.

Uso:
    python experimental/common/resumen_sesion.py PCARS2-AI/logs/learning/<ts>_sugo_gp_l1_linea.jsonl [--previsto 117.6] [--vueltas 2]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "PCARS2-AI" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from experimental.common import analisis_volante as av  # noqa: E402

# Criterio provisional de V19: (ámbito, métrica, límite). Todas son «como máximo».
CRITERIO_V19: Tuple[Tuple[str, str, float], ...] = (
    ("rectas", "volante_rms", 0.04), ("rectas", "inversiones_100m", 1.0), ("rectas", "cte_rms", 0.25),
    ("curvas", "tasa", 0.2), ("curvas", "cte_max", 1.8), ("curvas", "deriva_max", 4.0),
)
CTE_ALTO_M = 1.8
DERIVA_ALTA_DEG = 4.0
G = 9.81


def evaluar(res: Dict) -> List[Tuple[str, str, Optional[float], float, bool]]:
    """(ámbito, métrica, valor, límite, cumple) por cada línea del criterio; sin datos de un ámbito → valor None y no cumple."""
    filas = []
    for ambito, metrica, limite in CRITERIO_V19:
        bloque = res.get(ambito)
        valor = None if not bloque else float(bloque[metrica])
        filas.append((ambito, metrica, valor, limite, valor is not None and valor <= limite))
    return filas


def cargar_ticks(ruta: Path) -> List[dict]:
    with open(ruta, encoding="utf-8") as fh:
        return [t for t in (json.loads(l) for l in fh if '"type": "tick"' in l)]


def vueltas(ticks: Sequence[dict], minimo_m: float = 3400.0) -> List[Dict]:
    """Tiempo (reloj del juego) y extremos de cada vuelta completa (la que cubre al menos `minimo_m` metros)."""
    out = []
    for lap in sorted({t["lap"] for t in ticks}):
        tk = [t for t in ticks if t["lap"] == lap]
        d = np.array([t["lap_distance"] for t in tk])
        if len(tk) < 100 or np.sum(np.clip(np.diff(d), 0, 50)) < minimo_m:
            continue
        cte = np.array([abs(t["signed_cte"]) for t in tk])
        lv = [t["vehicle"]["local_velocity"] for t in tk]
        beta = np.array([abs(np.degrees(np.arctan2(v[0], -v[2]))) if -v[2] > 5 else 0.0 for v in lv])
        lat = np.array([abs(t["vehicle"]["local_accel"][0]) for t in tk])
        out.append({"vuelta": int(lap), "tiempo_s": float((tk[-1].get("timing") or {}).get("game_time_s", tk[-1]["t_s"] - tk[0]["t_s"])),
                    "cte_max": float(cte.max()), "deriva_max": float(beta.max()), "lateral_max": float(lat.max()),
                    "v_media_kmh": float(np.mean([t["speed_kmh"] for t in tk]))})
    return out


def tramos_fuera(ticks: Sequence[dict], vueltas_validas: Sequence[int]) -> List[Dict]:
    """Tramos de las vueltas dadas con |CTE| o deriva por encima de los límites, agrupados cuando están a menos de 25 m."""
    tk = [t for t in ticks if t["lap"] in vueltas_validas]
    if not tk:
        return []
    d = np.array([t["lap_distance"] for t in tk]); cte = np.array([abs(t["signed_cte"]) for t in tk])
    v = np.array([t["speed_kmh"] for t in tk]); g = np.array([t["gear"] for t in tk]); lap = np.array([t["lap"] for t in tk])
    beta = np.array([abs(np.degrees(np.arctan2(t["vehicle"]["local_velocity"][0], -t["vehicle"]["local_velocity"][2]))) if -t["vehicle"]["local_velocity"][2] > 5 else 0.0 for t in tk])
    lat = np.array([abs(t["vehicle"]["local_accel"][0]) for t in tk])
    malo = (cte > CTE_ALTO_M) | (beta > DERIVA_ALTA_DEG)
    out = []
    for lp in vueltas_validas:
        idx = np.flatnonzero(malo & (lap == lp))
        if not len(idx):
            continue
        for gr in np.split(idx, np.flatnonzero(np.diff(d[idx]) > 25) + 1):
            out.append({"vuelta": int(lp), "d0": float(d[gr[0]]), "d1": float(d[gr[-1]]), "cte_max": float(cte[gr].max()), "deriva_max": float(beta[gr].max()),
                        "v_kmh": float(v[gr].mean()), "marcha": sorted({int(x) for x in g[gr]}), "lateral_max": float(lat[gr].max())})
    return out


def frenos(ticks: Sequence[dict], vueltas_validas: Sequence[int]) -> Dict:
    """Pedal, deceleración en recta según el pedal y giro de las ruedas traseras frente a las delanteras al frenar."""
    tk = [t for t in ticks if t["lap"] in vueltas_validas]
    if len(tk) < 50:
        return {}
    t_ = np.array([t["t_s"] for t in tk]); v = np.array([t["speed_kmh"] for t in tk]) / 3.6
    brk = np.array([t["brake"] for t in tk]); thr = np.array([t["throttle"] for t in tk]); g = np.array([t["gear"] for t in tk])
    yaw = np.array([t["vehicle"]["yaw_rate"] for t in tk])
    rps = np.array([[abs(x) for x in t["vehicle"]["tyre_rps"]] for t in tk])
    ratio = rps[:, 2:].mean(axis=1) / np.maximum(rps[:, :2].mean(axis=1), 1e-6)
    abs_on = np.array([(t["vehicle"].get("car_flags", 0) >> 4) & 1 for t in tk])
    n = len(tk)
    a = np.full(n, np.nan)
    h = 8
    for i in range(h, n - h):
        a[i] = (v[i + h] - v[i - h]) / max(t_[i + h] - t_[i - h], 1e-6)
    recta = (v > 15) & (np.abs(yaw * v) < 3.0) & (thr == 0) & (g != 0)
    tabla = []
    for lo, hi in ((0.02, 0.2), (0.2, 0.4), (0.4, 0.55), (0.55, 0.7), (0.7, 1.01)):
        m = recta & (brk >= lo) & (brk < hi) & ~np.isnan(a)
        if m.sum() >= 8:
            tabla.append({"pedal": (lo, hi), "n": int(m.sum()), "decel_media": float(-np.nanmean(a[m])), "decel_max": float(-np.nanmin(a[m])),
                          "v_kmh": float(np.mean(v[m]) * 3.6), "razon_min": float(ratio[m].min())})
    fuerte = (brk > 0.05) & recta
    return {"pedal_max": float(brk.max()), "pedal_p99": float(np.percentile(brk, 99)), "ticks_con_freno": int((brk > 0.05).sum()), "tabla": tabla,
            "razon_min_con_freno": float(ratio[fuerte].min()) if fuerte.any() else None, "abs_ticks": int(abs_on.sum())}


def cambios(ticks: Sequence[dict], vueltas_validas: Sequence[int], v_min_kmh: float = 40.0) -> Dict:
    """Episodios de punto muerto (cambios de marcha) tras el arranque: duración, velocidad perdida, subidas y bajadas por separado."""
    tk = [t for t in ticks if t["lap"] in vueltas_validas and t["t_s"] > 6.0]
    if len(tk) < 20:
        return {}
    t_ = np.array([t["t_s"] for t in tk]); v = np.array([t["speed_kmh"] for t in tk]); g = np.array([t["gear"] for t in tk])
    idx = np.flatnonzero((g == 0) & (v > v_min_kmh))
    out: Dict[str, List[Tuple[float, float]]] = {"sube": [], "baja": []}
    if len(idx):
        for ep in np.split(idx, np.flatnonzero(np.diff(idx) > 3) + 1):
            i0, i1 = ep[0], ep[-1]
            if i0 < 2 or i1 + 3 >= len(tk):
                continue
            antes, despues = g[i0 - 1], g[min(i1 + 3, len(tk) - 1)]
            if antes == despues or antes == 0 or despues == 0:
                continue
            out["sube" if despues > antes else "baja"].append((float(t_[i1] - t_[i0] + 1 / 60), float(v[i1 + 1] - v[i0 - 1])))
    res = {}
    for tipo, filas in out.items():
        if filas:
            a = np.array(filas)
            res[tipo] = {"n": len(filas), "neutro_s": float(a[:, 0].mean()), "dv_kmh": float(a[:, 1].mean())}
    return res


def terreno(ticks: Sequence[dict]) -> Dict:
    from pcars2_surface import RACING_TERRAIN_IDS  # noqa: PLC0415

    terr = np.array([t["vehicle"]["terrain"] for t in ticks if t["vehicle"].get("terrain")])
    if not len(terr):
        return {}
    fuera = ~np.isin(terr, list(RACING_TERRAIN_IDS))
    return {"ticks": int(len(terr)), "alguna_rueda_fuera": int(fuera.any(axis=1).sum()), "dos_o_mas": int((fuera.sum(axis=1) >= 2).sum())}


def evaluar_parejas(ruta: Path, vs: Sequence[Dict]) -> List[Dict]:
    """Criterio de volante (V19) de cada pareja de vueltas completas **seguidas**: «2 vueltas completas seguidas» es lo que pide el criterio, así que una sola vuelta mala no invalida las demás parejas.

    Escribe en un archivo temporal la cabecera y los ticks de las dos vueltas y le pasa `analisis_volante.analizar`."""
    import tempfile  # noqa: PLC0415

    with open(ruta, encoding="utf-8") as fh:
        lineas = fh.readlines()
    cabecera = next((l for l in lineas if '"type": "session"' in l), "")
    por_vuelta: Dict[int, List[str]] = {}
    for l in lineas:
        if '"type": "tick"' in l:
            por_vuelta.setdefault(int(json.loads(l)["lap"]), []).append(l)
    out = []
    for a, b in zip(vs, vs[1:]):
        if b["vuelta"] != a["vuelta"] + 1:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            sub = Path(tmp) / "pareja.jsonl"
            sub.write_text(cabecera + "".join(por_vuelta.get(a["vuelta"], []) + por_vuelta.get(b["vuelta"], [])), encoding="utf-8")
            res = av.analizar(sub)
        filas = evaluar(res)
        out.append({"vueltas": (a["vuelta"], b["vuelta"]), "cumple": all(f[4] for f in filas), "fallan": [f"{f[0]} {f[1]} {f[2]:.3f} > {f[3]:g}" for f in filas if not f[4] and f[2] is not None]})
    return out


def resumen(ruta: Path, previsto_s: Optional[float] = None, n_vueltas: int = 2) -> Dict:
    ticks = cargar_ticks(ruta)
    vs = vueltas(ticks)
    validas = [v["vuelta"] for v in vs][:n_vueltas]
    # los tramos fuera de criterio se listan de **todas** las vueltas completas: el criterio de volante (`av.analizar`) también las cuenta todas y un desvío de la 4.ª vuelta no debe quedar sin localizar
    return {"ruta": str(ruta), "vueltas": vs, "previsto_s": previsto_s, "volante": av.analizar(ruta), "tramos": tramos_fuera(ticks, [v["vuelta"] for v in vs]), "parejas": evaluar_parejas(ruta, vs),
            "frenos": frenos(ticks, validas), "cambios": cambios(ticks, validas), "terreno": terreno(ticks)}


def _catalogo(ruta: Path):
    """Catálogo numerado de curvas de la pista del log (`circuito_virtual/pistas/<pista>/curvas.json`) o None."""
    try:
        import sys  # noqa: PLC0415

        repo = Path(__file__).resolve().parents[2]
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        from circuito_virtual.src.curvas import catalogo_de_log  # noqa: PLC0415

        return catalogo_de_log(ruta)
    except Exception:  # sin catálogo el resumen sale igual
        return None


def _imprimir(r: Dict) -> None:
    print(f"{Path(r['ruta']).name}")
    print("\nVueltas (la 1.ª incluye la salida parada):")
    for v in r["vueltas"]:
        print(f"  vuelta {v['vuelta']}: {v['tiempo_s']:6.1f} s  v media {v['v_media_kmh']:5.1f} km/h  |CTE| máx. {v['cte_max']:.2f} m  deriva máx. {v['deriva_max']:.1f}°  lateral máx. {v['lateral_max']:.1f} m/s²")
    if r["previsto_s"] and len(r["vueltas"]) > 1:
        t = r["vueltas"][1]["tiempo_s"]
        print(f"  vuelta lanzada {t:.1f} s frente a {r['previsto_s']:.1f} s previstos: {100 * (t / r['previsto_s'] - 1):+.1f} %")
    print("\nCriterio de volante (V19; dos vueltas seguidas):")
    ok = True
    for ambito, metrica, valor, limite, cumple in evaluar(r["volante"]):
        ok &= cumple
        txt = "sin datos" if valor is None else f"{valor:.3f}"
        print(f"  {'OK' if cumple else 'NO'}  {ambito:<6} {metrica:<17} {txt:>9}  (≤ {limite:g})")
    print(f"  => {'CUMPLE: se puede subir de banda' if ok else 'NO CUMPLE'}")
    if r.get("parejas"):
        print("  Por parejas de vueltas seguidas (el criterio pide dos seguidas):")
        for q in r["parejas"]:
            print(f"    vueltas {q['vueltas'][0]}-{q['vueltas'][1]}: {'CUMPLE' if q['cumple'] else 'no cumple (' + '; '.join(q['fallan']) + ')'}")
    if r["tramos"]:
        print(f"\nTramos con |CTE| > {CTE_ALTO_M:g} m o deriva > {DERIVA_ALTA_DEG:g}°:")
        cat = _catalogo(Path(r["ruta"]))
        for t in r["tramos"]:
            curva = f"  [{cat.etiqueta_tramo(t['d0'], t['d1'])}]" if cat else ""
            print(f"  vuelta {t['vuelta']}: {t['d0']:5.0f}-{t['d1']:5.0f} m{curva}  |CTE| {t['cte_max']:.2f}  deriva {t['deriva_max']:.1f}°  {t['v_kmh']:.0f} km/h  marcha {t['marcha']}  lateral {t['lateral_max']:.1f}")
    f = r["frenos"]
    if f:
        print(f"\nFrenos: pedal máx. {f['pedal_max']:.2f}, p99 {f['pedal_p99']:.2f}, {f['ticks_con_freno']} ticks con freno; ABS encendido en {f['abs_ticks']} ticks; "
              f"razón traseras/delanteras con freno en recta: mín. {f['razon_min_con_freno'] if f['razon_min_con_freno'] is None else round(f['razon_min_con_freno'], 2)}")
        for b in f["tabla"]:
            print(f"  pedal {b['pedal'][0]:.2f}-{min(b['pedal'][1], 1.0):.2f}: n {b['n']:4d}  deceleración {b['decel_media']:5.2f} (máx. {b['decel_max']:5.2f}) m/s² a {b['v_kmh']:.0f} km/h  razón mín. {b['razon_min']:.2f}")
    c = r["cambios"]
    if c:
        print("\nCambios de marcha:")
        for tipo, d in c.items():
            print(f"  {tipo}: {d['n']} cambios, {d['neutro_s']:.2f} s en punto muerto, {d['dv_kmh']:+.1f} km/h durante el cambio")
    t = r["terreno"]
    if t:
        print(f"\nTerreno: {t['alguna_rueda_fuera']} de {t['ticks']} ticks con alguna rueda fuera de la superficie de carrera ({t['dos_o_mas']} con dos o más)")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("log", type=Path)
    ap.add_argument("--previsto", type=float, default=None, help="vuelta prevista por el solver (s) para comparar con la 2.ª")
    ap.add_argument("--vueltas", type=int, default=2, help="vueltas completas que entran en el criterio (por defecto 2)")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    r = resumen(a.log, a.previsto, a.vueltas)
    _imprimir(r)
    if a.json:
        a.json.write_text(json.dumps(r, ensure_ascii=False, indent=1, default=float), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
