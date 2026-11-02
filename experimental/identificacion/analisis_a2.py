"""A2.1: el solver de perfil de velocidad reproduce las maniobras de A1 (aceleración a fondo y frenadas a fondo).

De los logs de A1 saca las tablas `a_acel(v)` y `a_freno(v)` (con `analisis_a1`, ya corregidas de pendiente), construye `CarParams` y comprueba
que, partiendo de la velocidad de entrada de cada maniobra, el modelo integrado a lo largo de la pista (con su pendiente) da el mismo tiempo y
la misma distancia que el coche. Dos comprobaciones:

- **dentro de la muestra:** tablas con todos los logs;
- **dejando un log fuera:** tablas con los demás y predicción del log que falta (la prueba honesta).

No es la prueba de la hipótesis de A2 (error de tiempo de vuelta < 3 % con vueltas a ritmo real): todavía no hay vueltas a ritmo real, y las
tablas llegan a 140 km/h (V56). Además imprime la vuelta potencial del modelo con ese tope, solo como información.

Uso:
    python experimental/identificacion/analisis_a2.py [--json salida.json] [--guardar circuito_virtual/coches/formula_rookie/parametros_a1.json]
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

_REPO = Path(__file__).resolve().parents[2]
for _p in (_REPO, _REPO / "PCARS2-AI" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from experimental.common import analisis_a1 as a1  # noqa: E402
from circuito_virtual.src import perfil_velocidad as pv  # noqa: E402

LOGS = _REPO / "PCARS2-AI" / "logs" / "learning"
ACEL_LOGS = ("20261031T172531Z", "20261031T173744Z", "20261031T175152Z", "20261031T180907Z", "20261101T000938Z", "20261101T195353Z")  # el último: techo a 140 km/h con 3.ª (V43)
BRAKE_LOGS = ("20261031T183302Z", "20261031T185936Z")
V_KNOWN_KMH = 140.0  # hasta 120 en 1ª y 2ª (el corte de la 2ª, H50), hasta 125 con la 3ª (G1, H60) y hasta 140 con el techo de V43 (log 20261101T195353Z)
MIN_PASS_S = 1.0
MIN_PASS_KMH = 8.0
MIN_V0_KMH = 20.0  # la salida parada (embrague, arranque) no está en el modelo
GRADE_LOGS = ("20261031T221721Z", "20261031T225254Z", "20261031T215824Z")  # vueltas completas a 60 km/h: cubren toda la pista


def measured_track() -> pv.Track:
    """Pista de `sugo_ai.json` con la pendiente que midió el coche en las vueltas completas de A1.3."""
    track = pv.Track.from_reference()
    ticks: List[dict] = []
    for s in GRADE_LOGS:
        ticks += [{"lap": x.get("lap"), "lap_distance": x["lap_distance"], "vehicle": {"position": ((x.get("vehicle") or {}).get("position"))}}
                  for x in a1.load_ticks(_path(s))]
    grade = pv.grade_from_ticks(ticks, track.n)
    if grade is not None:
        track.grade_ref = track.grade
        track.grade = grade
    return track


def _path(stamp: str) -> Path:
    return LOGS / f"{stamp}_sugo_gp_l1_linea.jsonl"


def collect(stamp_acel: Sequence[str] = ACEL_LOGS, stamp_brake: Sequence[str] = BRAKE_LOGS) -> Dict[str, dict]:
    """Por log: filas de aceleración / frenada y maniobras medidas, para no leer cada log más de una vez."""
    out: Dict[str, dict] = {}
    for s in stamp_acel:
        ticks = a1.load_ticks(_path(s))
        passes = [a1.analyze_pass(p) for p in a1.split_passes(ticks) if p[0]["drive_source"] == "ident:acel" and len(p) > 40]
        out[s] = {"kind": "acel", "rows": [r for p in passes for r in p["rows"] if r["v_kmh"] <= V_KNOWN_KMH],
                  "passes": [(p, _pass_ticks(ticks, p)) for p in passes]}
    for s in stamp_brake:
        ticks = a1.load_ticks(_path(s))
        out[s] = {"kind": "frenar", "rows": [], "ticks": ticks}
    return out


def _pass_ticks(ticks: List[dict], p: dict) -> List[dict]:
    return [x for x in ticks if x.get("lap") == p["lap"] and x.get("drive_source") == p["kind"] and p["d0"] <= x["lap_distance"] <= p["d1"]]


def fit(data: Dict[str, dict], track: pv.Track, skip: Optional[str] = None) -> pv.CarParams:
    """Tablas de aceleración y frenada y retraso del freno con todos los logs menos `skip`."""
    acel_rows = [r for s, d in data.items() if d["kind"] == "acel" and s != skip for r in d["rows"]]
    brake_rows: List[dict] = []
    for s, d in data.items():
        if d["kind"] != "frenar" or s == skip:
            continue
        brake_rows.extend(_brake_rows(d["ticks"]))
    accel = pv.table_points(a1._table(acel_rows, by_gear=False), min_kmh=10.0)
    brake = [(v, -x) for v, x in pv.table_points(a1._table(brake_rows, by_gear=False, min_n=8), min_kmh=40.0)]  # la tabla da dv/dt (< 0)
    car = pv.CarParams(accel, brake, v_known_kmh=V_KNOWN_KMH)
    diffs = []
    for s, d in data.items():
        if d['kind'] == 'frenar' and s != skip:
            diffs += [r['t_meas'] - r['t_pred'] for r in predict_brake_events({s: d}, car, track)]
    car.brake_delay_s = round(st.median(diffs), 3) if diffs else 0.0
    return car


def _brake_rows(ticks: List[dict]) -> List[dict]:
    import numpy as np

    half, trim = a1.WINDOWS["ident:frenar"]
    rows = []
    for seg in a1._brake_segments(ticks):
        t = np.array([x["t_s"] for x in seg], dtype=float)
        v = np.array([x["speed_kmh"] for x in seg], dtype=float) / 3.6
        a = a1.derivative(t, v, half)
        gr = a1.grades(seg)
        gm = float(np.nanmean(gr)) if np.isfinite(gr).any() else 0.0
        for k in np.flatnonzero(~np.isnan(a) & (t - t[0] >= trim) & (t[-1] - t >= half)):
            g_k = float(gr[k]) if np.isfinite(gr[k]) else gm
            rows.append({"v_kmh": float(v[k] * 3.6), "a": float(a[k]) + a1.G * g_k, "a_raw": float(a[k]), "grade": g_k,
                         "grade_known": bool(np.isfinite(gr[k])), "gear": 0, "rpm": 0.0, "torque": 0.0, "game_throttle": 0.0})
    return rows


def predict_accel_passes(data: Dict[str, dict], car: pv.CarParams, track: pv.Track, only: Optional[str] = None) -> List[dict]:
    out = []
    for s, d in data.items():
        if d["kind"] != "acel" or (only and s != only):
            continue
        for p, ticks in d["passes"]:
            if len(ticks) < 2 or p["duration_s"] < MIN_PASS_S or p["v0"] < MIN_V0_KMH or p["v1"] - p["v0"] < MIN_PASS_KMH or p["v1"] > V_KNOWN_KMH:
                continue
            t_meas = ticks[-1]["t_s"] - ticks[0]["t_s"]
            dist_meas = ticks[-1]["lap_distance"] - ticks[0]["lap_distance"]
            t_pred, dist_pred = pv.simulate_accel(track, car, ticks[0]["lap_distance"], p["v0"] / 3.6, p["v1"] / 3.6)
            out.append({"log": s, "d0": p["d0"], "v0": p["v0"], "v1": p["v1"], "t_meas": round(t_meas, 2), "t_pred": round(t_pred, 2),
                        "t_err_pct": round(100 * (t_pred - t_meas) / t_meas, 1), "dist_meas": round(dist_meas, 1),
                        "dist_pred": round(dist_pred, 1), "dist_err_pct": round(100 * (dist_pred - dist_meas) / dist_meas, 1)})
    return out


def predict_brake_events(data: Dict[str, dict], car: pv.CarParams, track: pv.Track, only: Optional[str] = None) -> List[dict]:
    out = []
    for s, d in data.items():
        if d["kind"] != "frenar" or (only and s != only):
            continue
        for e in a1.brake_events(d["ticks"]):
            if e["v_in"] <= e["v_out"] or e["time_s"] < 0.5 or e["v_out"] < 30.0:
                continue
            t_pred, dist_pred = pv.simulate_brake(track, car, e["d0"], e["v_in"] / 3.6, e["v_out"] / 3.6)
            out.append({"log": s, "d0": e["d0"], "v_in": e["v_in"], "v_out": e["v_out"], "t_meas": e["time_s"], "t_pred": round(t_pred, 2),
                        "t_err_pct": round(100 * (t_pred - e["time_s"]) / e["time_s"], 1), "dist_meas": e["dist_m"],
                        "dist_pred": round(dist_pred, 1),
                        "dist_err_pct": round(100 * (dist_pred - e["dist_m"]) / e["dist_m"], 1) if e["dist_m"] else None})
    return out


def _stats(rows: List[dict], key: str = "t_err_pct") -> dict:
    vals = [abs(r[key]) for r in rows if r.get(key) is not None]
    return {"n": len(vals), "mediana": round(st.median(vals), 1) if vals else None, "max": round(max(vals), 1) if vals else None}


def analyze(data: Optional[Dict[str, dict]] = None, track: Optional[pv.Track] = None) -> dict:
    data = data or collect()
    track = track or measured_track()
    car = fit(data, track)
    inside = {"acel": predict_accel_passes(data, car, track), "frenar": predict_brake_events(data, car, track)}
    loo = {"acel": [], "frenar": []}
    for s in data:
        car_s = fit(data, track, skip=s)
        loo["acel"] += predict_accel_passes(data, car_s, track, only=s)
        loo["frenar"] += predict_brake_events(data, car_s, track, only=s)
    prof = pv.solve(track, car)
    return {
        "params": car.to_dict(),
        "dentro": {k: {"stats_tiempo": _stats(v), "stats_distancia": _stats(v, "dist_err_pct"), "filas": v} for k, v in inside.items()},
        "log_fuera": {k: {"stats_tiempo": _stats(v), "stats_distancia": _stats(v, "dist_err_pct"), "filas": v} for k, v in loo.items()},
        "vuelta_potencial": {"tope_kmh": car.v_known_kmh, "tiempo_s": round(prof.time_s, 1), "en_el_tope": round(prof.share_at_cap, 3),
                             "limite_lateral": round(prof.share_lateral, 3), "frenando": round(prof.share_braking, 3),
                             "acelerando": round(prof.share_accel, 3), "v_media_kmh": round(track.length_m / prof.time_s * 3.6, 1)},
    }


def _print(res: dict) -> None:
    print("Parámetros ajustados (km/h → m/s²):")
    print("  aceleración:", ", ".join(f"{v:g}→{a:.2f}" for v, a in res["params"]["accel"]))
    print("  frenada:    ", ", ".join(f"{v:g}→{a:.2f}" for v, a in res["params"]["brake"]))
    print(f"  μ = {res['params']['mu']:g} m/s², k = {res['params']['k']:g}, tope de las tablas {res['params']['v_known_kmh']:g} km/h, "
          f"retraso del freno {res['params']['brake_delay_s']:g} s")
    for title, key in (("DENTRO DE LA MUESTRA", "dentro"), ("DEJANDO UN LOG FUERA", "log_fuera")):
        print(f"\n{title}")
        for kind in ("acel", "frenar"):
            blk = res[key][kind]
            print(f"  {kind}: {blk['stats_tiempo']['n']} maniobras · error de tiempo mediana {blk['stats_tiempo']['mediana']} %"
                  f" máx. {blk['stats_tiempo']['max']} % · error de distancia mediana {blk['stats_distancia']['mediana']} %"
                  f" máx. {blk['stats_distancia']['max']} %")
    vp = res["vuelta_potencial"]
    print(f"\nVuelta potencial del modelo (tope {vp['tope_kmh']:g} km/h, μ de D21): {vp['tiempo_s']} s, {vp['v_media_kmh']} km/h de media; "
          f"{100 * vp['en_el_tope']:.0f} % en el tope, {100 * vp['limite_lateral']:.0f} % en el límite lateral, "
          f"{100 * vp['frenando']:.0f} % frenando, {100 * vp['acelerando']:.0f} % acelerando")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "A2.1").splitlines()[0])
    ap.add_argument("--json", type=Path, default=None, help="guarda el resultado completo")
    ap.add_argument("--guardar", type=Path, default=None, help="guarda los parámetros ajustados (CarParams)")
    args = ap.parse_args(argv)
    res = analyze()
    _print(res)
    if args.json:
        args.json.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.guardar:
        pv.save_params(pv.CarParams.from_dict(res["params"]), args.guardar, {"logs": list(ACEL_LOGS + BRAKE_LOGS)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
