"""Tests de la curva de respuesta del volante."""

import pytest

from steering_curve import applied_steering, compensate_steering


def test_compensation_is_the_inverse_of_the_measured_response():
    for desired in (-1.0, -0.6, -0.3, -0.1, 0.0, 0.05, 0.2, 0.45, 0.8, 1.0):
        assert applied_steering(compensate_steering(desired)) == pytest.approx(desired, abs=0.02)


def test_compensation_boosts_small_commands_and_keeps_sign():
    assert compensate_steering(0.2) > 0.2
    assert compensate_steering(-0.2) == pytest.approx(-compensate_steering(0.2))
    assert compensate_steering(0.0) == 0.0


def test_compensation_is_monotonic_and_bounded():
    prev = -1.0
    for i in range(-100, 101):
        c = compensate_steering(i / 100)
        assert -1.0 <= c <= 1.0
        assert c >= prev
        prev = c
    assert compensate_steering(2.0) == 1.0


def test_game_response_matches_measured_points():
    assert applied_steering(0.25) == pytest.approx(0.118, abs=0.02)
    assert applied_steering(0.625) == pytest.approx(0.618, abs=0.01)
