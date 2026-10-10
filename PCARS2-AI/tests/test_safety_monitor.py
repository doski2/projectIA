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
