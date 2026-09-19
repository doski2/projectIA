"""Tests de persistencia de etapa de aprendizaje."""

from learn_progress import (
    load_learn_progress,
    read_saved_speed_band,
    read_saved_stage,
    save_learn_progress,
)


def test_save_and_read_stage(tmp_path, monkeypatch):
    path = tmp_path / "user_learn_settings.json"
    monkeypatch.setattr("learn_progress._PROGRESS_FILE", path)

    save_learn_progress("l3_frenar", reference="src/refs/sugo_ai.json")
    assert read_saved_stage() == "l3_frenar"
    data = load_learn_progress()
    assert data["reference"] == "src/refs/sugo_ai.json"


def test_read_saved_stage_default_when_missing(tmp_path, monkeypatch):
    path = tmp_path / "missing.json"
    monkeypatch.setattr("learn_progress._PROGRESS_FILE", path)
    assert read_saved_stage("l1_linea") == "l1_linea"


def test_save_and_read_speed_band(tmp_path, monkeypatch):
    path = tmp_path / "user_learn_settings.json"
    monkeypatch.setattr("learn_progress._PROGRESS_FILE", path)

    save_learn_progress("l2_velocidad", speed_band_kmh=30.0)
    assert read_saved_speed_band() == 30.0
    assert load_learn_progress()["speed_band_kmh"] == 30.0
