"""
teacher_intents.py
Vocabulario de intenciones del teacher: cuándo, por qué y cómo actuar.

Usado para entrenar políticas universales (multi-pista) condicionadas por regla.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

# Reason estable en teacher_controller / session log / JSONL universal
SAFETY_REVERSE_REASON = "safety_reverse"
ENGAGE_FIRST_REASON = "engage_first"

# Catálogo estable de reglas → metadatos explicables
RULE_CATALOG: Dict[str, Dict[str, str]] = {
    "maintain_speed": {
        "when": "speed_near_target",
        "why": "stable_cruise",
        "how": "light_throttle",
    },
    "accel_straight": {
        "when": "speed_below_target",
        "why": "straight_low_curvature",
        "how": "progressive_throttle",
    },
    "accel_curve_limited": {
        "when": "speed_below_target",
        "why": "curve_ahead",
        "how": "limited_throttle",
    },
    "brake_overspeed": {
        "when": "speed_above_target",
        "why": "curve_or_overspeed",
        "how": "progressive_brake",
    },
    "recover_line": {
        "when": "high_cte",
        "why": "off_racing_line",
        "how": "brake_and_steer",
    },
    "edge_grass": {
        "when": "wheels_on_grass_margin",
        "why": "narrow_margin",
        "how": "hold_throttle_steer_to_line",
    },
    "wheelspin_reduce": {
        "when": "rear_wheelspin",
        "why": "traction_loss",
        "how": "reduce_throttle",
    },
    "engage_first": {
        "when": "neutral_or_invalid_gear",
        "why": "need_first_before_accel",
        "how": "throttle_and_rb",
    },
    "safety_stuck": {
        "when": "stuck",
        "why": "no_progress",
        "how": "brake_recover",
    },
    "safety_off_surface": {
        "when": "off_surface",
        "why": "terrain_off_track",
        "how": "brake_recover",
    },
    "safety_off_track": {
        "when": "off_track",
        "why": "high_cte",
        "how": "brake_recover",
    },
    "safety_wrong_way": {
        "when": "wrong_way",
        "why": "heading_reversed",
        "how": "brake_recover",
    },
    "safety_reverse": {
        "when": "reverse_gear",
        "why": "longitudinal_backward",
        "how": "slow_brake_steer_to_line",
    },
    "safety_no_progress": {
        "when": "no_progress",
        "why": "blocked",
        "how": "brake_recover",
    },
    "safety_pit_box": {
        "when": "pit_zone",
        "why": "wrong_place",
        "how": "brake_recover",
    },
    "safety_generic": {
        "when": "safety_trigger",
        "why": "recover",
        "how": "brake_recover",
    },
    "hybrid": {
        "when": "bc_teacher_blend",
        "why": "uncertainty",
        "how": "weighted_action",
    },
    "unknown": {
        "when": "unknown",
        "why": "unknown",
        "how": "unknown",
    },
}

# ID estable para one-hot / clasificador
REASON_TO_ID: Dict[str, int] = {
    "unknown": 0,
    "maintain_speed": 1,
    "accel_straight": 2,
    "accel_curve_limited": 3,
    "brake_overspeed": 4,
    "recover_line": 5,
    "wheelspin_reduce": 6,
    "safety_stuck": 7,
    "safety_off_track": 8,
    "safety_wrong_way": 9,
    "safety_no_progress": 10,
    "safety_pit_box": 11,
    "safety_generic": 12,
    "hybrid": 13,
    "safety_reverse": 14,
    "engage_first": 15,
}

ID_TO_REASON: Dict[int, str] = {v: k for k, v in REASON_TO_ID.items()}
NUM_REASONS: int = len(REASON_TO_ID)


def normalize_reason(raw: str) -> str:
    """Normaliza reason dinámico (p.ej. safety_stuck) al vocabulario estable."""
    if not raw:
        return "unknown"
    if raw == "cruise":
        return "maintain_speed"
    if raw == "edge_grass":
        # Mismo id que recover_line: no amplía NUM_REASONS del modelo BC.
        return "recover_line"
    if raw in ("off_surface", "safety_off_surface"):
        return "safety_off_track"
    if raw in REASON_TO_ID:
        return raw
    if raw.startswith("safety_"):
        suffix = raw[7:]
        key = f"safety_{suffix}"
        if key in REASON_TO_ID:
            return key
        return "safety_generic"
    return "unknown"


def rule_for_reason(reason: str) -> Dict[str, str]:
    """Devuelve metadatos when/why/how para una intención."""
    if reason == "edge_grass":
        return dict(RULE_CATALOG["edge_grass"])
    key = normalize_reason(reason)
    return dict(RULE_CATALOG.get(key, RULE_CATALOG["unknown"]))


def encode_reason_onehot(reason: str) -> np.ndarray:
    """One-hot de tamaño NUM_REASONS."""
    vec = np.zeros(NUM_REASONS, dtype=np.float32)
    idx = REASON_TO_ID.get(normalize_reason(reason), 0)
    vec[idx] = 1.0
    return vec


def encode_reason_id(reason: str) -> int:
    return REASON_TO_ID.get(normalize_reason(reason), 0)


def decode_reason_id(reason_id: int) -> str:
    return ID_TO_REASON.get(int(reason_id), "unknown")


def build_conditioned_obs(obs: np.ndarray, reason: str) -> np.ndarray:
    """Concatena obs universal + one-hot de intención."""
    return np.concatenate([obs.astype(np.float32), encode_reason_onehot(reason)])


def conditioned_obs_dim(universal_obs_dim: int) -> int:
    return universal_obs_dim + NUM_REASONS
