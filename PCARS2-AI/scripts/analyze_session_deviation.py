#!/usr/bin/env python3
"""
Analiza desviación lateral y primer contacto con hierba en un log JSONL de sesión.

Uso:
    python scripts/analyze_session_deviation.py logs/teaching/....jsonl
    python scripts/analyze_session_deviation.py logs/teaching/....jsonl --hotspot 441
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

# Permite ejecutar desde raíz PCARS2-AI
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))


def _load_ticks(path: Path) -> tuple[dict | None, list[dict]]:
    session = None
    ticks: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("type") == "session":
                session = row
            elif row.get("type") == "tick":
                ticks.append(row)
    return session, ticks


def _signed(t: dict) -> float:
    if "signed_cte" in t:
        return float(t["signed_cte"])
    td = t.get("track_diag") or {}
    if "signed_cte" in td:
        return float(td["signed_cte"])
    return float(t.get("cte", 0.0))


def _off_surface(t: dict) -> bool:
    if t.get("off_surface"):
        return True
    td = t.get("track_diag") or {}
    return bool(td.get("any_off_track_terrain"))


def _print_drift_bins(ticks: list[dict], bin_m: int = 50, max_m: int = 3600) -> None:
    print("\n=== Deriva lateral por tramo (signed_cte medio) ===")
    print("  Negativo = coche a la IZQUIERDA de la línea humana grabada.\n")
    for b in range(0, max_m, bin_m):
        w = [t for t in ticks if b <= float(t.get("lap_distance", 0)) < b + bin_m]
        if not w:
            continue
        signed_avg = statistics.mean(_signed(t) for t in w)
        cte_avg = statistics.mean(float(t.get("cte", 0)) for t in w)
        surf_pct = 100.0 * sum(1 for t in w if _off_surface(t)) / len(w)
        print(
            f"  {b:4}-{b + bin_m:4} m | n={len(w):5} | signed={signed_avg:+.2f} m | "
            f"|cte|={cte_avg:.2f} m | off_surface={surf_pct:4.1f}%"
        )


def _first_event(ticks: list[dict], pred, label: str) -> None:
    for t in ticks:
        if pred(t):
            td = t.get("track_diag") or {}
            print(f"\n=== Primer {label} ===")
            print(f"  t={t.get('t_s')} s | lap_distance={t.get('lap_distance')} m")
            print(f"  speed={t.get('speed_kmh')} km/h | signed_cte={_signed(t):+.3f} m | cte={t.get('cte')} m")
            print(f"  reason={t.get('teacher_reason')} | safety_event={t.get('safety_event')}")
            if td:
                print(f"  pos=({td.get('pos_x')}, {td.get('pos_z')}) ref=({td.get('ref_x')}, {td.get('ref_z')})")
                print(f"  terrain={td.get('terrain')} grass_wheels={td.get('wheels_grass')} off={td.get('wheels_off')}")
                print(f"  closest_d={td.get('closest_lap_distance')} mismatch={td.get('lap_distance_mismatch_m')} m")
            return
    print(f"\n(No hubo {label} en el log)")


def _hotspot_window(ticks: list[dict], center: float, half: float = 25.0) -> None:
    lo, hi = center - half, center + half
    w = [t for t in ticks if lo <= float(t.get("lap_distance", 0)) <= hi]
    if not w:
        print(f"\nSin ticks en ventana {lo}-{hi} m")
        return
    print(f"\n=== Ventana hotspot {lo}-{hi} m (n={len(w)}) ===")
    print(f"  signed_cte: mean={statistics.mean(_signed(t) for t in w):+.2f} p95={sorted(abs(_signed(t)) for t in w)[int(0.95*len(w))-1]:.2f}")
    print(f"  off_surface: {100*sum(1 for t in w if _off_surface(t))/len(w):.1f}%")
    reasons = Counter(t.get("teacher_reason") for t in w)
    print(f"  reasons: {reasons.most_common(5)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico de desviación / hierba en sesión JSONL")
    parser.add_argument("jsonl", type=Path, help="Ruta al .jsonl de sesión")
    parser.add_argument("--hotspot", type=float, default=441.0, help="Metro de interés (default 441)")
    parser.add_argument("--bin", type=int, default=50, help="Tamaño de bin para deriva (m)")
    args = parser.parse_args()

    if not args.jsonl.is_file():
        print(f"No existe: {args.jsonl}", file=sys.stderr)
        return 1

    session, ticks = _load_ticks(args.jsonl)
    if not ticks:
        print("Sin ticks en el log.")
        return 1

    has_diag = sum(1 for t in ticks if t.get("track_diag")) 
    print(f"Archivo: {args.jsonl}")
    if session:
        print(f"Sesión: mode={session.get('mode')} phase={session.get('phase')} target={session.get('speed_target_kmh')} km/h")
    print(f"Ticks: {len(ticks)} | con track_diag: {has_diag}")

    _print_drift_bins(ticks, bin_m=args.bin)
    _first_event(ticks, lambda t: t.get("safety_override"), "safety_override")
    _first_event(ticks, _off_surface, "off_surface (hierba UDP)")
    _hotspot_window(ticks, args.hotspot)

    print("\n=== Interpretación rápida ===")
    print(
        "  Si signed_cte se queda en ~-3 m muchos tramos ANTES de la hierba, el coche va\n"
        "  paralelo pero DESCENTRADO respecto a la vuelta humana: no es que la ref esté mal,\n"
        "  es que el teacher no recentra (ganancia lateral / suavizado del volante).\n"
        "  Con ~3 m al borde interior/exterior, una rueda puede marcar GRASS con CTE ~3 m.\n"
        "  Vuelve a grabar con --diag-track en teaching_driver para ver terrain por rueda.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
