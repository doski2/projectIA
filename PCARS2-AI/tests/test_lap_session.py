"""Tests de cierre de vuelta compartido."""

from lap_session import completed_lap_ticks, evaluate_lap_for_phase, try_complete_lap


def _tick(t_s, lap_reason="maintain_speed", override=False, speed=20.0):
    return {
        "t_s": t_s,
        "speed_kmh": speed,
        "cte": 2.0,
        "safety_override": override,
        "off_track": False,
        "stuck": False,
        "teacher_reason": lap_reason,
    }


def test_completed_lap_excludes_new_lap_tick():
    buf = [_tick(0), _tick(10), _tick(20), _tick(30)]  # último = vuelta nueva
    completed = completed_lap_ticks(buf)
    assert len(completed) == 3
    assert completed[-1]["t_s"] == 20


def test_try_complete_lap_timing():
    buf = [_tick(i * 10.0) for i in range(4)]
    # laps_done=0, current_lap=2 → start_lap=1 → completed 3 ticks
    result = try_complete_lap(buf, current_lap=2, start_lap=1, laps_done=0, stage_id="l1_linea")
    assert result is not None
    assert result.laps_done == 1
    assert result.lap_time_s == 20.0


def test_l2_requires_speed():
    slow = [_tick(i * 10.0, speed=12.0) for i in range(4)]
    ev = try_complete_lap(slow, current_lap=2, start_lap=1, laps_done=0, stage_id="l2_velocidad")
    assert ev is not None
    assert ev.clean is False


def test_teaching_f1_phase():
    buf = [_tick(i * 10.0) for i in range(4)]
    ev = try_complete_lap(buf, current_lap=2, start_lap=1, laps_done=0, stage_id="f1_linea")
    assert ev is not None
    assert ev.clean is True


def test_imitation_phase_uses_imitation_criteria():
    buf = [_tick(i * 10.0) for i in range(4)]
    ev = evaluate_lap_for_phase(buf[:-1], "imit_bc_drive")
    assert ev["clean"] is True
    f4 = evaluate_lap_for_phase(buf[:-1], "f4_combinado")
    assert f4["clean"] is False
