"""
obs_spaces.py
Espacios de observación de los dos esquemas y un entorno ficticio con ellos, compartidos por
environment.py, pretrain.py y ppo_bootstrap.py (antes cada uno tenía su copia).
"""

from __future__ import annotations

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from obs_builder import OBS_DIM
from obs_universal import OBS_SCHEMA, OBS_UNIVERSAL_DIM

LEGACY_OBS_SCHEMA = "legacy_19"


def observation_space_for(obs_schema: str) -> spaces.Box:
    """Espacio de observación según el esquema: `legacy_19` o `universal_v1` (CTE con signo)."""
    if obs_schema == OBS_SCHEMA:
        return spaces.Box(
            low=np.full(OBS_UNIVERSAL_DIM, -1.0, dtype=np.float32),
            high=np.ones(OBS_UNIVERSAL_DIM, dtype=np.float32),
            dtype=np.float32,
        )
    if obs_schema != LEGACY_OBS_SCHEMA:
        raise ValueError(f"obs_schema desconocido: {obs_schema!r}")
    low = np.array([
        0, 0, -1, -1, -1, -1, -1,   # 0-6  speed/cte/delta/slip/yaw/lat/long
        0, 0,                        # 7-8  rpm/gear
        -1, -1,                      # 9-10 heading_err/curvatura
        0, 0,  0,  0,               # 11-14 lookahead×2 + ref_thr/brk
        -1, -1,  0,                 # 15-17 wheelspin/lockup/throttle_cur
        0,                           # 18  progress
    ], dtype=np.float32)
    return spaces.Box(low=low, high=np.ones(OBS_DIM, dtype=np.float32), dtype=np.float32)


class DummyEnv(gym.Env):
    """Entorno ficticio con los espacios de PCARS2Env: para crear/cargar un PPO sin el juego."""

    def __init__(self, obs_schema: str = OBS_SCHEMA):
        self.observation_space = observation_space_for(obs_schema)
        self._dim = OBS_UNIVERSAL_DIM if obs_schema == OBS_SCHEMA else OBS_DIM
        self.action_space = spaces.Box(-1.0, 1.0, shape=(3,), dtype=np.float32)

    def _zeros(self) -> np.ndarray:
        return np.zeros(self._dim, dtype=np.float32)

    def reset(self, **kwargs):
        return self._zeros(), {}

    def step(self, action):
        return self._zeros(), 0.0, False, False, {}
