"""Tests del currículo de aprendizaje online."""

from learning_curriculum import (
    DEFAULT_SPEED_BAND_KMH,
    evaluate_lap,
    evaluate_objectives,
    effective_min_avg_speed,
    get_learn_stage,
    resolve_learn_speed,
    resolve_stage_speed,
    try_advance_speed_band,
    try_advance_stage,
)


def _lap_tick(cte=2.0, override=False, reason="maintain_speed"):
    return {
        "cte": cte,
        "safety_override": override,
        "teacher_reason": reason,
        "stuck": False,
    }


def test_resolve_stage_speed_uses_stage_or_override():
    assert resolve_stage_speed("l1_linea", 0) == 15.0
    assert resolve_stage_speed("l1_linea", 22.0) == 22.0


def test_resolve_learn_speed_band_then_override():
    assert resolve_learn_speed("l1_linea", 30.0, 0) == 30.0
    assert resolve_learn_speed("l1_linea", 30.0, 25.0) == 25.0


def test_effective_min_avg_speed_scales_with_band():
    stage = get_learn_stage("l2_velocidad")
    assert effective_min_avg_speed(stage, 20.0) == 18.0
    assert effective_min_avg_speed(stage, 40.0) == 36.0


def test_advance_l5_to_l6():
    stage = get_learn_stage("l5_rapido")
    new_id, advanced, _ = try_advance_stage("l5_rapido", stage.clean_laps_required)
    assert advanced is True
    assert new_id == "l6_sostenido"


def test_advance_speed_band_after_l7():
    stage = get_learn_stage("l7_banda")
    new_band, advanced, new_stage, msg = try_advance_speed_band(
        DEFAULT_SPEED_BAND_KMH, "l7_banda", stage.clean_laps_required,
    )
    assert advanced is True
    assert new_band == 30.0
    assert new_stage == "l1_linea"
    assert "30" in msg


def test_clean_lap_l1():
    ticks = [_lap_tick() for _ in range(100)]
    ev = evaluate_lap(ticks, "l1_linea")
    assert ev["clean"] is True


def test_dirty_lap_high_cte():
    ticks = [_lap_tick(cte=8.0) for _ in range(50)]
    ev = evaluate_lap(ticks, "l1_linea")
    assert ev["clean"] is False


def test_advance_after_clean_streak():
    stage = get_learn_stage("l1_linea")
    new_id, advanced, _ = try_advance_stage("l1_linea", stage.clean_laps_required)
    assert advanced is True
    assert new_id == "l2_velocidad"


def test_no_advance_without_streak():
    _, advanced, msg = try_advance_stage("l1_linea", 0)
    assert advanced is False
    assert "0/" in msg


def test_objectives_l1():
    objs = evaluate_objectives(
        "l1_linea",
        {"avg_cte": 3.0, "pct_safety_override": 5.0, "avg_speed_kmh": 16.0, "pct_brake_reason": 10.0},
        [{"lap_time_s": 120.0}],
        clean_streak=2,
    )
    assert len(objs) == 3
    assert all(o["ok"] for o in objs)


def test_objectives_l2_speed_band_scales_target():
    objs = evaluate_objectives(
        "l2_velocidad",
        {"avg_cte": 3.0, "pct_safety_override": 5.0, "avg_speed_kmh": 27.0, "pct_brake_reason": 10.0},
        [{"lap_time_s": 120.0}],
        clean_streak=2,
        speed_band_kmh=30.0,
    )
    vel = next(o for o in objs if o["id"] == "velocidad")
    assert vel["threshold"] == "≥ 27.0km/h"
    assert vel["ok"] is True
