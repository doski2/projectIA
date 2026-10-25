"""
ppo_progress.py
Dice si una tirada de PPO "va bien encaminada" sin tener que leer los CSV a mano.

    python src/ppo_progress.py                      # logs/formula_rookie__sugo
    python src/ppo_progress.py --dir logs/otro_combo
    python src/ppo_progress.py --desde 22:43       # solo la serie que empezó a esa hora

Compara la primera mitad de las filas de `metricas.csv` con la segunda (como las tiradas se
continúan unas de otras, las filas se acumulan) y mira los tiempos de vuelta de `episodios.csv`.
La recompensa no se usa: con la velocidad objetivo subiendo no es comparable entre tramos.
"""

from __future__ import annotations

import argparse
import csv
import os
from typing import List, Tuple

from ppo_defaults import GATE_FAIL_CTE_M

MIN_ROLLOUTS = 16            # menos filas que esto no permite comparar dos mitades
SPEED_GAIN_KMH = 1.0         # subida de velocidad media que cuenta como mejora
CTE_WORSE_M = 0.3            # empeoramiento de CTE medio que cuenta como degradación
CTE_LIMIT_M = GATE_FAIL_CTE_M   # CTE medio absoluto a partir del cual la conducción ya es mala
STUCK_LIMIT_PCT = 10.0       # % de episodios en stuck por encima del cual hay un problema
LAP_GAIN_S = 1.5             # mejora de tiempo de vuelta que cuenta

Report = List[Tuple[str, str, str]]


def _num(rows: list, key: str) -> List[float]:
    out = []
    for r in rows:
        try:
            out.append(float(r[key]))
        except (KeyError, ValueError, TypeError):
            pass
    return out


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def assess(metrics: list, episodes: list) -> Report:
    """Devuelve [(clave, estado, texto)]; estado: bien / igual / mal / pocos datos."""
    if len(metrics) < MIN_ROLLOUTS:
        return [("conclusion", "pocos datos",
                 f"Solo {len(metrics)} rollouts; hacen falta al menos {MIN_ROLLOUTS} para comparar.")]

    half = len(metrics) // 2
    first, second = metrics[:half], metrics[half:]
    report: Report = []

    v1, v2 = _mean(_num(first, "avg_speed_kmh")), _mean(_num(second, "avg_speed_kmh"))
    if v2 - v1 >= SPEED_GAIN_KMH:
        status = "bien"
    elif v1 - v2 >= SPEED_GAIN_KMH:
        status = "mal"
    else:
        status = "igual"
    report.append(("ritmo", status, f"velocidad media {v1:.1f} -> {v2:.1f} km/h"))

    c1, c2 = _mean(_num(first, "avg_cte")), _mean(_num(second, "avg_cte"))
    stuck_eps = [e for e in episodes if e.get("fin") == "stuck"]
    stuck_pct = 100.0 * len(stuck_eps) / len(episodes) if episodes else 0.0
    # un stuck aislado no es un patrón: hacen falta 2 episodios y >10 %, o stuck repetido en 3 rollouts
    stuck_rollouts = sum(1 for x in _num(second, "pct_stuck") if x > 0)
    if (c2 > CTE_LIMIT_M or c2 - c1 > CTE_WORSE_M
            or (len(stuck_eps) >= 2 and stuck_pct > STUCK_LIMIT_PCT) or stuck_rollouts >= 3):
        status = "mal"
    else:
        status = "bien"
    report.append(("estabilidad", status,
                   f"CTE medio {c1:.2f} -> {c2:.2f} m; {len(stuck_eps)} de {len(episodes)} episodios en stuck"))

    laps = [float(e["lap_time_s"]) for e in episodes if e.get("lap_time_s")]
    if len(laps) >= 3:
        lh = len(laps) // 2
        l1, l2 = _mean(laps[:lh]), _mean(laps[lh:])
        status = "bien" if l1 - l2 >= LAP_GAIN_S else ("mal" if l2 - l1 >= LAP_GAIN_S else "igual")
        report.append(("vueltas", status, f"tiempo de vuelta lanzada {l1:.1f} -> {l2:.1f} s ({len(laps)} vueltas)"))
    else:
        report.append(("vueltas", "pocos datos", f"{len(laps)} vueltas con tiempo (hacen falta 3)"))

    s1, s2 = _mean(_num(first, "std")), _mean(_num(second, "std"))
    report.append(("politica", "igual" if abs(s2 - s1) < 0.005 else "bien",
                   f"std {s1:.4f} -> {s2:.4f} (si no se mueve, la política apenas cambia)"))

    states = {r[0]: r[1] for r in report}
    if states["estabilidad"] == "mal" or states["ritmo"] == "mal" or states["vueltas"] == "mal":
        verdict, text = "mal", "Algo se degrada: para y revisa la consola antes de seguir."
    elif states["ritmo"] == "bien" or states["vueltas"] == "bien":
        verdict, text = "bien", "Va mejorando sin perder estabilidad: sigue."
    else:
        verdict, text = "igual", "Estable pero sin mejora todavía: dale más pasos o afloja el ancla (--bc-pull)."
    report.append(("conclusion", verdict, text))
    return report


def since(rows: list, hhmm: str) -> list:
    """Filas con timestamp (HH:MM:SS) >= hhmm; sirve para ignorar tiradas anteriores en el mismo fichero."""
    return [r for r in rows if r.get("timestamp", "") >= hhmm]


def _read(path: str) -> list:
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", default=os.path.join("logs", "formula_rookie__sugo"))
    p.add_argument("--desde", default="", metavar="HH:MM",
                   help="Solo filas desde esa hora (los ficheros acumulan tiradas; usa la hora de la primera de la serie)")
    args = p.parse_args()
    metrics = _read(os.path.join(args.dir, "metricas.csv"))
    episodes = _read(os.path.join(args.dir, "episodios.csv"))
    if args.desde:
        metrics, episodes = since(metrics, args.desde), since(episodes, args.desde)
    print(f"[Progreso] {len(metrics)} rollouts, {len(episodes)} episodios en {args.dir}")
    for key, status, text in assess(metrics, episodes):
        print(f"  {key:12s} [{status}] {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
