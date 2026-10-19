"""
bc_training.py
Entrenamiento y fine-tuning incremental de la política BC universal.
"""

from __future__ import annotations

import copy
import os
from typing import Dict, Optional

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from obs_universal import OBS_SCHEMA, OBS_UNIVERSAL_DIM
from teacher_intents import NUM_REASONS
from universal_policy import UniversalPolicy, load_universal_policy, save_universal_policy


def _train_loop(
    model: UniversalPolicy,
    obs_array: np.ndarray,
    act_array: np.ndarray,
    reason_ids: np.ndarray,
    epochs: int,
    batch_size: int,
    lr: float,
    reason_loss_weight: float,
    patience: int,
    log_prefix: str = "Universal BC",
) -> float:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)

    reason_onehot = np.zeros((len(obs_array), NUM_REASONS), dtype=np.float32)
    for i, rid in enumerate(reason_ids):
        reason_onehot[i, int(rid)] = 1.0

    obs_t = torch.tensor(obs_array, dtype=torch.float32)
    act_t = torch.tensor(act_array, dtype=torch.float32)
    rh_t = torch.tensor(reason_onehot, dtype=torch.float32)
    rid_t = torch.tensor(reason_ids, dtype=torch.long)

    loader = DataLoader(
        TensorDataset(obs_t, act_t, rh_t, rid_t),
        batch_size=min(batch_size, max(len(obs_array), 1)),
        shuffle=True,
    )

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    action_loss_fn = nn.MSELoss()
    reason_loss_fn = nn.CrossEntropyLoss()

    print(f"[{log_prefix}] Dispositivo: {device}")
    print(f"[{log_prefix}] Muestras: {len(obs_array)} | obs_dim={OBS_UNIVERSAL_DIM}")

    best_loss = float("inf")
    patience_counter = 0
    best_state: Optional[Dict[str, torch.Tensor]] = None

    for epoch in range(1, epochs + 1):
        model.train()
        total = 0.0
        for batch in loader:
            obs_b, act_b, rh_b, rid_b = (t.to(device) for t in batch)

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
            best_state = copy.deepcopy(model.state_dict())
            patience_counter = 0
        else:
            patience_counter += 1

        if epoch % 5 == 0 or epoch == 1 or epoch == epochs:
            print(f"  [{log_prefix}] Época {epoch:>3}/{epochs} | loss={avg:.6f} | mejor={best_loss:.6f}")

        if patience_counter >= patience:
            print(f"  [{log_prefix}] Early stopping en época {epoch}")
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    return best_loss


def train_universal(
    obs_array: np.ndarray,
    act_array: np.ndarray,
    reason_ids: np.ndarray,
    output_path: str,
    epochs: int = 100,
    batch_size: int = 256,
    lr: float = 1e-3,
    reason_loss_weight: float = 0.25,
    patience: int = 15,
) -> UniversalPolicy:
    model = UniversalPolicy()
    best_loss = _train_loop(
        model, obs_array, act_array, reason_ids,
        epochs=epochs, batch_size=batch_size, lr=lr,
        reason_loss_weight=reason_loss_weight, patience=patience,
    )
    save_universal_policy(
        model,
        output_path,
        metadata={
            "obs_schema": OBS_SCHEMA,
            "obs_dim": OBS_UNIVERSAL_DIM,
            "num_reasons": NUM_REASONS,
            "best_loss": best_loss,
            "training": "full",
        },
    )
    print(f"\n[Universal BC] Modelo guardado: {output_path}")
    return model


def fine_tune_universal(
    model_path: str,
    obs_array: np.ndarray,
    act_array: np.ndarray,
    reason_ids: np.ndarray,
    output_path: Optional[str] = None,
    epochs: int = 8,
    batch_size: int = 256,
    lr: float = 5e-4,
    reason_loss_weight: float = 0.25,
    patience: int = 4,
    min_samples: int = 200,
) -> dict:
    """Fine-tune incremental (p. ej. tras cada vuelta). Crea modelo nuevo si no existe."""
    out = output_path or model_path
    n = len(obs_array)
    if n < min_samples:
        return {
            "trained": False,
            "reason": f"pocas muestras ({n} < {min_samples})",
            "samples": n,
        }

    if os.path.isfile(model_path):
        model = load_universal_policy(model_path)
        print(f"[Online BC] Fine-tune desde {model_path}")
    else:
        model = UniversalPolicy()
        print(f"[Online BC] Modelo nuevo (no existía {model_path})")

    best_loss = _train_loop(
        model, obs_array, act_array, reason_ids,
        epochs=epochs, batch_size=batch_size, lr=lr,
        reason_loss_weight=reason_loss_weight, patience=patience,
        log_prefix="Online BC",
    )

    save_universal_policy(
        model,
        out,
        metadata={
            "obs_schema": OBS_SCHEMA,
            "obs_dim": OBS_UNIVERSAL_DIM,
            "num_reasons": NUM_REASONS,
            "best_loss": best_loss,
            "training": "incremental",
            "samples": n,
        },
    )
    print(f"[Online BC] Modelo actualizado: {out}")
    return {
        "trained": True,
        "samples": n,
        "best_loss": best_loss,
        "model_path": out,
    }
