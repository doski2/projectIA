"""Tests de auto_shift."""

from auto_shift import AutoShifter, auto_shift


class FakeController:
    def __init__(self):
        self.pressed: list[str] = []

    def press_button(self, button: str) -> None:
        self.pressed.append(button)

    def apply_action(self, throttle: float, brake: float, steering: float) -> None:
        pass


def _telem(gear=2, rpm=4000, max_rpm=8000, speed=5.0, num_gears=6, local_vx=None):
    from telemetry_udp import TelemetryFrame

    vx = local_vx if local_vx is not None else speed
    return TelemetryFrame(
        position=(0.0, 0.0, 0.0),
        orientation=(0.0, 0.0, 0.0),
        local_velocity=(0.0, 0.0, -vx),  # eje 2 = longitudinal, negativo al avanzar (H1)
        world_velocity=(speed, 0.0, 0.0),
        angular_velocity=(0.0, 0.0, 0.0),
        local_acceleration=(0.0, 0.0, 0.0),
        speed=speed,
        throttle=0,
        brake=0,
        steering=0,
        clutch=0,
        gear=gear,
        num_gears=num_gears,
        raw_throttle=0,
        raw_brake=0,
        raw_steering=0,
        tyre_temp=(80, 80, 80, 80),
        tyre_tread_temp=(80, 80, 80, 80),
        tyre_wear=(0, 0, 0, 0),
        tyre_rps=(5.0, 5.0, 5.0, 5.0),
        terrain=(0, 0, 0, 0),
        ride_height=(0.1, 0.1, 0.1, 0.1),
        suspension_travel=(0.05, 0.05, 0.05, 0.05),
        rpm=rpm,
        max_rpm=max_rpm,
        fuel_level=0.8,
        aero_damage=0,
        engine_damage=0,
        car_flags=0,
        brake_bias=50,
        viewed_participant_index=0,
        viewed_is_ai=False,
    )


def test_auto_shift_neutral_boosts_low_throttle_for_rb():
    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0)
    event = auto_shift(ctrl, _telem(gear=0, speed=2.0), 0.02, 0.0, shifter)
    assert event == "to_first"
    assert ctrl.pressed[-1] == "rb"


def test_auto_shift_neutral_to_first_at_any_speed():
    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0)
    for speed in (0.0, 3.0):
        event = auto_shift(ctrl, _telem(gear=0, speed=speed), 0.5, 0.0, shifter)
        assert event == "to_first"
        assert ctrl.pressed[-1] == "rb"


def test_neutral_rb_retry_is_slower_than_normal_cooldown():
    import time

    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.01, neutral_retry_s=0.6)
    telem = _telem(gear=0, speed=0.0)
    assert auto_shift(ctrl, telem, 0.5, 0.0, shifter) == "to_first"
    time.sleep(0.05)
    assert auto_shift(ctrl, telem, 0.5, 0.0, shifter) is None
    assert ctrl.pressed == ["rb"]


def test_auto_shift_cooldown_prevents_spam():
    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.2)
    telem = _telem(gear=0, speed=0.0)
    assert auto_shift(ctrl, telem, 0.5, 0.0, shifter) == "to_first"
    assert auto_shift(ctrl, telem, 0.5, 0.0, shifter) is None  # cooldown
    assert len(ctrl.pressed) == 1


def test_auto_shift_stalled_high_gear_downshifts_not_upshifts():
    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0)
    event = auto_shift(ctrl, _telem(gear=4, speed=0.0), 0.5, 0.0, shifter)
    assert event == "down_to_first"
    assert ctrl.pressed == ["lb"]


def test_auto_shift_upshift_only_below_teaching_max_gear():
    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0)
    assert auto_shift(ctrl, _telem(gear=2, rpm=7200), 0.8, 0.0, shifter) is None
    event = auto_shift(ctrl, _telem(gear=1, rpm=7200), 0.8, 0.0, shifter)
    assert event == "up"
    assert ctrl.pressed == ["rb"]


def test_auto_shift_second_gear_crawl_downshifts_to_first():
    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0)
    telem = _telem(gear=2, speed=1.0, rpm=900)
    event = auto_shift(ctrl, telem, 0.5, 0.0, shifter)
    assert event == "down_to_first"
    assert ctrl.pressed == ["lb"]


def test_auto_shift_downshift_on_brake():
    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0)
    event = auto_shift(ctrl, _telem(gear=3, rpm=2000), 0.0, 0.5, shifter)
    assert event == "down"
    assert ctrl.pressed == ["lb"]


def test_auto_shift_backward_in_forward_gear_does_not_upshift():
    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0)
    telem = _telem(gear=1, speed=2.0, local_vx=-2.0)
    assert auto_shift(ctrl, telem, 0.5, 0.0, shifter) is None
    assert ctrl.pressed == []


def test_auto_shift_backward_neutral_still_rb():
    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0)
    telem = _telem(gear=0, speed=2.0, local_vx=-2.0)
    event = auto_shift(ctrl, telem, 0.5, 0.0, shifter)
    assert event == "from_reverse"
    assert ctrl.pressed == ["rb"]


def test_auto_shift_top_gear_glitch_with_throttle_downshifts():
    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0)
    telem = _telem(gear=6, speed=1.0, rpm=900, num_gears=6)
    event = auto_shift(ctrl, telem, 0.5, 0.0, shifter)
    assert event == "down_to_first"
    assert ctrl.pressed == ["lb"]


def test_false_neutral_after_second_does_not_upshift():
    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0)
    assert auto_shift(ctrl, _telem(gear=2, speed=8.0, rpm=2000), 0.4, 0.0, shifter) is None
    event = auto_shift(ctrl, _telem(gear=0, speed=8.0, rpm=2000), 0.4, 0.0, shifter)
    assert event is None
    assert ctrl.pressed == []


def test_persistent_neutral_after_second_shifts_up_to_first():
    from auto_shift import NEUTRAL_BLIP_FRAMES

    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0)
    auto_shift(ctrl, _telem(gear=2, speed=1.2, rpm=1400), 0.0, 0.0, shifter)
    ctrl.pressed.clear()
    event = None
    for _ in range(NEUTRAL_BLIP_FRAMES + 1):
        event = auto_shift(ctrl, _telem(gear=0, speed=1.2, rpm=3000), 0.45, 0.0, shifter)
    assert event == "to_first"
    assert ctrl.pressed[-1] == "rb"


def test_reverse_gear_uses_rb_not_lb():
    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0)
    auto_shift(ctrl, _telem(gear=2, speed=1.0, rpm=1400), 0.4, 0.0, shifter)
    ctrl.pressed.clear()
    event = auto_shift(ctrl, _telem(gear=15, speed=0.0, rpm=2000, num_gears=4), 0.0, 0.7, shifter)
    assert event == "from_reverse"
    assert ctrl.pressed == ["rb"]

    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0)
    telem = _telem(gear=3, rpm=2000, speed=0.4)
    assert auto_shift(ctrl, telem, 0.0, 0.5, shifter) is None
    assert ctrl.pressed == []


def test_default_max_gear_is_production_and_never_goes_above_second():
    assert AutoShifter().max_gear == 2
    ctrl = FakeController()
    assert auto_shift(ctrl, _telem(gear=2, rpm=7300), 0.8, 0.0, AutoShifter(cooldown_s=0.0)) is None
    assert ctrl.pressed == []


def test_max_gear_3_upshifts_second_to_third_and_stops_there():
    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0, max_gear=3)
    assert auto_shift(ctrl, _telem(gear=2, rpm=7000, max_rpm=7700, speed=30.0), 0.8, 0.0, shifter) == "up"
    assert auto_shift(ctrl, _telem(gear=3, rpm=7000, max_rpm=7700, speed=40.0), 0.8, 0.0, shifter) is None
    assert ctrl.pressed == ["rb"]


def test_max_gear_4_upshifts_third_to_fourth_and_stops_at_top_gear():
    """Coche de 4 marchas (V112): con tope 4 sube de 3ª a 4ª al 0,87 del régimen y en 4ª no pulsa nada, ni RB ni LB."""
    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0, max_gear=4)
    assert auto_shift(ctrl, _telem(gear=3, rpm=6700, max_rpm=7700, speed=39.2, num_gears=4), 1.0, 0.0, shifter) == "up"
    assert auto_shift(ctrl, _telem(gear=4, rpm=7000, max_rpm=7700, speed=50.0, num_gears=4), 1.0, 0.0, shifter) is None
    assert auto_shift(ctrl, _telem(gear=4, rpm=5200, max_rpm=7700, speed=39.2, num_gears=4), 1.0, 0.0, shifter) is None
    assert ctrl.pressed == ["rb"]


def test_third_gear_is_not_sent_back_to_first_when_allowed():
    """Con tope 2 una 3ª a 40 km/h se baja con LB (H50); con tope 3 se deja."""
    low = FakeController()
    assert auto_shift(low, _telem(gear=3, rpm=4000, speed=11.0), 0.8, 0.0, AutoShifter(cooldown_s=0.0)) == "down_to_first"
    ok = FakeController()
    assert auto_shift(ok, _telem(gear=3, rpm=4000, speed=11.0), 0.8, 0.0, AutoShifter(cooldown_s=0.0, max_gear=3)) is None
    assert ok.pressed == []


def test_gear_1_reading_at_the_rev_limit_is_a_udp_glitch_not_a_shift():
    """H50: a 120 km/h y 7442 rpm el UDP marca 1ª tras ir en 2ª; no se debe pulsar RB ni tomarlo como marcha."""
    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0, max_gear=3)
    auto_shift(ctrl, _telem(gear=2, rpm=6000, max_rpm=7700, speed=30.0), 0.8, 0.0, shifter)
    assert auto_shift(ctrl, _telem(gear=1, rpm=7442, max_rpm=7700, speed=33.4), 0.8, 0.0, shifter) is None
    assert shifter.last_forward_gear == 2 and shifter.gear1_glitch
    assert ctrl.pressed == []


def test_real_downshift_to_first_under_braking_is_not_taken_as_a_glitch():
    shifter = AutoShifter(cooldown_s=0.0, max_gear=3)
    auto_shift(FakeController(), _telem(gear=2, rpm=3000, max_rpm=7700, speed=12.0), 0.0, 0.5, shifter)
    auto_shift(FakeController(), _telem(gear=1, rpm=3000, max_rpm=7700, speed=11.0), 0.0, 0.5, shifter)
    assert not shifter.gear1_glitch and shifter.last_forward_gear == 1
