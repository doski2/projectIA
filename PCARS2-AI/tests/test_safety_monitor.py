# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
"""Tests de safety_monitor helpers."""

from safety_monitor import SafetyStatus, off_track_pct_breakdown, session_tick_flags


def test_session_tick_flags_off_track_from_cte():
    status = SafetyStatus(active=False)
    flags = session_tick_flags(status, cte=8.5)
    assert flags.off_track is True
    assert flags.off_track_cte is True
    assert flags.off_surface is False
    assert flags.stuck is False


def test_off_track_pct_breakdown_legacy_ticks():
    ticks = [
        {"off_track": True, "cte": 9.0, "teacher_reason": "recover_line"},
        {"off_surface": True, "off_track": True, "cte": 2.0, "teacher_reason": "safety_off_surface"},
    ]
    b = off_track_pct_breakdown(ticks)
    assert b["pct_off_surface"] == 50.0
    assert b["pct_off_track_cte"] == 50.0
    assert b["pct_off_track"] == 100.0


def test_session_tick_flags_stuck_includes_no_progress():
    status = SafetyStatus(active=True, reason="no_progress")
    flags = session_tick_flags(status, cte=2.0)
    assert flags.off_track is False
    assert flags.stuck is True


def _stopped_frames():
    from types import SimpleNamespace

    telem = SimpleNamespace(
        speed=0.0, position=(0.0, 0.0, 0.0), world_velocity=(0.0, 0.0, 0.0),
        orientation=(0.0, 0.0, 0.0), terrain=(0, 0, 0, 0),
    )
    timings = SimpleNamespace(lap_distance=11.0, current_lap=2)
    return telem, timings


def test_hold_keeps_deliberate_stop_from_counting_as_stuck():
    """Parada intencionada (fine-tune): ni stuck ni no_progress, antes ni después."""
    from types import SimpleNamespace
    from safety_monitor import SafetyMonitor

    ref = SimpleNamespace(
        track_length=3500.0,
        cross_track_error=lambda pos, d: 0.2,
        heading_error=lambda vel, d: 0.0,
        heading_at=lambda d: 0.0,
    )
    mon = SafetyMonitor(ref=ref, grace_steps=0, stuck_max_steps=5, no_progress_max_steps=5)
    telem, timings = _stopped_frames()
    for _ in range(50):
        status = mon.update(telem, timings)
        mon.hold(timings)
        assert not status.active
    # Al soltar el freno hay que volver a esperar el tiempo completo antes de intervenir.
    reasons = [mon.update(telem, timings).reason for _ in range(4)]
    assert reasons == ["", "", "", ""]
    assert mon.update(telem, timings).active
