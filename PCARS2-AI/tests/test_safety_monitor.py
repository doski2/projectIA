"""Tests de safety_monitor helpers."""

from safety_monitor import SafetyStatus, session_tick_flags


def test_session_tick_flags_off_track_from_cte():
    status = SafetyStatus(active=False)
    off, stuck = session_tick_flags(status, cte=8.5)
    assert off is True
    assert stuck is False


def test_session_tick_flags_stuck_includes_no_progress():
    status = SafetyStatus(active=True, reason="no_progress")
    off, stuck = session_tick_flags(status, cte=2.0)
    assert off is False
    assert stuck is True
