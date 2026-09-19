"""Tests de cierre de vuelta compartido."""

from lap_session import (
    LapCompletionTracker,
    completed_lap_ticks,
    evaluate_lap_for_phase,
    lap_rollover_detected,
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


def test_lap_rollover_detected_same_completed_lap_num():
    assert lap_rollover_detected(2, 3400.0, 2, 20.0) == (True, 2)
    assert lap_rollover_detected(2, 20.0, 3, 50.0) == (True, 2)
