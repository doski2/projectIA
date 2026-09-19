"""Tests para guardia de transición de vuelta (meta / fine-tune BC)."""

from lap_transition import LapTransitionGuard


def test_guard_triggers_on_lap_increment():
    guard = LapTransitionGuard(track_length=3500.0, settle_frames=5)
    guard.reset(0, 3400.0)
    assert not guard.on_frame(0, 3450.0)
    assert guard.on_frame(1, 10.0)
    assert guard.active


def test_guard_triggers_on_distance_wrap():
    guard = LapTransitionGuard(track_length=3500.0, settle_frames=3)
    guard.reset(2, 3400.0)
    assert not guard.on_frame(2, 3450.0)
    assert guard.on_frame(2, 20.0)
    assert guard.active


def test_guard_settle_applies_brake_and_skips_bc():
    guard = LapTransitionGuard(settle_frames=2)
    guard.trigger_settle()
    guard.on_frame(1, 50.0)
    settle = guard.apply((0.8, 0.0, 0.1), (0.9, 0.0, -0.2))
    assert settle.active
    assert settle.skip_bc
    assert settle.throttle == 0.0
    assert settle.brake >= 0.55
    assert settle.steering == 0.1


def test_on_frame_triggers_settle_on_lap_change_without_extra_trigger():
    guard = LapTransitionGuard(settle_frames=5)
    guard.reset(0, 3400.0)
    assert not guard.on_frame(0, 3500.0)
    assert guard.on_frame(1, 5.0)
    assert guard.active


def test_fine_tuning_extends_settle():
    guard = LapTransitionGuard(settle_frames=2)
    guard.set_fine_tuning(True)
    assert guard.active
    settle = guard.apply((0.5, 0.0, 0.0), (1.0, 0.0, 0.0))
    assert settle.reason == "fine_tune"
