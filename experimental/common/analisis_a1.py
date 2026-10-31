"""Análisis de las sesiones de identificación A1 (maniobras `ident:*` de `learn_driver --ident`).

De cada pasada saca la aceleración longitudinal como derivada de la velocidad (regresión lineal en una ventana corta sobre el
reloj del PC, que va a 60 Hz) y **le quita el efecto de la pendiente**: a_llano = a_medida + g · pendiente, con la pendiente de la
posición vertical (`vehicle.position[1]`) frente a la distancia horizontal recorrida. Sin esto no se puede comparar nada: la recta
de 3113 m sube un 9,8 % hasta ≈ 3320 m y llega al 1 % hacia 3440 m, lo que mueve la aceleración medida ≈ ±1 m/s² (H51).

- `acel` da `a_acel(v, marcha)`; `rodar` da la desaceleración por resistencia al avance (con el freno motor de la marcha engranada).
- Las frenadas a fondo (`ident:frenar`, A1.2) se resumen por evento (velocidad de entrada y salida, distancia, tiempo, deceleración
  media y máxima, medidas y corregidas de pendiente) y como curva `a_freno(v)` por tramos de 10 km/h. Un cambio de marcha a mitad de
  frenada no parte el evento.
- El eje 2 de `local_accel` se imprime solo como contraste (H1).

Uso:
    python experimental/common/analisis_a1.py PCARS2-AI/logs/learning/<ts>_sugo_gp_l1_linea.jsonl [--json salida.json]
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
G = 9.81
BIN_KMH = 10
# (semiancho de la derivada, recorte del principio) por maniobra: una frenada a fondo dura < 2 s y el pedal responde enseguida
WINDOWS = {"ident:acel": (0.25, 0.5), "ident:rodar": (0.25, 0.5), "ident:frenar": (0.10, 0.10)}
GRADE_HALF_S = 0.4
GRADE_MIN_RUN_M = 3.0  # con menos recorrido en la ventana la pendiente no se puede medir


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


def derivative(t: np.ndarray, v: np.ndarray, half_s: float = 0.25) -> np.ndarray:
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


def grades(seg: List[dict], half_s: float = GRADE_HALF_S) -> np.ndarray:
    """Pendiente (subida/recorrido horizontal, + = cuesta arriba) de cada tick, de la posición del coche; NaN si no se puede."""
    pos = np.array([((x.get("vehicle") or {}).get("position") or [np.nan] * 3)[:3] for x in seg], dtype=float)
    out = np.full(len(seg), np.nan)
    if len(seg) < 5 or np.isnan(pos).any():
        return out
    t = np.array([x["t_s"] for x in seg], dtype=float)
    s = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(pos[:, 0]), np.diff(pos[:, 2])))])
    y = pos[:, 1]
    lo = 0
    hi = 0
    for i in range(len(seg)):
        while t[lo] < t[i] - half_s:
            lo += 1
        while hi < len(seg) and t[hi] <= t[i] + half_s:
            hi += 1
        if hi - lo >= 5 and s[hi - 1] - s[lo] >= GRADE_MIN_RUN_M:
            ss = s[lo:hi]
            den = float(np.sum((ss - ss.mean()) ** 2))
            if den > 0:
                out[i] = float(np.sum((ss - ss.mean()) * (y[lo:hi] - y[lo:hi].mean())) / den)
    return out


def analyze_pass(p: List[dict]) -> dict:
    kind = p[0]["drive_source"]
    half, trim = WINDOWS[kind]
    t = np.array([x["t_s"] for x in p], dtype=float)
    v = np.array([x["speed_kmh"] for x in p], dtype=float) / 3.6
    a = derivative(t, v, half)
    gr = grades(p)
    keep = (t - t[0] >= trim) & (t[-1] - t >= half) & ~np.isnan(a)
    rows = []
    for i in np.flatnonzero(keep):
        veh = p[i].get("vehicle") or {}
        la = veh.get("local_accel") or [0.0, 0.0, 0.0]
        known = bool(np.isfinite(gr[i]))
        grade = float(gr[i]) if known else 0.0
        rows.append({
            "v_kmh": float(v[i] * 3.6), "a_raw": float(a[i]), "a": float(a[i]) + G * grade, "grade": grade, "grade_known": known,
            "gear": int(p[i].get("gear", 0)), "rpm": float(p[i].get("rpm", 0.0)),
            "torque": float(veh.get("engine_torque", 0.0) or 0.0), "game_throttle": float(veh.get("game_throttle", 0.0) or 0.0),
            "la2": float(la[2]) if len(la) > 2 else 0.0,
        })
    return {
        "kind": kind, "lap": p[0].get("lap"), "d0": round(p[0]["lap_distance"]), "d1": round(p[-1]["lap_distance"]),
        "v0": round(float(v[0] * 3.6), 1), "v1": round(float(v[-1] * 3.6), 1), "vmax": round(float(v.max() * 3.6), 1),
        "duration_s": round(float(t[-1] - t[0]), 1), "max_cte": round(max(abs(x["cte"]) for x in p), 2), "rows": rows,
    }


def _table(rows: List[dict], by_gear: bool, min_n: int = 10) -> List[dict]:
    cells = defaultdict(list)
    for r in rows:
        cells[(r["gear"] if by_gear else -1, int(r["v_kmh"] // BIN_KMH) * BIN_KMH)].append(r)
    table = []
    for (gear, lo), rs in sorted(cells.items()):
        if len(rs) < min_n:
            continue
        aa = sorted(r["a"] for r in rs)
        table.append({
            "gear": gear if by_gear else None, "v_kmh": f"{lo}-{lo + BIN_KMH}", "n": len(rs), "a_med": round(st.median(aa), 3),
            "a_p10": round(aa[int(0.1 * (len(aa) - 1))], 3), "a_p90": round(aa[int(0.9 * (len(aa) - 1))], 3),
            "a_raw_med": round(st.median(r["a_raw"] for r in rs), 3),
            "grade_med_pct": round(100 * st.median(r["grade"] for r in rs), 1),
            "no_grade": sum(1 for r in rs if not r["grade_known"]),
            "rpm_med": round(st.median(r["rpm"] for r in rs)), "torque_med": round(st.median(r["torque"] for r in rs), 1),
            "game_throttle_med": round(st.median(r["game_throttle"] for r in rs), 2),
        })
    return table


def summarize(passes: List[dict]) -> Dict[str, dict]:
    """Por maniobra de aceleración o de rodar: marcha y tramo de velocidad con mediana, p10 y p90 (a_med ya corregida de pendiente)."""
    out: Dict[str, dict] = {}
    for kind in ("ident:acel", "ident:rodar"):
        mine = [p for p in passes if p["kind"] == kind]
        out[kind] = {"passes": len(mine), "table": _table([r for p in mine for r in p["rows"]], by_gear=True)}
    return out


def _brake_segments(ticks: List[dict]):
    """Cada frenada a fondo: tramo continuo de `ident:frenar` (con los cambios de marcha dentro) desde la velocidad de entrada."""
    i = 0
    while i < len(ticks):
        if ticks[i].get("drive_source") != "ident:frenar":
            i += 1
            continue
        j = i
        while j + 1 < len(ticks) and ticks[j + 1].get("drive_source") in ("ident:frenar", SHIFT):
            j += 1
        if j - i + 1 >= 10:
            yield ticks[i:j + 1]
        i = j + 1


def brake_events(ticks: List[dict]) -> List[dict]:
    half, trim = WINDOWS["ident:frenar"]
    events: List[dict] = []
    for seg in _brake_segments(ticks):
        t = np.array([x["t_s"] for x in seg], dtype=float)
        v = np.array([x["speed_kmh"] for x in seg], dtype=float) / 3.6
        a = derivative(t, v, half)
        gr = grades(seg)
        ok = ~np.isnan(a) & (t - t[0] >= trim) & (t[-1] - t >= half)
        gm = float(np.nanmean(gr)) if np.isfinite(gr).any() else 0.0
        dur = float(t[-1] - t[0])
        a_mean = float((v[0] - v[-1]) / dur) if dur > 0 else float("nan")
        flat = a + G * np.where(np.isfinite(gr), gr, gm)
        events.append({
            "lap": seg[0].get("lap"), "d0": round(seg[0]["lap_distance"]), "v_in": round(float(v[0] * 3.6), 1),
            "v_out": round(float(v[-1] * 3.6), 1), "dist_m": round((seg[-1]["lap_distance"] - seg[0]["lap_distance"]) % 100000.0),
            "time_s": round(dur, 2), "grade_pct": round(100 * gm, 1),
            "a_mean_raw": round(a_mean, 2), "a_mean": round(a_mean - G * gm, 2),  # deceleración (+) medida y corregida de pendiente
            "a_peak": round(float(-flat[ok].min()), 2) if ok.any() else None, "gears": sorted({x["gear"] for x in seg}),
            "brake_temp_max": max((max((x.get("vehicle") or {}).get("brake_temp") or [0]) for x in seg), default=0),
            "max_cte": round(max(abs(x["cte"]) for x in seg), 2),
        })
    return events


def brake_curve(ticks: List[dict]) -> List[dict]:
    """a_freno(v): variación de velocidad corregida de pendiente por tramos de 10 km/h, juntando todas las marchas de cada frenada."""
    half, trim = WINDOWS["ident:frenar"]
    rows: List[dict] = []
    for seg in _brake_segments(ticks):
        t = np.array([x["t_s"] for x in seg], dtype=float)
        v = np.array([x["speed_kmh"] for x in seg], dtype=float) / 3.6
        a = derivative(t, v, half)
        gr = grades(seg)
        gm = float(np.nanmean(gr)) if np.isfinite(gr).any() else 0.0
        for k in np.flatnonzero(~np.isnan(a) & (t - t[0] >= trim) & (t[-1] - t >= half)):
            known = bool(np.isfinite(gr[k]))
            g_k = float(gr[k]) if known else gm
            rows.append({"v_kmh": float(v[k] * 3.6), "a": float(a[k]) + G * g_k, "a_raw": float(a[k]), "grade": g_k,
                         "grade_known": known, "gear": 0, "rpm": 0.0, "torque": 0.0, "game_throttle": 0.0})
    return _table(rows, by_gear=False, min_n=8)


def la2_check(passes: List[dict]) -> Optional[float]:
    """Correlación del eje 2 de local_accel con la derivada, para contrastar (no se usa)."""
    a = [r["a_raw"] for p in passes for r in p["rows"]]
    b = [r["la2"] for p in passes for r in p["rows"]]
    if len(a) < 20 or np.std(b) == 0:
        return None
    return round(float(np.corrcoef(a, b)[0, 1]), 3)


def analyze(ticks: List[dict]) -> dict:
    passes = [analyze_pass(p) for p in split_passes(ticks) if len(p) >= 12]
    return {
        "passes": [{k: v for k, v in p.items() if k != "rows"} for p in passes],
        "summary": summarize(passes),
        "brake_events": brake_events(ticks),
        "brake_curve": brake_curve(ticks),
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
        print("\nfrenadas a fondo (deceleración en m/s², + = frena; 'corr.' = quitada la pendiente):")
        print("  vuelta     d  v_in  v_out  dist_m  tiempo  pend%  a_media  a_corr.  a_máx  marchas  frenos°C  CTE")
        for e in res["brake_events"]:
            print(f"  {e['lap']:>5} {e['d0']:>5} {e['v_in']:>5} {e['v_out']:>6} {e['dist_m']:>7} {e['time_s']:>7} {e['grade_pct']:>6} "
                  f"{e['a_mean_raw']:>8} {e['a_mean']:>8} {e['a_peak']:>6}  {','.join(map(str, e['gears'])):>7} "
                  f"{e['brake_temp_max']:>8} {e['max_cte']:>5}")
    if res["brake_curve"]:
        print("\na_freno(v) corregida de pendiente (todas las marchas; a negativa = frena):")
        print("    km/h      n   a_med  a_p10  a_p90  a_medida  pend%")
        for r in res["brake_curve"]:
            print(f"  {r['v_kmh']:>7} {r['n']:>6} {r['a_med']:>7} {r['a_p10']:>6} {r['a_p90']:>6} {r['a_raw_med']:>9} {r['grade_med_pct']:>6}")
    for kind, block in res["summary"].items():
        if not block["table"]:
            continue
        what = "aceleración (m/s²)" if kind.endswith("acel") else "variación de velocidad rodando (m/s², negativa = frena)"
        print(f"\n{kind}: {block['passes']} pasada(s); {what}, corregida de pendiente")
        print("  marcha  km/h      n   a_med  a_p10  a_p90  a_medida  pend%   rpm  par  gas_juego  sin_pend")
        for r in block["table"]:
            print(f"  {r['gear']:>6}  {r['v_kmh']:>7} {r['n']:>5} {r['a_med']:>7} {r['a_p10']:>6} {r['a_p90']:>6} {r['a_raw_med']:>9} "
                  f"{r['grade_med_pct']:>6} {r['rpm_med']:>5} {r['torque_med']:>5} {r['game_throttle_med']:>6} {r['no_grade']:>8}")
    if a.json:
        a.json.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        print(f"\nJSON: {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
