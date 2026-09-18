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
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from dataset_recorder import load_universal_dataset, merge_datasets
from obs_universal import OBS_SCHEMA, OBS_UNIVERSAL_DIM
from teacher_intents import NUM_REASONS, normalize_reason
from universal_policy import UniversalPolicy, save_universal_policy


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


def train(
    obs_array: np.ndarray,
    act_array: np.ndarray,
    reason_ids: np.ndarray,
    epochs: int,
    batch_size: int,
    lr: float,
    reason_loss_weight: float,
    output_path: str,
) -> UniversalPolicy:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = UniversalPolicy().to(device)

    reason_onehot = np.zeros((len(obs_array), NUM_REASONS), dtype=np.float32)
    for i, rid in enumerate(reason_ids):
        reason_onehot[i, int(rid)] = 1.0

    obs_t = torch.tensor(obs_array, dtype=torch.float32)
    act_t = torch.tensor(act_array, dtype=torch.float32)
    rh_t = torch.tensor(reason_onehot, dtype=torch.float32)
    rid_t = torch.tensor(reason_ids, dtype=torch.long)

    loader = DataLoader(
        TensorDataset(obs_t, act_t, rh_t, rid_t),
        batch_size=batch_size,
        shuffle=True,
    )

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    action_loss_fn = nn.MSELoss()
    reason_loss_fn = nn.CrossEntropyLoss()

    print(f"[Universal BC] Dispositivo: {device}")
    print(f"[Universal BC] Muestras: {len(obs_array)} | obs_dim={OBS_UNIVERSAL_DIM} | reasons={NUM_REASONS}")

    best_loss = float("inf")
    patience = 15
    patience_counter = 0

    for epoch in range(1, epochs + 1):
        model.train()
        total = 0.0
        for obs_b, act_b, rh_b, rid_b in loader:
            obs_b = obs_b.to(device)
            act_b = act_b.to(device)
            rh_b = rh_b.to(device)
            rid_b = rid_b.to(device)

            pred_act = model(obs_b, rh_b)
            x = torch.cat([obs_b, rh_b], dim=-1)
            h = model.forward_features(x)
            pred_rid = model.reason_head(h)

            loss = action_loss_fn(pred_act, act_b) + reason_loss_weight * reason_loss_fn(pred_rid, rid_b)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total += loss.item()

        avg = total / max(len(loader), 1)
        if avg < best_loss:
            best_loss = avg
            patience_counter = 0
        else:
            patience_counter += 1

        if epoch % 10 == 0 or epoch == 1:
            print(f"  Época {epoch:>4}/{epochs} | loss={avg:.6f} | mejor={best_loss:.6f}")

        if patience_counter >= patience:
            print(f"  [Universal BC] Early stopping en época {epoch}")
            break

    save_universal_policy(
        model,
        output_path,
        metadata={
            "obs_schema": OBS_SCHEMA,
            "obs_dim": OBS_UNIVERSAL_DIM,
            "num_reasons": NUM_REASONS,
            "best_loss": best_loss,
        },
    )
    print(f"\n[Universal BC] Modelo guardado: {output_path}")
    return model


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

    train(
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
