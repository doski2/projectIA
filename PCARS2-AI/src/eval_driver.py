"""
eval_driver.py
Evaluación offline de modelos BC: MAE steering/throttle/brake y métricas de calidad.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np

from controller import decode_action
from dataset_recorder import load_dataset
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PCARS2-AI — Evaluación BC offline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset", "-d", required=True, help="JSONL de demostraciones")
    parser.add_argument("--model", "-m", required=True, help="Ruta al modelo BC (sin .zip)")
    parser.add_argument("--origin", default=None, help="Filtrar por origen (TEACHER/DEMO/MIXED)")
    parser.add_argument("--min-quality", type=float, default=0.5)
    parser.add_argument("--min-confidence", type=float, default=0.5)
    return parser.parse_args()


def load_policy(model_path: str):
    from stable_baselines3 import PPO

    path = model_path if model_path.endswith(".zip") else f"{model_path}.zip"
    if not os.path.isfile(path):
        print(f"[Error] Modelo no encontrado: {path}")
        sys.exit(1)
    return PPO.load(path, device="cpu")


def evaluate(
    obs_array: np.ndarray,
    act_array: np.ndarray,
    meta: list,
    model_path: str,
) -> dict:
    policy = load_policy(model_path)
    preds = []
    for obs in obs_array:
        action, _ = policy.predict(obs, deterministic=True)
        preds.append(action)
    preds = np.array(preds, dtype=np.float32)

    pred_phys = np.array([decode_action(a) for a in preds])
    true_phys = np.array([decode_action(a) for a in act_array])

    mae_steer = float(np.mean(np.abs(pred_phys[:, 2] - true_phys[:, 2])))
    mae_thr = float(np.mean(np.abs(pred_phys[:, 0] - true_phys[:, 0])))
    mae_brk = float(np.mean(np.abs(pred_phys[:, 1] - true_phys[:, 1])))

    cte_vals = [m.get("cte", 0.0) for m in meta]
    avg_cte = float(np.mean(cte_vals)) if cte_vals else 0.0

    return {
        "samples": len(obs_array),
        "mae_steering": mae_steer,
        "mae_throttle": mae_thr,
        "mae_brake": mae_brk,
        "avg_cte_dataset": avg_cte,
        "pass_steer": mae_steer < 0.15,
        "pass_pedals": mae_thr < 0.20 and mae_brk < 0.20,
    }


def print_report(metrics: dict) -> None:
    print("\n=== Evaluación BC offline ===")
    print(f"  Muestras:        {metrics['samples']}")
    print(f"  MAE steering:    {metrics['mae_steering']:.4f}  {'OK' if metrics['pass_steer'] else 'FAIL'}")
    print(f"  MAE throttle:    {metrics['mae_throttle']:.4f}")
    print(f"  MAE brake:       {metrics['mae_brake']:.4f}  {'OK' if metrics['pass_pedals'] else 'FAIL'}")
    print(f"  CTE medio data:  {metrics['avg_cte_dataset']:.2f} m")
    ok = metrics["pass_steer"] and metrics["pass_pedals"]
    print(f"\n  Resultado: {'APTO para BC_DRIVE' if ok else 'Necesita más entrenamiento/datos'}")


def main() -> None:
    args = parse_args()
    obs, act, meta = load_dataset(
        args.dataset,
        origin=args.origin,
        min_quality=args.min_quality,
        min_confidence=args.min_confidence,
    )
    if len(obs) == 0:
        print("[Error] Dataset vacío tras filtros.")
        sys.exit(1)

    metrics = evaluate(obs, act, meta, args.model)
    print_report(metrics)


if __name__ == "__main__":
    main()
