"""Destilación del BC a un PPO de SB3 con la observación universal."""

import inspect
import math

import numpy as np
import torch
from stable_baselines3 import PPO

from environment import PCARS2Env
from obs_universal import OBS_UNIVERSAL_DIM
from ppo_anchor import HoldBrakeDuringUpdateCallback
from ppo_bootstrap import distill
from universal_policy import UniversalPolicy


def _data(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    obs = rng.uniform(-1, 1, size=(n, OBS_UNIVERSAL_DIM)).astype(np.float32)
    rid = rng.integers(0, 4, size=n).astype(np.int64)
    act = np.zeros((n, 3), dtype=np.float32)
    return obs, act, rid


def test_distill_imitates_the_bc_and_anchors_std(tmp_path):
    torch.manual_seed(0)
    bc = UniversalPolicy(hidden=[32])
    obs, act, rid = _data()
    out = str(tmp_path / "ppo_base")
    stats = distill(bc, obs, act, rid, out, epochs=40, batch_size=256, lr=3e-3)
    assert stats["val_mae_to_bc"] < 0.15
    loaded = PPO.load(out, device="cpu")
    assert loaded.observation_space.shape == (OBS_UNIVERSAL_DIM,)
    assert math.isclose(loaded.policy.log_std.exp().mean().item(), 0.1, rel_tol=1e-4)
    action, _ = loaded.predict(obs[0], deterministic=True)
    assert action.shape == (3,)


def test_env_accepts_steer_comp_and_can_hold_brake():
    assert "steer_comp" in inspect.signature(PCARS2Env.__init__).parameters
    env = object.__new__(PCARS2Env)
    calls = []
    env._controller = type("C", (), {"apply_action": lambda self, *a: calls.append(a)})()
    env.hold_brake()
    assert calls == [(0.0, 1.0, 0.0)]


def test_hold_brake_callback_fires_before_each_update():
    calls = []
    cb = HoldBrakeDuringUpdateCallback(lambda: calls.append(1))
    cb._on_rollout_end()
    cb._on_rollout_end()
    assert len(calls) == 2
