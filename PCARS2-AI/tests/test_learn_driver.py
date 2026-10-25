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


def test_load_training_data_filters_buffer_by_track(tmp_path):
    base = tmp_path / "base.jsonl"
    buffer = tmp_path / "buffer.jsonl"
    _write_sample(base, FINE_TUNE_MIN_QUALITY + 0.1)
    rows = []
    for track in ("SUGO_GP", "SPA"):
        rows.append(json.dumps({
            "obs_schema": OBS_SCHEMA,
            "obs": [0.0] * OBS_UNIVERSAL_DIM,
            "action": [0.2, 0.0, 0.0],
            "quality": FINE_TUNE_MIN_QUALITY + 0.1,
            "confidence": 1.0,
            "teacher_reason": "hold",
            "learn_stage": "l1_linea",
            "speed_band_kmh": 20.0,
            "track_name": track,
        }))
    buffer.write_text("\n".join(rows) + "\n", encoding="utf-8")

    obs, *_ = _load_training_data(str(buffer), str(base), "l1_linea", 20.0, "SPA")
    assert len(obs) == 2  # base + solo la fila SPA
    obs, *_ = _load_training_data(str(buffer), str(base), "l1_linea", 20.0)
    assert len(obs) == 3  # sin pista: no filtra


def test_load_training_data_adds_curated_for_the_current_stage_and_band(tmp_path):
    from curate_dataset import curate

    base = tmp_path / "base.jsonl"
    raw = tmp_path / "raw.jsonl"
    curated = tmp_path / "curated.npz"
    _write_sample(base, 1.0)
    rows = []
    for stage, band, speed in (("l7_banda", 55.0, 0.2), ("l7_banda", 20.0, 0.4), ("l1_linea", 55.0, 0.6)):
        obs = [0.0] * OBS_UNIVERSAL_DIM
        obs[0] = speed
        rows.append({
            "obs_schema": OBS_SCHEMA, "obs": obs, "action": [0.1, 0.0, 0.0], "quality": 1.0,
            "teacher_reason": "hold", "reason_id": 1, "track_name": "SUGO_GP",
            "learn_stage": stage, "speed_band_kmh": band,
        })
    raw.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    curate(str(raw), str(curated), maintain_cap=1.0)

    obs, _act, _rid, _meta = _load_training_data(
        str(tmp_path / "nuevo.jsonl"), str(base), "l7_banda", 55.0, "SUGO_GP", str(curated),
    )
    assert len(obs) == 2          # base + la fila curada de l7_banda/55
