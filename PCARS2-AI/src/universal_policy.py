"""
universal_policy.py
Red neuronal para BC universal: obs + intención → acción.

Incluye cabeza auxiliar para predecir intención desde obs (modo autónomo).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn

from obs_universal import OBS_UNIVERSAL_DIM
from teacher_intents import NUM_REASONS, build_conditioned_obs, encode_reason_id


class UniversalPolicy(nn.Module):
    def __init__(
        self,
        obs_dim: int = OBS_UNIVERSAL_DIM,
        num_reasons: int = NUM_REASONS,
        hidden: Optional[List[int]] = None,
    ):
        super().__init__()
        self.obs_dim = obs_dim
        self.num_reasons = num_reasons
        hidden = hidden or [256, 256, 128]
        in_dim = obs_dim + num_reasons

        layers: List[nn.Module] = []
        prev = in_dim
        for h in hidden:
            layers.extend([nn.Linear(prev, h), nn.ReLU()])
            prev = h
        self.trunk = nn.Sequential(*layers)
        self.action_head = nn.Linear(prev, 3)
        self.reason_head = nn.Linear(prev, num_reasons)

    def forward_features(self, x: torch.Tensor) -> torch.Tensor:
        return self.trunk(x)

    def forward(self, obs: torch.Tensor, reason_onehot: torch.Tensor) -> torch.Tensor:
        x = torch.cat([obs, reason_onehot], dim=-1)
        h = self.forward_features(x)
        return self.action_head(h)

    def predict_reason_logits(self, obs: torch.Tensor) -> torch.Tensor:
        """Predice intención solo desde obs (entrada con reason=unknown)."""
        unknown = torch.zeros(obs.shape[0], self.num_reasons, device=obs.device)
        unknown[:, 0] = 1.0
        x = torch.cat([obs, unknown], dim=-1)
        h = self.forward_features(x)
        return self.reason_head(h)

    def predict(
        self,
        obs: np.ndarray,
        reason: Optional[str] = None,
        use_predicted_reason: bool = False,
    ) -> Tuple[np.ndarray, int]:
        """
        Inferencia numpy. Devuelve (acción [-1,1], reason_id).
        """
        self.eval()
        with torch.no_grad():
            obs_t = torch.tensor(obs, dtype=torch.float32).unsqueeze(0)
            if use_predicted_reason or reason is None:
                logits = self.predict_reason_logits(obs_t)
                rid = int(torch.argmax(logits, dim=-1).item())
                onehot = torch.zeros(1, self.num_reasons)
                onehot[0, rid] = 1.0
            else:
                rid = encode_reason_id(reason)
                onehot = torch.zeros(1, self.num_reasons)
                onehot[0, rid] = 1.0
            action = self.forward(obs_t, onehot).squeeze(0).cpu().numpy()
        return action.astype(np.float32), rid


def save_universal_policy(
    model: UniversalPolicy,
    path: str,
    metadata: Optional[dict] = None,
) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "state_dict": model.state_dict(),
        "obs_dim": model.obs_dim,
        "num_reasons": model.num_reasons,
        "metadata": metadata or {},
    }
    torch.save(payload, str(out))


def load_universal_policy(path: str, device: str = "cpu") -> UniversalPolicy:
    payload = torch.load(path, map_location=device, weights_only=False)
    model = UniversalPolicy(
        obs_dim=payload.get("obs_dim", OBS_UNIVERSAL_DIM),
        num_reasons=payload.get("num_reasons", NUM_REASONS),
    )
    model.load_state_dict(payload["state_dict"])
    model.to(device)
    model.eval()
    return model
