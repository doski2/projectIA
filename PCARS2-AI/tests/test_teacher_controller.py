"""Tests del Teaching Controller."""

import math

import pytest

from reference_recorder import ReferenceLine, ReferencePoint
from teacher_controller import TeacherConfig, TeachingController, reverse_brake_target
from telemetry_udp import TelemetryFrame, TimingsFrame


def _curved_ref() -> ReferenceLine:
    points = []
    for d in range(80):
        angle = d * 0.05
        x = 40.0 * math.cos(angle)
        z = 40.0 * math.sin(angle)
        points.append(
            ReferencePoint(
                lap_distance=float(d),
                position=(x, 0.0, z),
                speed=15.0,
                throttle=180,
                brake=0,
                steering=10,
                gear=3,
                orientation=(0.0, 0.0, angle + math.pi / 2),
                local_velocity=(15.0, 0.0, 0.0),
            )
        )
    return ReferenceLine(
        points=points,
        track_length=80.0,
        track_name="curve",
        lap_time=5.0,
    )


def _base_telem(speed: float = 5.0) -> TelemetryFrame:
    return TelemetryFrame(
        position=(0.0, 0.0, 3.0),
        orientation=(0.0, 0.0, 0.0),
        local_velocity=(speed, 0.0, 0.0),
        world_velocity=(speed, 0.0, 0.0),
        angular_velocity=(0.0, 0.0, 0.0),
        local_acceleration=(0.0, 0.0, 0.0),
        speed=speed,
        throttle=0,
        brake=0,
        steering=0,
        clutch=0,
        gear=2,
        num_gears=6,
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
        rpm=4000,
        max_rpm=8000,
        fuel_level=0.8,
        aero_damage=0,
        engine_damage=0,
        car_flags=0,
        brake_bias=50,
        viewed_participant_index=0,
        viewed_is_ai=False,
    )


def _timings() -> TimingsFrame:
    return TimingsFrame(
        lap_distance=10.0,
        current_lap=1,
        current_time=5.0,
        current_sector_time=5.0,
        sector=1,
        race_position=1,
        event_time_remaining=-1.0,
    )


def test_teacher_decision_has_reason():
    ref = _curved_ref()
    teacher = TeachingController(ref, TeacherConfig(speed_target_kmh=20.0))
    decision = teacher.decide(_base_telem(), _timings())
    assert decision.reason
    assert -1.0 <= decision.steering <= 1.0
    assert 0.0 <= decision.throttle <= 1.0
    assert 0.0 <= decision.brake <= 1.0


def test_teacher_steers_toward_line():
    points = [
        ReferencePoint(
            lap_distance=float(d),
            position=(float(d), 0.0, 0.0),
            speed=10.0,
            throttle=100,
            brake=0,
            steering=0,
            gear=2,
            orientation=(0.0, 0.0, 0.0),
            local_velocity=(10.0, 0.0, 0.0),
        )
        for d in range(50)
    ]
    ref = ReferenceLine(
        points=points,
        track_length=50.0,
        track_name="straight",
        lap_time=5.0,
    )
    teacher = TeachingController(ref, TeacherConfig())
    telem = _base_telem(speed=3.0)
    telem.position = (10.0, 0.0, 4.0)  # a la izquierda del trazado (+Z con heading +X)
    timings = TimingsFrame(
        lap_distance=10.0,
        current_lap=1,
        current_time=5.0,
        current_sector_time=5.0,
        sector=1,
        race_position=1,
        event_time_remaining=-1.0,
    )
    signed = teacher.signed_lateral_error(telem.position, timings.lap_distance)
    assert signed < 0.0
    decision = teacher.decide(telem, timings)
    assert decision.steering > 0.0  # girar derecha para volver a la línea


def test_teacher_feedforward_left_curve():
    """En curva a la izquierda (curv > 0), en línea debe girar a la izquierda."""
    ref = _curved_ref()
    teacher = TeachingController(ref, TeacherConfig(speed_target_kmh=40.0))
    d = 20.0
    pt = ref.lookup(d)
    hv = ref.heading_vector(d)
    assert pt is not None
    assert hv is not None
    telem = _base_telem(speed=8.0)
    telem.position = pt.position
    telem.orientation = pt.orientation
    telem.world_velocity = (hv[0] * 8.0, 0.0, hv[1] * 8.0)
    timings = TimingsFrame(
        lap_distance=d,
        current_lap=1,
        current_time=5.0,
        current_sector_time=5.0,
        sector=1,
        race_position=1,
        event_time_remaining=-1.0,
    )
    assert ref.curvature(d) > 0.0
    decision = teacher.decide(telem, timings)
    assert decision.steering < 0.0


def test_teacher_safety_override_no_progress_stopped_uses_throttle():
    ref = _curved_ref()
    teacher = TeachingController(ref)
    telem = _base_telem(speed=0.2)
    decision = teacher.recovery_decision(telem, _timings(), "no_progress")
    assert decision.safety_override
    assert decision.throttle > 0.0
    assert decision.brake == 0.0


def test_teacher_safety_override_stuck_stopped_uses_throttle():
    ref = _curved_ref()
    teacher = TeachingController(ref)
    telem = _base_telem(speed=0.2)
    decision = teacher.recovery_decision(telem, _timings(), "stuck")
    assert decision.safety_override
    assert decision.throttle > 0.0
    assert decision.brake == 0.0


def test_teacher_safety_override_stuck_moving_uses_brake():
    ref = _curved_ref()
    teacher = TeachingController(ref)
    decision = teacher.recovery_decision(_base_telem(speed=3.0), _timings(), "stuck")
    assert decision.safety_override
    assert decision.brake > 0.0
    assert decision.throttle == 0.0


def test_teacher_backward_cuts_throttle():
    ref = _curved_ref()
    teacher = TeachingController(ref)
    telem = _base_telem(speed=2.0)
    telem = telem.__class__(**{**telem.__dict__, "local_velocity": (-2.0, 0.0, 0.0)})
    decision = teacher.decide(telem, _timings())
    assert decision.throttle == 0.0
    assert decision.brake > 0.0
    from teacher_intents import SAFETY_REVERSE_REASON

    assert decision.reason == SAFETY_REVERSE_REASON
    assert decision.safety_override


def test_reverse_brake_target_scales_with_speed():
    assert reverse_brake_target(0.0) == 0.0
    assert reverse_brake_target(0.35) < reverse_brake_target(3.0)


def test_teacher_backward_brakes_harder_when_fast():
    ref = _curved_ref()
    teacher = TeachingController(ref)
    slow = _base_telem(speed=1.0)
    slow = slow.__class__(**{**slow.__dict__, "local_velocity": (-0.5, 0.0, 0.0)})
    fast = _base_telem(speed=5.0)
    fast = fast.__class__(**{**fast.__dict__, "local_velocity": (-4.0, 0.0, 0.0)})
    d_slow = teacher.decide(slow, _timings())
    d_fast = teacher.decide(fast, _timings())
    assert d_fast.brake > d_slow.brake


def test_teacher_backward_steering_not_saturated_on_cte():
    points = [
        ReferencePoint(
            lap_distance=float(d),
            position=(float(d), 0.0, 0.0),
            speed=10.0,
            throttle=100,
            brake=0,
            steering=0,
            gear=2,
            orientation=(0.0, 0.0, 0.0),
            local_velocity=(10.0, 0.0, 0.0),
        )
        for d in range(50)
    ]
    ref = ReferenceLine(
        points=points,
        track_length=50.0,
        track_name="straight",
        lap_time=5.0,
    )
    teacher = TeachingController(ref)
    telem = _base_telem(speed=2.0)
    telem = telem.__class__(
        **{
            **telem.__dict__,
            "position": (10.0, 0.0, 2.0),
            "local_velocity": (-2.0, 0.0, 0.0),
            "world_velocity": (-2.0, 0.0, 0.0),
            "orientation": (0.0, 0.0, 0.0),
        }
    )
    decision = teacher.decide(telem, TimingsFrame(
        lap_distance=10.0, current_lap=1, current_time=5.0,
        current_sector_time=5.0, sector=1, race_position=1, event_time_remaining=-1.0,
    ))
    assert decision.reason == "safety_reverse"
    assert abs(decision.steering) < 0.95


def test_teacher_backward_beats_stuck_throttle():
    from safety_monitor import SafetyMonitor, SafetyStatus
    from teacher_controller import resolve_teacher_decision

    ref = _curved_ref()
    teacher = TeachingController(ref)
    telem = _base_telem(speed=0.2)
    telem = telem.__class__(**{**telem.__dict__, "local_velocity": (-0.5, 0.0, 0.0)})
    safety = SafetyMonitor(ref=ref)
    status = SafetyStatus(active=True, reason="stuck")
    decision = resolve_teacher_decision(teacher, telem, _timings(), safety, status)
    assert decision.throttle == 0.0
    assert decision.brake > 0.0
