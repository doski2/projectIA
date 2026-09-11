"""Tests para PCARS2-AI v2 (config + launcher)."""

import json
from pathlib import Path

import pytest

from v2.config import apply_mode_defaults, get_mode, TrainingSettings, TRAINING_MODES
from v2.launcher import build_argv, find_latest_checkpoint, project_root


def test_training_modes_include_basico():
    ids = {m.id for m in TRAINING_MODES}
    assert "basico" in ids
    assert "completo" in ids


def test_basico_mode_has_basics_flag():
    mode = get_mode("basico")
    assert "--basics" in mode.cli_flags
    assert mode.default_overrides["speed_target_kmh"] == 20.0


def test_apply_mode_defaults():
    s = TrainingSettings(mode_id="basico", speed_target_kmh=99, timesteps=1)
    apply_mode_defaults(s)
    assert s.speed_target_kmh == 20.0
    assert s.timesteps == 150_000


def test_build_argv_basico():
    s = TrainingSettings(
        mode_id="basico",
        reference="src/refs/sugo_ai.json",
        timesteps=100_000,
        speed_target_kmh=20,
        frame_skip=4,
        warmup_steps=30,
    )
    argv = build_argv(s)
    assert "--basics" in argv
    assert "--speed-target-kmh" in argv
    assert "20" in argv
    assert "--curriculum" not in argv


def test_build_argv_with_model():
    s = TrainingSettings(
        mode_id="basico",
        model_path="models/foo/pcars2_foo_1000_steps",
    )
    argv = build_argv(s)
    assert "--model" in argv
    assert "models/foo/pcars2_foo_1000_steps" in argv


def test_find_latest_checkpoint_missing_dir():
    assert find_latest_checkpoint("nonexistent_combo_xyz") is None


def test_find_latest_checkpoint_sorts_by_step_number(tmp_path, monkeypatch):
    model_dir = tmp_path / "models" / "formula_rookie__sugo"
    model_dir.mkdir(parents=True)
    (model_dir / "pcars2_formula_rookie__sugo_90000_steps.zip").write_bytes(b"x")
    (model_dir / "pcars2_formula_rookie__sugo_300000_steps.zip").write_bytes(b"x")

    monkeypatch.setattr(
        "v2.launcher.project_root",
        lambda: tmp_path,
    )
    result = find_latest_checkpoint("formula_rookie__sugo")
    assert result is not None
    assert result.endswith("pcars2_formula_rookie__sugo_300000_steps")
