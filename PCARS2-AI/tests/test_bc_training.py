"""Tests de entrenamiento BC."""

import copy

import numpy as np
import torch

from bc_training import _train_loop, fine_tune_universal, train_universal
from obs_universal import OBS_UNIVERSAL_DIM
from universal_policy import UniversalPolicy


def test_train_universal_small(tmp_path):
    n = 300
    obs = np.random.randn(n, OBS_UNIVERSAL_DIM).astype(np.float32)
    act = np.random.uniform(-1, 1, (n, 3)).astype(np.float32)
    rid = np.zeros(n, dtype=np.int64)
    out = tmp_path / "model.pt"
    model = train_universal(obs, act, rid, str(out), epochs=3, batch_size=64, patience=2)
    assert out.is_file()
    assert model is not None


def test_train_loop_restores_best_weights():
    n = 64
    obs = np.random.randn(n, OBS_UNIVERSAL_DIM).astype(np.float32)
    act = np.random.uniform(-1, 1, (n, 3)).astype(np.float32)
    rid = np.zeros(n, dtype=np.int64)

    model = UniversalPolicy()
    before = copy.deepcopy(model.state_dict())
    _train_loop(
        model, obs, act, rid,
        epochs=6, batch_size=32, lr=1e-3,
        reason_loss_weight=0.25, patience=2,
        log_prefix="test",
    )
    after = model.state_dict()
    assert not all(torch.equal(before[k], after[k]) for k in before)


def test_fine_tune_skips_few_samples(tmp_path):
    obs = np.random.randn(50, OBS_UNIVERSAL_DIM).astype(np.float32)
    act = np.random.uniform(-1, 1, (50, 3)).astype(np.float32)
    rid = np.zeros(50, dtype=np.int64)
    out = tmp_path / "model.pt"
    result = fine_tune_universal(str(out), obs, act, rid, min_samples=200)
    assert result["trained"] is False
