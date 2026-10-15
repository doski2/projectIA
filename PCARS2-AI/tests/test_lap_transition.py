"""Tests para la parada de meta durante el fine-tune."""

from lap_transition import LapTransitionGuard


def test_guard_does_not_brake_on_lap_increment():
    guard = LapTransitionGuard(track_length=3500.0)
    guard.reset(0, 3400.0)
    assert not guard.on_frame(0, 3450.0)
    assert not guard.on_frame(1, 10.0)
    assert not guard.active


def test_fine_tuning_stops_the_car_in_first():
    guard = LapTransitionGuard()
    guard.set_fine_tuning(True)
    moving = guard.apply((0.5, 0.0, 0.25), (1.0, 0.0, -0.4), speed_ms=8.0, gear=2)
    assert moving.reason == "fine_tune"
    assert moving.throttle == 0.0
    assert moving.brake == LapTransitionGuard.HOLD_BRAKE
    assert moving.steering == 0.25
    held = guard.apply((0.5, 0.0, 0.1), (1.0, 0.0, 0.0), speed_ms=0.0, gear=1)
    assert held.reason == "fine_tune"
    assert held.brake == LapTransitionGuard.HOLD_BRAKE
    assert held.throttle == 0.0
    guard.set_fine_tuning(False)
    assert not guard.active


def test_fine_tuning_engages_first_when_stopped_out_of_gear():
    guard = LapTransitionGuard()
    guard.set_fine_tuning(True)
    settle = guard.apply((0.2, 0.0, 0.0), (0.9, 0.0, 0.2), speed_ms=0.1, gear=0)
    assert settle.reason == "fine_tune_gear"
    assert settle.throttle > 0.2
    assert settle.brake == 0.0


def test_gear_engage_does_not_flip_back_to_brake():
    guard = LapTransitionGuard()
    guard.set_fine_tuning(True)
    guard.apply((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), speed_ms=0.1, gear=0)
    crept = guard.apply((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), speed_ms=1.2, gear=0)
    assert crept.reason == "fine_tune_gear"
    assert crept.brake == 0.0
    held = guard.apply((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), speed_ms=0.0, gear=1)
    assert held.reason == "fine_tune"
    assert held.brake == LapTransitionGuard.HOLD_BRAKE
