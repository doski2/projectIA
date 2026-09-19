"""Tests de learn_driver (carga de datos para fine-tune)."""

import json

from learn_driver import FINE_TUNE_MIN_QUALITY, _load_training_data
from obs_universal import OBS_SCHEMA, OBS_UNIVERSAL_DIM


def _write_sample(
    path,
    quality: float,
    learn_stage: str = "",
    speed_band_kmh: float = 0.0,
) -> None:
    row = {
        "obs_schema": OBS_SCHEMA,
        "obs": [0.0] * OBS_UNIVERSAL_DIM,
        "action": [0.1, 0.0, 0.0],
        "quality": quality,
        "confidence": 1.0,
        "teacher_reason": "hold",
    }
    if learn_stage:
        row["learn_stage"] = learn_stage
    if speed_band_kmh > 0:
        row["speed_band_kmh"] = speed_band_kmh
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def test_load_training_data_filters_low_quality(tmp_path):
    base = tmp_path / "base.jsonl"
    buffer = tmp_path / "buffer.jsonl"
    _write_sample(base, FINE_TUNE_MIN_QUALITY + 0.1)
    _write_sample(buffer, FINE_TUNE_MIN_QUALITY - 0.1)

    obs, _act, _rid, _meta = _load_training_data(str(buffer), str(base), "l1_linea", 20.0)
    assert len(obs) == 1


def test_load_training_data_filters_buffer_by_stage(tmp_path):
    base = tmp_path / "base.jsonl"
    buffer = tmp_path / "buffer.jsonl"
    _write_sample(base, FINE_TUNE_MIN_QUALITY + 0.1)
    _write_sample(buffer, FINE_TUNE_MIN_QUALITY + 0.1, learn_stage="l1_linea", speed_band_kmh=30.0)
    with buffer.open("a", encoding="utf-8") as f:
        row = {
            "obs_schema": OBS_SCHEMA,
            "obs": [0.0] * OBS_UNIVERSAL_DIM,
            "action": [0.2, 0.0, 0.0],
            "quality": FINE_TUNE_MIN_QUALITY + 0.1,
            "confidence": 1.0,
            "teacher_reason": "hold",
            "learn_stage": "l3_frenar",
            "speed_band_kmh": 30.0,
        }
        f.write(json.dumps(row) + "\n")

    obs, _act, _rid, _meta = _load_training_data(str(buffer), str(base), "l3_frenar", 30.0)
    assert len(obs) == 2  # base + una fila l3 en buffer (l1 excluida)


def test_load_training_data_filters_buffer_by_speed_band(tmp_path):
    base = tmp_path / "base.jsonl"
    buffer = tmp_path / "buffer.jsonl"
    _write_sample(base, FINE_TUNE_MIN_QUALITY + 0.1)
    _write_sample(buffer, FINE_TUNE_MIN_QUALITY + 0.1, learn_stage="l1_linea", speed_band_kmh=20.0)
    with buffer.open("a", encoding="utf-8") as f:
        row = {
            "obs_schema": OBS_SCHEMA,
            "obs": [0.0] * OBS_UNIVERSAL_DIM,
            "action": [0.2, 0.0, 0.0],
            "quality": FINE_TUNE_MIN_QUALITY + 0.1,
            "confidence": 1.0,
            "teacher_reason": "hold",
            "learn_stage": "l1_linea",
            "speed_band_kmh": 30.0,
        }
        f.write(json.dumps(row) + "\n")

    obs, _act, _rid, _meta = _load_training_data(str(buffer), str(base), "l1_linea", 20.0)
    assert len(obs) == 2  # base + solo banda 20
