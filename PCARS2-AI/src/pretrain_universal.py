"""
pretrain_universal.py
Behavioral Cloning universal: obs agnóstico de pista + intención del teacher.

Uso:
    python pretrain_universal.py --dataset data/sugo_teacher.jsonl --output models/universal_bc.pt
    python pretrain_universal.py --dataset data/track1.jsonl --dataset data/track2.jsonl
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
import torch

from bc_training import train_universal
from dataset_recorder import load_universal_dataset, merge_datasets
from teacher_intents import normalize_reason


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PCARS2-AI — BC universal (obs + intención → acción)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset", "-d", action="append", required=True,
                        help="JSONL(s) con obs_schema=universal_v1. Repetible.")
    parser.add_argument("--output", "-o", default="models/universal_bc.pt")
    parser.add_argument("--epochs", "-e", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--reason-loss-weight", type=float, default=0.25,
                        help="Peso de la pérdida auxiliar de clasificación de intención.")
    parser.add_argument("--origin", default=None)
    parser.add_argument("--min-quality", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def expand_globs(paths: list) -> list:
    out = []
    for p in paths:
        matches = glob.glob(p)
        if matches:
            out.extend(matches)
        elif os.path.isfile(p):
            out.append(p)
    return sorted(set(out))


def main() -> None:
    args = parse_args()
    paths = expand_globs(args.dataset)
    if not paths:
        print("[Error] No se encontraron datasets.")
        sys.exit(1)

    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    if len(paths) == 1:
        obs, act, reason_ids, meta = load_universal_dataset(
            paths[0],
            origin=args.origin,
            min_quality=args.min_quality,
        )
    else:
        obs, act, reason_ids, meta = merge_datasets(
            paths,
            origin=args.origin,
            min_quality=args.min_quality,
        )

    if len(obs) == 0:
        print("[Error] Dataset universal vacío. Graba con: record.bat --universal")
        sys.exit(1)

    tracks = {m.get("track_name", "?") for m in meta}
    reasons = {normalize_reason(m.get("teacher_reason", "")) for m in meta}
    print(f"[Universal BC] Pistas: {', '.join(sorted(tracks))}")
    print(f"[Universal BC] Intenciones: {', '.join(sorted(reasons))}")

    train_universal(
        obs_array=obs,
        act_array=act,
        reason_ids=reason_ids,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        reason_loss_weight=args.reason_loss_weight,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
