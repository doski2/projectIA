"""Tests de tiempos de vuelta."""

from lap_tracker import LapTracker, compute_lap_times_from_ticks, format_lap_time, lap_time_stats


def test_format_lap_time():
    assert format_lap_time(65.5) == "1:05.500"
    assert format_lap_time(12.3) == "12.300s"


def test_lap_tracker_detects_lap():
    tr = LapTracker(start_lap=1)
    assert tr.on_frame(0.0, 1) is None
    assert tr.on_frame(10.0, 1) is None
    ev = tr.on_frame(120.5, 2)
    assert ev is not None
    assert ev["lap_time_s"] == 120.5
    assert len(tr.completed) == 1


def test_lap_time_stats_improving():
    events = [
        {"lap_time_s": 100.0},
        {"lap_time_s": 95.0},
        {"lap_time_s": 92.0},
    ]
    st = lap_time_stats(events)
    assert st["best_s"] == 92.0
    assert st["improving_vs_prev"] is True


def test_compute_lap_times_from_ticks():
    ticks = [{"lap": 1, "t_s": i * 0.1} for i in range(100)]
    events = compute_lap_times_from_ticks(ticks)
    assert len(events) == 1
    assert events[0]["lap_time_s"] == 9.9
