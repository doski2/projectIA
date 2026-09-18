"""
eval_universal.py
Evaluación offline del modelo BC universal (acción + intención).
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import torch

from controller import decode_action
from dataset_recorder import load_universal_dataset
from universal_policy import load_universal_policy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluación BC universal offline")
    parser.add_argument("--dataset", "-d", required=True)
    parser.add_argument("--model", "-m", required=True)
    parser.add_argument("--origin", default=None)
    parser.add_argument("--min-quality", type=float, default=0.5)
    return parser.parse_args()


def evaluate(obs, act, reason_ids, model_path: str) -> dict:
    model = load_universal_policy(model_path)
    device = next(model.parameters()).device

    preds = []
    pred_reasons = []
    for i, o in enumerate(obs):
        rid = int(reason_ids[i])
        onehot = torch.zeros(1, model.num_reasons, device=device)
        onehot[0, rid] = 1.0
        obs_t = torch.tensor(o, dtype=torch.float32, device=device).unsqueeze(0)
        with torch.no_grad():
            pred = model(obs_t, onehot).squeeze(0).cpu().numpy()
            logits = model.predict_reason_logits(obs_t)
            pr = int(torch.argmax(logits, dim=-1).item())
        preds.append(pred)
        pred_reasons.append(pr)

    preds = np.array(preds, dtype=np.float32)
    pred_phys = np.array([decode_action(a) for a in preds])
    true_phys = np.array([decode_action(a) for a in act])

    mae_steer = float(np.mean(np.abs(pred_phys[:, 2] - true_phys[:, 2])))
    mae_thr = float(np.mean(np.abs(pred_phys[:, 0] - true_phys[:, 0])))
    mae_brk = float(np.mean(np.abs(pred_phys[:, 1] - true_phys[:, 1])))

    reason_acc = float(np.mean(np.array(pred_reasons) == reason_ids))

    return {
        "samples": len(obs),
        "mae_steering": mae_steer,
        "mae_throttle": mae_thr,
        "mae_brake": mae_brk,
        "reason_accuracy": reason_acc,
        "pass_steer": mae_steer < 0.15,
        "pass_pedals": mae_thr < 0.20 and mae_brk < 0.20,
        "pass_reason": reason_acc > 0.6,
    }


def main() -> None:
    args = parse_args()
    obs, act, reason_ids, meta = load_universal_dataset(
        args.dataset, origin=args.origin, min_quality=args.min_quality,
    )
    if len(obs) == 0:
        print("[Error] Dataset universal vacío.")
        sys.exit(1)

    tracks = {m.get("track_name", "?") for m in meta}
    metrics = evaluate(obs, act, reason_ids, args.model)

    print("\n=== Evaluación BC universal ===")
    print(f"  Pistas en dataset: {', '.join(sorted(tracks))}")
    print(f"  Muestras:          {metrics['samples']}")
    print(f"  MAE steering:      {metrics['mae_steering']:.4f}  {'OK' if metrics['pass_steer'] else 'FAIL'}")
    print(f"  MAE throttle:      {metrics['mae_throttle']:.4f}")
    print(f"  MAE brake:         {metrics['mae_brake']:.4f}  {'OK' if metrics['pass_pedals'] else 'FAIL'}")
    print(f"  Precisión intent:  {metrics['reason_accuracy']:.1%}  {'OK' if metrics['pass_reason'] else 'FAIL'}")

    ok = metrics["pass_steer"] and metrics["pass_pedals"] and metrics["pass_reason"]
    print(f"\n  Resultado: {'APTO para pista nueva' if ok else 'Necesita más datos/multi-pista'}")


if __name__ == "__main__":
    main()
