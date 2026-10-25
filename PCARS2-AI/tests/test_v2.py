"""Tests para PCARS2-AI v2 (config + launcher)."""



from learning_curriculum import LEARN_STAGES, SPEED_BANDS_KMH as CURR_SPEED_BANDS

from v2.config import apply_mode_defaults, get_mode, TrainingSettings, TRAINING_MODES
from v2.config import LEARN_STAGE_IDS, LearnSettings, SPEED_BANDS_KMH, TeachingSettings
from v2.launcher import (
    build_argv,
    build_learn_argv,
    build_teaching_argv,
    find_latest_checkpoint,
    load_learn_settings,
    save_learn_settings,
)


def test_learn_stage_ids_match_curriculum():
    assert LEARN_STAGE_IDS == list(LEARN_STAGES.keys())
    assert SPEED_BANDS_KMH == CURR_SPEED_BANDS


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


def test_build_argv_basico_fresh_explicit():
    s = TrainingSettings(
        mode_id="basico",
        reference="src/refs/sugo_ai.json",
        timesteps=100_000,
        speed_target_kmh=20,
        frame_skip=4,
        warmup_steps=30,
        fresh_start=True,
    )
    argv = build_argv(s)
    assert "--basics" in argv
    assert "--speed-target-kmh" in argv
    assert "20" in argv
    assert "--curriculum" not in argv
    assert "--fresh" in argv


def test_build_argv_without_model_and_no_fresh_auto_resumes():
    s = TrainingSettings(mode_id="basico", model_path="", fresh_start=False)
    argv = build_argv(s)
    assert "--fresh" not in argv
    assert "--model" not in argv


def test_build_argv_fresh_when_checked():
    s = TrainingSettings(mode_id="basico", model_path="", fresh_start=True)
    argv = build_argv(s)
    assert "--fresh" in argv
    assert "--model" not in argv


def test_build_argv_with_model_ignores_fresh():
    s = TrainingSettings(
        mode_id="basico",
        model_path="models/foo/pcars2_foo_1000_steps",
        fresh_start=True,
    )
    argv = build_argv(s)
    assert "--model" in argv
    assert "models/foo/pcars2_foo_1000_steps" in argv
    assert "--fresh" not in argv


def test_build_teaching_argv_record_uses_universal():
    s = TeachingSettings(
        mode_id="record",
        dataset_output="data/universal_teacher.jsonl",
    )
    argv = build_teaching_argv(s)
    assert "--universal" in argv
    assert "data/universal_teacher.jsonl" in argv


def test_save_and_load_learn_settings(tmp_path, monkeypatch):
    path = tmp_path / "learn.json"
    monkeypatch.setattr("learn_progress._PROGRESS_FILE", path)
    s = LearnSettings(stage_id="l4_combinado", reference="src/refs/sugo_ai.json", speed_target_kmh=0.0)
    save_learn_settings(s)
    loaded = load_learn_settings()
    assert loaded is not None
    assert loaded.stage_id == "l4_combinado"
    assert loaded.reference == "src/refs/sugo_ai.json"


def test_build_learn_argv_speed_override():
    s = LearnSettings(
        stage_id="l2_velocidad",
        speed_band_kmh=30.0,
        speed_target_kmh=18.0,
    )
    argv = build_learn_argv(s)
    assert "--speed-band" in argv
    assert "30" in argv
    assert "--speed-target" in argv
    assert "18.0" in argv


def test_build_learn_argv_includes_stage_and_universal_model():
    s = LearnSettings(
        reference="src/refs/sugo_ai.json",
        stage_id="l3_frenar",
        model_path="models/universal_bc.pt",
    )
    argv = build_learn_argv(s)
    assert "learn_driver.py" in " ".join(argv)
    assert "--stage" in argv
    assert "l3_frenar" in argv
    assert "--model" in argv
    assert "models/universal_bc.pt" in argv
    assert "--open-report" in argv


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


def test_speed_bands_reach_80_and_chain_to_the_end():
    from learning_curriculum import MAX_SPEED_BAND_KMH, next_speed_band

    assert CURR_SPEED_BANDS[-1] == MAX_SPEED_BAND_KMH == 80.0
    assert next_speed_band(50.0) == 55.0
    assert next_speed_band(55.0) == 60.0
    assert next_speed_band(60.0) == 70.0
    assert next_speed_band(70.0) == 80.0
    assert next_speed_band(80.0) is None
