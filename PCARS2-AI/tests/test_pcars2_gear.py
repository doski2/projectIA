"""Tests de heurísticas de marcha UDP."""

import pytest

from pcars2_gear import (
    backward_allows_rb_shift,
    cap_bc_to_speed_target,
    needs_gear_engagement,
    should_downshift_toward_first,
    should_rb_to_first,
    choose_bc_drive_pedals,
    should_use_teacher_pedals,
)
from test_auto_shift import _telem


def test_should_rb_to_first_neutral():
    assert should_rb_to_first(_telem(gear=0, speed=1.0, rpm=800))


def test_top_gear_glitch_at_crawl_downshifts_not_rb():
    telem = _telem(gear=6, speed=1.0, rpm=900, num_gears=6)
    assert not should_rb_to_first(telem)
    assert should_downshift_toward_first(telem)


def test_second_gear_at_crawl_needs_lb_not_rb():
    telem = _telem(gear=2, speed=1.0, rpm=900)
    assert not should_rb_to_first(telem)
    assert should_downshift_toward_first(telem)
    assert needs_gear_engagement(telem)


def test_second_gear_stalled_high_rpm_still_downshifts():
    telem = _telem(gear=2, speed=0.2, rpm=6000)
    assert should_downshift_toward_first(telem)


def test_backward_in_first_does_not_allow_rb_shift():
    telem = _telem(gear=1, speed=2.0, local_vx=-2.0)
    assert not backward_allows_rb_shift(telem)


def test_backward_neutral_allows_rb_shift():
    telem = _telem(gear=0, speed=2.0, local_vx=-2.0)
    assert backward_allows_rb_shift(telem)


def test_choose_bc_drive_pedals_neutral_uses_teacher():
    telem = _telem(gear=0, speed=1.0)
    bc = (0.1, 0.0, 0.0)
    teacher = (0.45, 0.0, 0.1)
    ped, src, ovr = choose_bc_drive_pedals(bc, teacher, telem, False)
    assert ped == teacher
    assert src == "teacher:gear"
    assert not ovr


def test_should_use_teacher_pedals_on_neutral_not_only_safety():
    telem = _telem(gear=0, speed=2.0, rpm=2500)
    assert needs_gear_engagement(telem)
    assert should_use_teacher_pedals(telem, safety_override=False)
    assert not should_use_teacher_pedals(telem, safety_override=False, settling=True)


def test_speed_cap_cuts_throttle_above_target_and_keeps_steer():
    proposed = (0.8, 0.0, -0.35)
    ped, capped = cap_bc_to_speed_target(proposed, speed_ms=20 / 3.6, target_ms=20 / 3.6)
    assert not capped
    assert ped == proposed
    ped, capped = cap_bc_to_speed_target(proposed, speed_ms=30 / 3.6, target_ms=20 / 3.6)
    assert capped
    assert ped[0] == 0.0
    assert ped[1] > 0.4
    assert ped[2] == -0.35


def test_neutral_rolling_still_needs_teacher_engagement():
    telem = _telem(gear=0, speed=1.5, rpm=3000)
    assert should_rb_to_first(telem)
    assert needs_gear_engagement(telem)


def test_gear_zero_while_moving_is_udp_glitch():
    from pcars2_gear import is_udp_gear_glitch

    moving = _telem(gear=0, speed=9.0, rpm=2000)
    assert is_udp_gear_glitch(moving)
    assert not needs_gear_engagement(moving)
    assert not should_use_teacher_pedals(moving, False)


def test_gear_zero_slow_or_backward_is_not_glitch():
    from pcars2_gear import is_udp_gear_glitch

    assert not is_udp_gear_glitch(_telem(gear=0, speed=1.5))
    assert not is_udp_gear_glitch(_telem(gear=0, speed=5.0, local_vx=-5.0))
    assert needs_gear_engagement(_telem(gear=0, speed=1.5))


def test_auto_shifter_ignores_glitch_neutral_at_speed():
    from auto_shift import AutoShifter

    class Ctl:
        def __init__(self):
            self.pressed = []

        def press_button(self, button):
            self.pressed.append(button)

        def apply_action(self, throttle, brake, steering):
            pass

    shifter = AutoShifter(last_forward_gear=2, neutral_frames=50)
    ctl = Ctl()
    assert shifter.shift(ctl, _telem(gear=0, speed=9.0, rpm=2000), 0.4, 0.0) is None
    assert ctl.pressed == []


def test_damp_bc_steering_scales_inverse_with_speed():
    from pcars2_gear import damp_bc_steering

    assert damp_bc_steering((0.3, 0.0, 0.8), 10.0, 12.5) == (0.3, 0.0, 0.8)  # bajo la ref
    t, b, s = damp_bc_steering((0.3, 0.1, -0.8), 25.0, 12.5)
    assert (t, b) == (0.3, 0.1)
    assert s == pytest.approx(-0.4)


def test_damp_bc_steering_disabled_with_zero_ref():
    from pcars2_gear import damp_bc_steering

    assert damp_bc_steering((0.3, 0.0, 0.8), 30.0, 0.0) == (0.3, 0.0, 0.8)


def test_speed_cap_soft_has_no_brake_step_for_small_excess():
    proposed = (0.4, 0.0, 0.1)
    over = 20 / 3.6 + 0.6  # algo más de la gracia (0,4 m/s)
    hard, capped = cap_bc_to_speed_target(proposed, speed_ms=over, target_ms=20 / 3.6)
    soft, capped_soft = cap_bc_to_speed_target(proposed, speed_ms=over, target_ms=20 / 3.6, soft=True)
    assert capped and capped_soft
    assert hard[0] == 0.0 and hard[1] >= 0.25  # escalón de freno
    assert soft[0] == 0.0 and 0.0 < soft[1] < 0.1  # suelta el gas y frena apenas
    assert soft[2] == proposed[2]
    far, _ = cap_bc_to_speed_target(proposed, speed_ms=30 / 3.6, target_ms=20 / 3.6, soft=True)
    assert 0.3 < far[1] < 0.5  # 10 km/h de exceso: freno firme pero sin el escalón


def test_backward_uses_longitudinal_axis_not_lateral():
    """H13: el eje 0 de local_velocity es el lateral; marcha atrás real = eje 2 positivo."""
    from pcars2_gear import backward_speed_ms, is_driving_backward

    sliding = _telem(gear=1, speed=11.5)
    sliding.local_velocity = (-0.4, 0.0, -11.5)  # avanza a 41 km/h y se desliza hacia un lado
    assert not is_driving_backward(sliding)
    assert backward_speed_ms(sliding) == 0.0

    reversing = _telem(gear=0, speed=2.0)
    reversing.local_velocity = (0.0, 0.0, 2.0)
    assert is_driving_backward(reversing)
    assert backward_speed_ms(reversing) == 2.0
