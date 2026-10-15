"""Tests de heurísticas de marcha UDP."""

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
