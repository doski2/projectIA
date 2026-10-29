"""Tests del Teaching Controller."""

import math


from reference_recorder import ReferenceLine, ReferencePoint
from teacher_controller import (
    MAINTAIN_THROTTLE,
    TeacherConfig,
    TeachingController,
    reverse_brake_target,
)
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
        local_velocity=(0.0, 0.0, -speed),  # eje 2 = longitudinal, negativo al avanzar (H1)
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


def test_teacher_stronger_steer_when_far_from_line():
    """Con |signed_cte|>2.5 m el boost lateral debe aumentar |steering| vs proporción lineal."""
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
    ref = ReferenceLine(points=points, track_length=50.0, track_name="straight", lap_time=5.0)
    teacher = TeachingController(ref, TeacherConfig())
    timings = TimingsFrame(
        lap_distance=10.0,
        current_lap=1,
        current_time=5.0,
        current_sector_time=5.0,
        sector=1,
        race_position=1,
        event_time_remaining=-1.0,
    )
    telem_near = _base_telem(speed=5.0)
    telem_near.position = (10.0, 0.0, 2.0)
    telem_far = _base_telem(speed=5.0)
    telem_far.position = (10.0, 0.0, 3.5)
    s_near = abs(teacher.signed_lateral_error(telem_near.position, 10.0))
    s_far = abs(teacher.signed_lateral_error(telem_far.position, 10.0))
    assert s_far > s_near
    st_near = abs(teacher.decide(telem_near, timings).steering)
    st_far = abs(teacher.decide(telem_far, timings).steering)
    # Con boost, el ratio de steer crece más que el ratio de CTE.
    assert st_far / max(st_near, 1e-6) > (s_far / s_near) * 1.1


def test_edge_grass_does_not_brake():
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
    ref = ReferenceLine(points=points, track_length=50.0, track_name="straight", lap_time=5.0)
    teacher = TeachingController(ref, TeacherConfig(speed_target_kmh=20.0))
    telem = _base_telem(speed=5.0)
    telem.position = (10.0, 0.0, 2.0)
    decision = teacher.decide(telem, _timings(), edge_surface=True)
    assert decision.safety_override is False
    assert decision.reason == "edge_grass"
    assert decision.brake == 0.0
    assert decision.throttle == MAINTAIN_THROTTLE
    assert abs(decision.steering) > 0.0


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
    telem = telem.__class__(**{**telem.__dict__, "local_velocity": (0.0, 0.0, 2.0)})
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
    slow = slow.__class__(**{**slow.__dict__, "local_velocity": (0.0, 0.0, 0.5)})
    fast = _base_telem(speed=5.0)
    fast = fast.__class__(**{**fast.__dict__, "local_velocity": (0.0, 0.0, 4.0)})
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
            "local_velocity": (0.0, 0.0, 2.0),
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


def test_teacher_neutral_rolling_keeps_engage_first():
    from teacher_intents import ENGAGE_FIRST_REASON

    ref = _curved_ref()
    teacher = TeachingController(ref)
    telem = _base_telem(speed=2.0)
    telem = telem.__class__(**{**telem.__dict__, "gear": 0, "rpm": 2500})
    for _ in range(119):
        teacher.decide(telem, _timings())
    decision = teacher.decide(telem, _timings())
    assert decision.reason == ENGAGE_FIRST_REASON
    assert decision.throttle >= 0.35
    assert decision.brake == 0.0


def test_teacher_engage_first_from_second_at_crawl():
    ref = _curved_ref()
    teacher = TeachingController(ref)
    telem = _base_telem(speed=1.0)
    telem = telem.__class__(**{**telem.__dict__, "gear": 2, "rpm": 900})
    decision = teacher.decide(telem, _timings())
    from teacher_intents import ENGAGE_FIRST_REASON

    assert decision.reason == ENGAGE_FIRST_REASON


def test_teacher_engage_first_after_glitch_gear_not_wheelspin():
    ref = _curved_ref()
    teacher = TeachingController(ref)
    telem = _base_telem(speed=1.0)
    telem = telem.__class__(**{**telem.__dict__, "gear": 6, "rpm": 900, "num_gears": 6})
    decision = teacher.decide(telem, _timings())
    from teacher_intents import ENGAGE_FIRST_REASON

    assert decision.reason == ENGAGE_FIRST_REASON
    assert decision.brake == 0.0
    for _ in range(20):
        decision = teacher.decide(telem, _timings())
    assert decision.reason == ENGAGE_FIRST_REASON
    assert decision.throttle >= 0.35


def _straight_ref() -> ReferenceLine:
    points = [
        ReferencePoint(
            lap_distance=float(d), position=(float(d), 0.0, 0.0), speed=10.0, throttle=100, brake=0,
            steering=0, gear=2, orientation=(0.0, 0.0, 0.0), local_velocity=(10.0, 0.0, 0.0),
        )
        for d in range(50)
    ]
    return ReferenceLine(points=points, track_length=50.0, track_name="straight", lap_time=5.0)


def _on_line(speed: float) -> TelemetryFrame:
    telem = _base_telem(speed=speed)
    telem.position = (10.0, 0.0, 0.0)
    return telem


def test_teacher_never_presses_throttle_and_brake_together():
    """P16: un solo eje de pedal; al pasar de frenar a acelerar (y al revés) la transición pasa por cero."""
    teacher = TeachingController(_straight_ref(), TeacherConfig(speed_target_kmh=40.0))
    seen = set()
    for speed in ([20.0] * 40 + [11.0] * 40 + [3.0] * 40) * 3:  # exceso, mantener y falta de velocidad, en bucle
        decision = teacher.decide(_on_line(speed), _timings())
        assert min(decision.throttle, decision.brake) == 0.0, (speed, decision)
        seen.add(decision.reason)
    assert {"brake_overspeed", "accel_straight", "maintain_speed"} <= seen


def test_teacher_releases_brake_before_gas_returns():
    teacher = TeachingController(_straight_ref(), TeacherConfig(speed_target_kmh=40.0))
    braking = [teacher.decide(_on_line(20.0), _timings()) for _ in range(60)][-1]
    assert braking.brake > 0.2 and braking.throttle == 0.0
    steps = [teacher.decide(_on_line(11.0), _timings()) for _ in range(120)]
    first_gas = next(i for i, d in enumerate(steps) if d.throttle > 0.0)
    assert all(d.brake > 0.0 for d in steps[:first_gas])  # hasta soltar el freno no hay gas
    assert all(d.brake == 0.0 for d in steps[first_gas:])
    assert steps[-1].throttle > 0.0


def _sugo():
    from pathlib import Path

    return ReferenceLine.load(str(Path(__file__).resolve().parents[1] / "src" / "refs" / "sugo_ai.json"))


def test_physical_curve_target_needs_no_slowdown_at_40_kmh_but_anticipates_at_80():
    """P16: v_lim = sqrt(a_lat/κ) con anticipación de frenada; a 40 km/h Sugo no exige bajar en ninguna curva."""
    cfg = dict(lat_accel_limit=6.5)
    slow = TeachingController(_sugo(), TeacherConfig(speed_target_kmh=40.0, **cfg))
    fast = TeachingController(_sugo(), TeacherConfig(speed_target_kmh=80.0, **cfg))
    ds = range(0, 3560, 10)
    assert min(slow.physical_curve_target(float(d)) for d in ds) >= 40.0 / 3.6
    targets = [min(80.0 / 3.6, fast.physical_curve_target(float(d))) for d in ds]
    assert min(targets) < 80.0 / 3.6 - 2.0  # alguna curva obliga a bajar


def test_physical_curve_target_removes_spurious_overspeed_brake_at_fixed_40_kmh():
    ref = _sugo()
    heuristic = TeachingController(ref, TeacherConfig(speed_target_kmh=40.0))
    physical = TeachingController(ref, TeacherConfig(speed_target_kmh=40.0, lat_accel_limit=6.5))

    def reasons(teacher):
        out = set()
        for d in range(0, 3560, 7):
            pt = ref.lookup(float(d))
            hv = ref.heading_vector(float(d))
            assert pt is not None and hv is not None
            telem = _base_telem(speed=11.4)  # 41 km/h, como en C0
            telem.position = pt.position
            telem.orientation = pt.orientation
            telem.world_velocity = (hv[0] * 11.4, 0.0, hv[1] * 11.4)
            timings = TimingsFrame(
                lap_distance=float(d), current_lap=1, current_time=5.0, current_sector_time=5.0,
                sector=1, race_position=1, event_time_remaining=-1.0,
            )
            out.add(teacher.decide(telem, timings).reason)
        return out

    assert "brake_overspeed" in reasons(heuristic)
    assert "brake_overspeed" not in reasons(physical)


def test_physical_mode_holds_speed_with_pi_throttle_and_no_brake():
    """P16: en modo físico el gas lo fija un PI, no un valor fijo; un coche de juguete se queda en la consigna."""
    results = {}
    for name, cfg in (
        ("heuristic", TeacherConfig(speed_target_kmh=40.0)),
        ("pi", TeacherConfig(speed_target_kmh=40.0, lat_accel_limit=6.5)),
    ):
        teacher = TeachingController(_straight_ref(), cfg)
        v, brake_ticks, tail = 11.4, 0, []
        for i in range(60 * 60):
            equilibrium = 0.31 if i < 60 * 30 else 0.45  # el gas que pide el coche cambia (pendiente, marcha...)
            d = teacher.decide(_on_line(v), _timings())
            assert min(d.throttle, d.brake) == 0.0
            v = max(0.0, v + (6.0 * (d.throttle - equilibrium) - 9.0 * d.brake) / 60)
            brake_ticks += d.brake > 0.05
            if i >= 60 * 55:
                tail.append(v * 3.6)
        results[name] = (sum(tail) / len(tail), brake_ticks)
    mean_pi, brakes_pi = results["pi"]
    assert abs(mean_pi - 40.0) < 1.0 and brakes_pi == 0
    assert abs(results["heuristic"][0] - 40.0) > abs(mean_pi - 40.0)  # el gas fijo se queda corto


def test_physical_mode_pi_resets_on_safety():
    teacher = TeachingController(_straight_ref(), TeacherConfig(speed_target_kmh=40.0, lat_accel_limit=6.5))
    for _ in range(600):
        teacher.decide(_on_line(10.0), _timings())  # 3 km/h/s por debajo: la integral sube
    assert teacher._speed_i > teacher.config.pi_ff
    teacher.decide(_on_line(10.0), _timings(), safety=True, safety_reason="stuck")
    assert teacher._speed_i == teacher.config.pi_ff


def test_teacher_backward_beats_stuck_throttle():
    from safety_monitor import SafetyMonitor, SafetyStatus
    from teacher_controller import resolve_teacher_decision

    ref = _curved_ref()
    teacher = TeachingController(ref)
    telem = _base_telem(speed=0.2)
    telem = telem.__class__(**{**telem.__dict__, "local_velocity": (0.0, 0.0, 0.5)})
    safety = SafetyMonitor(ref=ref)
    status = SafetyStatus(active=True, reason="stuck")
    decision = resolve_teacher_decision(teacher, telem, _timings(), safety, status)
    assert decision.throttle == 0.0
    assert decision.brake > 0.0


def _label_gas_while_bc_drives(track: bool, applied_gas: float = 0.04, seconds: int = 400) -> float:
    """Gas que etiqueta el teacher mientras conduce otro a una velocidad algo por debajo de la consigna."""
    teacher = TeachingController(_straight_ref(), TeacherConfig(speed_target_kmh=20.0, lat_accel_limit=6.5))
    v = 19.6 / 3.6
    label = 0.0
    for _ in range(60 * seconds):
        d = teacher.decide(_on_line(v), _timings())
        label = d.throttle
        if track:
            teacher.track_applied_pedals(applied_gas, 0.0)
    return label


def test_pi_integral_winds_up_when_nobody_tracks_the_applied_pedals():
    """Sin anti-windup la etiqueta de gas se satura (en el check del 29/10 llegó a 0,55 con 0,04 aplicado)."""
    assert _label_gas_while_bc_drives(track=False) > 0.5


def test_track_applied_pedals_keeps_the_gas_label_near_what_is_applied():
    label = _label_gas_while_bc_drives(track=True)
    assert label < 0.15
    assert abs(label - 0.04) < 0.1


def test_track_applied_pedals_follows_a_higher_applied_gas_too():
    assert abs(_label_gas_while_bc_drives(track=True, applied_gas=0.2) - 0.2) < 0.05


def test_track_applied_pedals_is_noop_outside_the_pi():
    teacher = TeachingController(_straight_ref(), TeacherConfig(speed_target_kmh=40.0))  # sin modo físico: no hay PI
    teacher.decide(_on_line(10.0), _timings())
    before = teacher._speed_i
    teacher.track_applied_pedals(0.9, 0.0)
    assert teacher._speed_i == before
    teacher.config.lat_accel_limit = 6.5
    teacher.decide(_on_line(10.0), _timings(), safety=True, safety_reason="stuck")  # rama de seguridad: no pasa por el PI
    teacher.track_applied_pedals(0.9, 0.0)
    assert teacher._speed_i == teacher.config.pi_ff
