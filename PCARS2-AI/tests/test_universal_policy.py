"""Tests de política universal."""

import numpy as np
import torch

from obs_universal import OBS_UNIVERSAL_DIM
from teacher_intents import NUM_REASONS
from universal_policy import UniversalPolicy, load_universal_policy, save_universal_policy


def test_forward_shape():
    model = UniversalPolicy()
    obs = torch.randn(4, OBS_UNIVERSAL_DIM)
    rh = torch.zeros(4, NUM_REASONS)
    rh[:, 1] = 1.0
    out = model(obs, rh)
    assert out.shape == (4, 3)


def test_predict_with_reason():
    model = UniversalPolicy()
    obs = np.zeros(OBS_UNIVERSAL_DIM, dtype=np.float32)
    action, rid = model.predict(obs, reason="accel_straight")
    assert action.shape == (3,)
    assert rid > 0


def test_save_load_roundtrip(tmp_path):
    model = UniversalPolicy()
    path = tmp_path / "test.pt"
    save_universal_policy(model, str(path), metadata={"test": True})
    loaded = load_universal_policy(str(path))
    assert loaded.obs_dim == OBS_UNIVERSAL_DIM
