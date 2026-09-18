"""Tests de resolve_teacher_decision y utilidades compartidas."""

from reference_recorder import ReferenceLine, ReferencePoint
from safety_monitor import SafetyMonitor, SafetyStatus
from teacher_controller import TeacherConfig, TeachingController, resolve_teacher_decision
from telemetry_udp import TelemetryFrame, TimingsFrame


def _ref() -> ReferenceLine:
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
        for d in range(40)
    ]
    return ReferenceLine(points=points, track_length=40.0, track_name="t", lap_time=4.0)


def _telem(z: float = 0.0) -> TelemetryFrame:
    return TelemetryFrame(
        position=(10.0, 0.0, z),
        orientation=(0.0, 0.0, 0.0),
        local_velocity=(5.0, 0.0, 0.0),
        world_velocity=(5.0, 0.0, 0.0),
        angular_velocity=(0.0, 0.0, 0.0),
        local_acceleration=(0.0, 0.0, 0.0),
        speed=5.0,
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


def test_resolve_teacher_uses_recovery_on_active_safety():
    ref = _ref()
    teacher = TeachingController(ref, TeacherConfig())
    safety = SafetyMonitor(ref=ref)
    status = SafetyStatus(active=True, reason="stuck")
    decision = resolve_teacher_decision(teacher, _telem(), _timings(), safety, status)
    assert decision.safety_override
    assert decision.brake > 0.0


def test_resolve_teacher_recovers_line_on_high_cte():
    ref = _ref()
    teacher = TeachingController(ref, TeacherConfig())
    safety = SafetyMonitor(ref=ref)
    status = SafetyStatus(active=False)
    telem = _telem(z=8.0)  # muy desviado (CTE > 6 m)
    decision = resolve_teacher_decision(teacher, telem, _timings(), safety, status)
    assert decision.reason == "recover_line"
    assert decision.brake > 0.0
    assert not decision.safety_override


def test_resolve_teacher_safety_on_active_off_track():
    ref = _ref()
    teacher = TeachingController(ref, TeacherConfig())
    safety = SafetyMonitor(ref=ref)
    status = SafetyStatus(active=True, reason="off_track")
    telem = _telem(z=8.0)
    decision = resolve_teacher_decision(teacher, telem, _timings(), safety, status)
    assert decision.safety_override
    assert decision.reason == "safety_off_track"
