"""Tests del currículo de aprendizaje online."""

from learning_curriculum import (
    evaluate_lap,
    evaluate_objectives,
    get_learn_stage,
    resolve_stage_speed,
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
