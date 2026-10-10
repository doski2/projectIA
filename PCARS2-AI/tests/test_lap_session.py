"""Tests de cierre de vuelta compartido."""

from lap_session import (
    LapCompleteResult,
    LapCompletionTracker,
    completed_lap_ticks,
    driving_ticks_for_lap_eval,
    driving_ticks_for_session_eval,
    evaluate_lap_for_phase,
    lap_rollover_detected,
    lap_summary_row_from_result,
    lap_tick_safety_flags,
    make_lap_buffer_tick,
    print_session_lap_board,
    process_lap_rollover,
    try_complete_lap,
)


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


class _FakeSessionRec:
    def __init__(self):
        self.events = []

    def record_event(self, event: dict) -> None:
        self.events.append(event)


def test_completed_lap_excludes_new_lap_tick():
    buf = [_tick(0), _tick(10), _tick(20), _tick(30)]  # último = vuelta nueva
    completed = completed_lap_ticks(buf)
    assert len(completed) == 3
    assert completed[-1]["t_s"] == 20


def test_tracker_detects_lap_increment():
    tracker = LapCompletionTracker()
    tracker.reset(1, 3400.0)
    assert not tracker.on_frame(1, 3450.0)
    assert tracker.on_frame(2, 10.0)
    assert tracker.laps_done == 1


def test_tracker_detects_distance_wrap_without_lap_increment():
    tracker = LapCompletionTracker()
    tracker.reset(2, 3400.0)
    assert not tracker.on_frame(2, 3450.0)
    assert tracker.on_frame(2, 20.0)
    assert tracker.laps_done == 1


def test_try_complete_lap_timing():
    buf = [_tick(i * 10.0) for i in range(12)]
    result = try_complete_lap(buf, laps_done=1, stage_id="l1_linea")
    assert result.laps_done == 1
    assert result.lap_time_s == 100.0


def test_l2_requires_speed():
    slow = [_tick(i * 10.0, speed=12.0) for i in range(12)]
    ev = try_complete_lap(slow, laps_done=1, stage_id="l2_velocidad")
    assert ev.clean is False


def test_teaching_f1_phase():
    buf = [_tick(i * 10.0) for i in range(12)]
    ev = try_complete_lap(buf, laps_done=1, stage_id="f1_linea")
    assert ev.clean is True


def test_imitation_phase_uses_imitation_criteria():
    buf = [_tick(i * 10.0) for i in range(4)]
    ev = evaluate_lap_for_phase(buf[:-1], "imit_bc_drive")
    assert ev["clean"] is True
    f4 = evaluate_lap_for_phase(buf[:-1], "f4_combinado")
    assert f4["clean"] is False


def test_tracker_dedupes_wrap_then_lap_increment():
    """UDP a veces manda wrap de distancia y después incremento de lap en la misma meta."""
    tracker = LapCompletionTracker()
    tracker.reset(2, 3400.0)
    assert tracker.on_frame(2, 20.0)
    assert tracker.laps_done == 1
    assert not tracker.on_frame(3, 50.0)
    assert tracker.laps_done == 1


def test_process_lap_rollover_on_distance_wrap():
    tracker = LapCompletionTracker()
    tracker.reset(3, 3300.0)
    buf = [_tick(i * 1.0) for i in range(15)]
    rec = _FakeSessionRec()
    result = process_lap_rollover(
        buf, 3, 15.0, tracker, "l1_linea", rec,
    )
    assert result is not None
    assert result.laps_done == 1
    assert len(rec.events) == 1
    assert rec.events[0]["type"] == "lap"


def test_lap_event_includes_failure_summary():
    from lap_session import LapCompleteResult, lap_event_from_result

    result = LapCompleteResult(
        laps_done=1,
        lap_eval={
            "clean": False,
            "avg_cte": 5.1,
            "pct_override": 18.0,
            "pct_off_track": 0.0,
            "pct_stuck": 0.0,
            "summary": "revisar: CTE 5.1m, overrides 18%",
        },
        lap_time_s=90.0,
        lap_overrides=42,
    )
    ev = lap_event_from_result(result, stage_id="l1_linea", speed_band_kmh=20.0)
    assert ev["clean"] is False
    assert "overrides" in ev["summary"]
    assert ev["pct_override"] == 18.0


def test_lap_tick_safety_flags_clear_when_settling():
    from safety_monitor import SafetyStatus

    status = SafetyStatus()
    status.reason = "stuck"
    status.stuck_steps = 99
    flags = lap_tick_safety_flags(status, 3.0, settling=True)
    assert flags.off_track is False and flags.stuck is False


def test_lap_rollover_detected_same_completed_lap_num():
    assert lap_rollover_detected(2, 3400.0, 2, 20.0) == (True, 2)
    assert lap_rollover_detected(2, 20.0, 3, 50.0) == (True, 2)


def test_driving_ticks_for_lap_eval_excludes_settling():
    ticks = [
        make_lap_buffer_tick(0, 40.0, 2.0, False, False, False, "maintain_speed"),
        make_lap_buffer_tick(1, 0.0, 2.0, False, False, False, "maintain_speed", settling=True),
        make_lap_buffer_tick(2, 38.0, 2.0, False, False, False, "maintain_speed"),
    ]
    driving = driving_ticks_for_lap_eval(ticks)
    assert len(driving) == 2
    assert driving[0]["speed_kmh"] == 40.0


def test_try_complete_lap_ignores_settling_for_l2_speed():
    buf = []
    for i in range(50):
        buf.append(make_lap_buffer_tick(
            float(i), 38.0, 2.0, False, False, False, "maintain_speed",
        ))
    for i in range(50, 70):
        buf.append(make_lap_buffer_tick(
            float(i), 0.0, 2.0, False, False, False, "maintain_speed", settling=True,
        ))
    buf.append(make_lap_buffer_tick(70.0, 38.0, 2.0, False, False, False, "maintain_speed"))
    result = try_complete_lap(buf, 1, "l2_velocidad", speed_band_kmh=40.0)
    assert result.lap_eval["avg_speed_kmh"] == 38.0
    assert result.clean is True


def test_driving_ticks_for_session_eval_excludes_settle():
    ticks = [
        {"drive_source": "bc", "stuck": False},
        {"drive_source": "settle:finish_line", "stuck": True},
        {"drive_source": "settle:fine_tune", "stuck": True},
        {"drive_source": "teacher", "stuck": False},
    ]
    driving = driving_ticks_for_session_eval(ticks)
    assert len(driving) == 2
    assert all(not t.get("stuck") for t in driving)


def test_lap_summary_row_and_board(capsys):
    result = LapCompleteResult(
        laps_done=2,
        lap_eval={
            "clean": False,
            "avg_cte": 2.2,
            "pct_override": 63.2,
            "pct_off_track": 32.8,
            "pct_stuck": 30.2,
            "summary": "revisar: overrides",
        },
        lap_time_s=1487.771,
        lap_overrides=52040,
    )
    row = lap_summary_row_from_result(result, clean_streak=0)
    assert row["n"] == 2
    assert row["pct_override"] == 63.2
    print_session_lap_board([row])
    out = capsys.readouterr().out
    assert "ovr%" in out
    assert "63.2" in out
    assert "24:" in out or "1487" in row["time"]


def test_driving_ticks_for_lap_eval_also_filters_drive_source():
    ticks = [
        make_lap_buffer_tick(0, 40.0, 2.0, False, False, False, "maintain_speed"),
        {"t_s": 1, "speed_kmh": 0.0, "drive_source": "settle:fine_tune"},
        make_lap_buffer_tick(2, 38.0, 2.0, False, False, False, "maintain_speed"),
    ]
    assert len(driving_ticks_for_lap_eval(ticks)) == 2
