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
        local_velocity=(vx, 0.0, 0.0),
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


def test_auto_shift_no_brake_downshift_when_crawling():
    ctrl = FakeController()
    shifter = AutoShifter(cooldown_s=0.0)
    telem = _telem(gear=3, rpm=2000, speed=0.4)
    assert auto_shift(ctrl, telem, 0.0, 0.5, shifter) is None
    assert ctrl.pressed == []
