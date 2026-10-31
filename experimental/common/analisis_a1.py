"""Análisis de las sesiones de identificación A1 (maniobras `ident:acel` e `ident:rodar` de `learn_driver --ident`).

Las frenadas (`ident:frenar`, A1.2) se resumen además por evento: velocidad de entrada y de salida, distancia, tiempo y
deceleración media y máxima; un cambio de marcha a mitad de frenada no parte el evento.

De cada pasada saca la aceleración longitudinal como derivada de la velocidad (regresión lineal en una ventana de ~0,5 s sobre el
reloj del PC, que va a 60 Hz) y la agrupa por marcha y tramo de velocidad. `acel` da `a_acel(v, marcha)`; `rodar` da la
desaceleración por resistencia al avance (con el freno motor de la marcha engranada). El eje 2 de `local_accel` se imprime solo
como contraste: su correlación con la derivada no es limpia (H1) y no se usa.

Uso:
    python experimental/common/analisis_a1.py experimental/../PCARS2-AI/logs/learning/<ts>_sugo_gp_l1_linea.jsonl [--json salida.json]
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

KINDS = ("ident:acel", "ident:rodar", "ident:frenar")
SHIFT = "ident:cambio"  # ticks de un cambio de marcha dentro de una maniobra
WINDOW_S = 0.25  # semiancho de la ventana de la derivada
TRIM_S = 0.5  # se descarta el principio de cada pasada: el pedal y el motor aún no han respondido
BIN_KMH = 10


def load_ticks(path: Path) -> List[dict]:
    with open(path, encoding="utf-8") as fh:
        return [r for r in map(json.loads, fh) if r.get("type") == "tick"]


def split_passes(ticks: List[dict]) -> List[List[dict]]:
    """Tramos consecutivos de ticks con la misma maniobra de identificación."""
    passes: List[List[dict]] = []
    cur: List[dict] = []
    for t in ticks:
        src = t.get("drive_source")
        if src in KINDS and cur and cur[-1]["drive_source"] == src:
            cur.append(t)
            continue
        if cur:
            passes.append(cur)
            cur = []
        if src in KINDS:
            cur = [t]
    if cur:
        passes.append(cur)
    return passes


def derivative(t: np.ndarray, v: np.ndarray, half_s: float = WINDOW_S) -> np.ndarray:
    """dv/dt de cada punto por regresión lineal en [t - half_s, t + half_s]; NaN si hay menos de 5 puntos."""
    out = np.full(len(t), np.nan)
    lo = 0
    hi = 0
    for i in range(len(t)):
        while t[lo] < t[i] - half_s:
            lo += 1
        while hi < len(t) and t[hi] <= t[i] + half_s:
            hi += 1
        if hi - lo >= 5:
            tt = t[lo:hi] - t[i]
            vv = v[lo:hi]
            den = float(np.sum((tt - tt.mean()) ** 2))
            if den > 0:
                out[i] = float(np.sum((tt - tt.mean()) * (vv - vv.mean())) / den)
    return out


def analyze_pass(p: List[dict]) -> dict:
    t = np.array([x["t_s"] for x in p], dtype=float)
    v = np.array([x["speed_kmh"] for x in p], dtype=float) / 3.6
    a = derivative(t, v)
    keep = (t - t[0] >= TRIM_S) & (t[-1] - t >= WINDOW_S) & ~np.isnan(a)
    rows = []
    for i in np.flatnonzero(keep):
        veh = p[i].get("vehicle") or {}
        la = veh.get("local_accel") or [0.0, 0.0, 0.0]
        rows.append({
            "v_kmh": float(v[i] * 3.6), "a": float(a[i]), "gear": int(p[i].get("gear", 0)), "rpm": float(p[i].get("rpm", 0.0)),
            "torque": float(veh.get("engine_torque", 0.0) or 0.0), "game_throttle": float(veh.get("game_throttle", 0.0) or 0.0),
            "la2": float(la[2]) if len(la) > 2 else 0.0,
        })
    return {
        "kind": p[0]["drive_source"], "lap": p[0].get("lap"), "d0": round(p[0]["lap_distance"]), "d1": round(p[-1]["lap_distance"]),
        "v0": round(float(v[0] * 3.6), 1), "v1": round(float(v[-1] * 3.6), 1), "vmax": round(float(v.max() * 3.6), 1),
        "duration_s": round(float(t[-1] - t[0]), 1), "max_cte": round(max(abs(x["cte"]) for x in p), 2), "rows": rows,
    }


def summarize(passes: List[dict]) -> Dict[str, dict]:
    """Por maniobra, marcha y tramo de velocidad: mediana, p10 y p90 de la aceleración y número de ticks."""
    out: Dict[str, dict] = {}
    for kind in KINDS:
        cells = defaultdict(list)
        for p in passes:
            if p["kind"] != kind:
                continue
            for r in p["rows"]:
                cells[(r["gear"], int(r["v_kmh"] // BIN_KMH) * BIN_KMH)].append(r)
        table = []
        for (gear, lo), rs in sorted(cells.items()):
            if len(rs) < 10:
                continue
            aa = sorted(r["a"] for r in rs)
            table.append({
                "gear": gear, "v_kmh": f"{lo}-{lo + BIN_KMH}", "n": len(rs), "a_med": round(st.median(aa), 3),
                "a_p10": round(aa[int(0.1 * (len(aa) - 1))], 3), "a_p90": round(aa[int(0.9 * (len(aa) - 1))], 3),
                "rpm_med": round(st.median(r["rpm"] for r in rs)), "torque_med": round(st.median(r["torque"] for r in rs), 1),
                "game_throttle_med": round(st.median(r["game_throttle"] for r in rs), 2),
            })
        out[kind] = {"passes": sum(1 for p in passes if p["kind"] == kind), "table": table}
    return out


def la2_check(passes: List[dict]) -> Optional[float]:
    """Correlación del eje 2 de local_accel con la derivada, para contrastar (no se usa)."""
    a = [r["a"] for p in passes for r in p["rows"]]
    b = [r["la2"] for p in passes for r in p["rows"]]
    if len(a) < 20 or np.std(b) == 0:
        return None
    return round(float(np.corrcoef(a, b)[0, 1]), 3)


def brake_events(ticks: List[dict]) -> List[dict]:
    """Cada frenada a fondo: tramo continuo de `ident:frenar` (con los cambios de marcha dentro) desde la velocidad de entrada."""
    events: List[dict] = []
    i = 0
    while i < len(ticks):
        if ticks[i].get("drive_source") != "ident:frenar":
            i += 1
            continue
        j = i
        while j + 1 < len(ticks) and ticks[j + 1].get("drive_source") in ("ident:frenar", SHIFT):
            j += 1
        seg = ticks[i:j + 1]
        if len(seg) >= 10:
            t = np.array([x["t_s"] for x in seg], dtype=float)
            v = np.array([x["speed_kmh"] for x in seg], dtype=float) / 3.6
            a = derivative(t, v)
            a = a[~np.isnan(a)]
            dist = (seg[-1]["lap_distance"] - seg[0]["lap_distance"]) % 100000.0
            dur = float(t[-1] - t[0])
            events.append({
                "lap": seg[0].get("lap"), "d0": round(seg[0]["lap_distance"]), "v_in": round(float(v[0] * 3.6), 1),
                "v_out": round(float(v[-1] * 3.6), 1), "dist_m": round(float(dist)), "time_s": round(dur, 2),
                "a_mean": round(float((v[0] - v[-1]) / dur), 2) if dur > 0 else None,
                "a_peak": round(float(-a.min()), 2) if len(a) else None, "gears": sorted({x["gear"] for x in seg}),
                "brake_temp_max": max((max((x.get("vehicle") or {}).get("brake_temp") or [0]) for x in seg), default=0),
                "max_cte": round(max(abs(x["cte"]) for x in seg), 2),
            })
        i = j + 1
    return events


def analyze(ticks: List[dict]) -> dict:
    passes = [analyze_pass(p) for p in split_passes(ticks) if len(p) >= 30]
    return {
        "passes": [{k: v for k, v in p.items() if k != "rows"} for p in passes],
        "summary": summarize(passes),
        "brake_events": brake_events(ticks),
        "local_accel_axis2_corr": la2_check(passes),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log", type=Path)
    ap.add_argument("--json", type=Path, default=None, help="guarda el resultado completo")
    a = ap.parse_args(argv)
    res = analyze(load_ticks(a.log))
    if not res["passes"]:
        print("No hay maniobras de identificación en el log (¿se lanzó con --ident?).")
        return 1
    print(f"{len(res['passes'])} pasadas | contraste local_accel[2]: correlación {res['local_accel_axis2_corr']}")
    for p in res["passes"]:
        print(f"  {p['kind']} vuelta {p['lap']} {p['d0']}-{p['d1']} m: {p['v0']} -> {p['v1']} km/h (máx. {p['vmax']}) "
              f"en {p['duration_s']} s, CTE máx. {p['max_cte']}")
    if res["brake_events"]:
        print("\nfrenadas a fondo (entrada → salida):")
        print("  vuelta     d  v_in  v_out  dist_m  tiempo  a_media  a_máx  marchas  frenos°C  CTE")
        for e in res["brake_events"]:
            print(f"  {e['lap']:>5} {e['d0']:>5} {e['v_in']:>5} {e['v_out']:>6} {e['dist_m']:>7} {e['time_s']:>7} "
                  f"{e['a_mean']:>8} {e['a_peak']:>6}  {','.join(map(str, e['gears'])):>7} {e['brake_temp_max']:>8} {e['max_cte']:>5}")
    for kind, block in res["summary"].items():
        if not block["table"]:
            continue
        what = {"ident:acel": "aceleración (m/s²)", "ident:rodar": "variación de velocidad rodando (m/s², negativa = frena)",
                "ident:frenar": "variación de velocidad frenando a fondo (m/s², negativa = frena)"}[kind]
        print(f"\n{kind}: {block['passes']} pasada(s); {what}")
        print("  marcha  km/h      n   a_med  a_p10  a_p90   rpm  par  gas_juego")
        for r in block["table"]:
            print(f"  {r['gear']:>6}  {r['v_kmh']:>7} {r['n']:>5} {r['a_med']:>7} {r['a_p10']:>6} {r['a_p90']:>6} "
                  f"{r['rpm_med']:>5} {r['torque_med']:>5} {r['game_throttle_med']:>6}")
    if a.json:
        a.json.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        print(f"\nJSON: {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
