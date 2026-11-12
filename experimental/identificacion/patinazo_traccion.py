"""Patinazo trasero con gas (sin juego): techo del deslizamiento a la salida de las curvas, para la A/B del control de tracción (V112).

El control de tracción del coche no tiene bit en el UDP ni toca el gas que se ve (`game_throttle` = gas pedido), así que,
si actúa, corta par en el motor y solo se nota en las ruedas: el deslizamiento trasero con gas topa en un valor fijo
(V112, TC 10 %: techo duro en el 6 %, a la salida de C4, C6 y C9 en 2.ª). Este script lo mide en cualquier log, para
comparar sesiones que solo cambian el TC del garaje.

Deslizamiento trasero = (rps traseras / rps delanteras) / razón de calibración − 1, con las rps en valor absoluto y la
razón calibrada en el propio log rodando recto con el embrague suelto y gas < 0,2 (los radios de las gomas no son iguales:
≈ 0,9425; con más gas la razón sube, 0,948 con gas 0,4-0,6 y 0,960 a fondo, y eso ya es patinazo).
Ticks con gas: gas del juego > `--gas-min`, sin freno, embrague suelto y misma marcha en ±`--margen-cambio` ticks
(fuera de los cambios), a más de 30 km/h. La calibración exige además gas pedido < 0,2: al final de cada cambio el juego
corta el gas mientras entra el embrague (`clutch` > 0) aunque el profesor pida 1,0, y la razón sube a ≈ 0,98 sin ser
rodar libre (2026-11-12).

Uso: `python patinazo_traccion.py <log.jsonl> [--vueltas 4-6] [--contra <otro log>]`
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[2]
VEL_MIN_KMH = 30.0
CALIB_GAS_MAX = 0.2  # rodando recto con poco gas (par < 20) la razón no se mueve: 0,9423-0,9426 en V112 y V121


def parse_range(text: str) -> Tuple[int, int]:
    a, _, b = text.partition("-")
    return int(a), int(b or a)


def load(path: Path, laps: Optional[Tuple[int, int]]) -> Dict[str, np.ndarray]:
    """Ticks del log (todas las vueltas: la calibración usa también las que no entran en la medida)."""
    rows: List[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("type") != "tick":
                continue
            v = r.get("vehicle") or {}
            if "tyre_rps" not in v:
                continue
            rows.append(r)
    if not rows:
        raise SystemExit("sin ticks con tyre_rps")
    veh = [r["vehicle"] for r in rows]
    lap = np.array([r.get("lap", 0) for r in rows])
    return {
        "lap": lap,
        "medir": (lap >= laps[0]) & (lap <= laps[1]) if laps else lap >= 2,
        "s": np.array([r.get("lap_distance", 0.0) for r in rows], float),
        "kmh": np.array([r.get("speed_kmh", 0.0) for r in rows], float),
        "gear": np.array([r.get("gear", 0) for r in rows], int),
        "steer": np.array([r.get("steering", 0.0) for r in rows], float),
        "gas": np.array([v.get("game_throttle", r.get("throttle", 0.0)) for r, v in zip(rows, veh)], float),
        "brake": np.array([max(r.get("brake", 0.0), v.get("game_brake", 0.0)) for r, v in zip(rows, veh)], float),
        "rps": np.abs(np.array([v["tyre_rps"] for v in veh], float)),
        "gas_pedido": np.array([r.get("throttle", 0.0) for r in rows], float),
        "clutch": np.array([v.get("clutch", 0) for v in veh], int),
    }


def gear_stable(gear: np.ndarray, margin: int) -> np.ndarray:
    """True donde la marcha es la misma en los `margin` ticks de antes y de después."""
    ok = np.ones(len(gear), bool)
    for k in range(1, margin + 1):
        ok[k:] &= gear[k:] == gear[:-k]
        ok[:-k] &= gear[:-k] == gear[k:]
    ok[:margin] = False
    ok[len(gear) - margin:] = False
    return ok


def ratio_raw(d: Dict[str, np.ndarray]) -> np.ndarray:
    front = d["rps"][:, :2].mean(axis=1)
    rear = d["rps"][:, 2:].mean(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(front > 1.0, rear / front, np.nan)


def calibrate(d: Dict[str, np.ndarray], stable: np.ndarray) -> Tuple[float, int]:
    """Razón traseras / delanteras rodando recto con poco gas (mediana) y cuántos ticks la sostienen."""
    m = stable & (d["clutch"] == 0) & (d["gas"] < CALIB_GAS_MAX) & (d["gas_pedido"] < CALIB_GAS_MAX) & (d["brake"] < 0.01) & (np.abs(d["steer"]) < 0.02) & (d["kmh"] > 60.0)
    r = ratio_raw(d)[m]
    r = r[np.isfinite(r)]
    if len(r) < 10:
        raise SystemExit(f"solo {len(r)} ticks para calibrar la razón traseras/delanteras")
    return float(np.median(r)), int(len(r))


def analyze(path: Path, laps: Optional[Tuple[int, int]] = None, gas_min: float = 0.5, margin: int = 5,
            ceiling_band: float = 0.5) -> Dict[str, Any]:
    d = load(path, laps)
    stable = gear_stable(d["gear"], margin)
    calib, n_calib = calibrate(d, stable)
    slip = (ratio_raw(d) / calib - 1.0) * 100.0  # %
    m = d["medir"] & stable & (d["clutch"] == 0) & (d["gas"] > gas_min) & (d["brake"] < 0.01) & (d["kmh"] > VEL_MIN_KMH) & np.isfinite(slip)
    s = slip[m]
    if len(s) == 0:
        raise SystemExit("sin ticks con gas en las vueltas pedidas")
    top = float(np.max(s))
    hist = {int(k): int(n) for k, n in zip(*np.unique(np.floor(s).astype(int), return_counts=True))}
    near = m & (slip >= top - ceiling_band)
    cat = _catalogo(path)
    zones: Dict[str, Dict[str, Any]] = {}
    for i in np.flatnonzero(near):
        name = cat.etiqueta(d["s"][i]) if cat else f"{int(d['s'][i] // 50 * 50)} m"
        z = zones.setdefault(name, {"n": 0, "gears": set(), "s": [], "kmh": []})
        z["n"] += 1
        z["gears"].add(int(d["gear"][i]))
        z["s"].append(float(d["s"][i]))
        z["kmh"].append(float(d["kmh"][i]))
    by_gear = {}
    for g in sorted(set(d["gear"][m].tolist())):
        sg = slip[m & (d["gear"] == g)]
        by_gear[int(g)] = {"n": int(len(sg)), "p50": float(np.percentile(sg, 50)), "p99": float(np.percentile(sg, 99)), "max": float(np.max(sg))}
    return {
        "log": path.name,
        "vueltas": laps,
        "calibracion": calib,
        "n_calibracion": n_calib,
        "n": int(len(s)),
        "p50": float(np.percentile(s, 50)),
        "p90": float(np.percentile(s, 90)),
        "p99": float(np.percentile(s, 99)),
        "max": top,
        "histograma": hist,
        "por_marcha": by_gear,
        "techo": {k: {"n": v["n"], "marchas": sorted(v["gears"]), "s": (min(v["s"]), max(v["s"])),
                      "kmh": (min(v["kmh"]), max(v["kmh"]))} for k, v in sorted(zones.items(), key=lambda kv: -kv[1]["n"])},
        "n_techo": int(near.sum()),
    }


def _catalogo(path: Path):
    try:
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from circuito_virtual.src.curvas import catalogo_de_log  # noqa: PLC0415

        return catalogo_de_log(path)
    except Exception:  # sin catálogo, las zonas salen por tramos de 50 m
        return None


def _print(r: Dict[str, Any], band: float) -> None:
    print(f"== {r['log']}  (vueltas {r['vueltas'] or '2 en adelante'})")
    print(f"razón traseras/delanteras calibrada: {r['calibracion']:.4f} ({r['n_calibracion']} ticks rectos con gas < 0,2)")
    print(f"deslizamiento trasero con gas ({r['n']} ticks): mediana {r['p50']:.1f} %, p90 {r['p90']:.1f} %, p99 {r['p99']:.1f} %, máx. {r['max']:.1f} %")
    print("  histograma (% entero: ticks): " + ", ".join(f"{k}: {n}" for k, n in r["histograma"].items()))
    print("  por marcha: " + "; ".join(f"{g}.ª n {v['n']} mediana {v['p50']:.1f} p99 {v['p99']:.1f} máx. {v['max']:.1f}" for g, v in r["por_marcha"].items()))
    print(f"  pegados al techo (≥ máx. − {band:g} puntos): {r['n_techo']} ticks")
    for name, z in r["techo"].items():
        print(f"    {name:<14} {z['n']:4d} ticks  marcha {z['marchas']}  {z['s'][0]:.0f}-{z['s'][1]:.0f} m  {z['kmh'][0]:.0f}-{z['kmh'][1]:.0f} km/h")


def main(argv: Optional[Sequence[str]] = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("log", type=Path)
    ap.add_argument("--vueltas", default="4-6", help="vueltas medidas, «4-6» (por defecto); la calibración usa todas")
    ap.add_argument("--contra", type=Path, action="append", default=[], help="otro log a medir igual (se puede repetir)")
    ap.add_argument("--gas-min", type=float, default=0.5)
    ap.add_argument("--margen-cambio", type=int, default=5, help="ticks sin cambio de marcha antes y después")
    ap.add_argument("--banda-techo", type=float, default=0.5, help="puntos bajo el máximo que cuentan como «en el techo»")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    laps = parse_range(a.vueltas)
    out = []
    for p in [a.log, *a.contra]:
        r = analyze(p, laps, a.gas_min, a.margen_cambio, a.banda_techo)
        _print(r, a.banda_techo)
        print()
        out.append(r)
    if a.json:
        a.json.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=list), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
