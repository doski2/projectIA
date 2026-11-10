"""Tests del Teaching Controller."""

import math
from typing import Any, Dict

import pytest

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
    cfg: Dict[str, Any] = dict(lat_accel_limit=6.5)
    slow = TeachingController(_sugo(), TeacherConfig(speed_target_kmh=40.0, **cfg))
    fast = TeachingController(_sugo(), TeacherConfig(speed_target_kmh=80.0, **cfg))
    ds = range(0, 3560, 10)
    assert min(slow.physical_curve_target(float(d)) for d in ds) >= 40.0 / 3.6
    targets = [min(80.0 / 3.6, fast.physical_curve_target(float(d))) for d in ds]
    assert min(targets) < 80.0 / 3.6 - 2.0  # alguna curva obliga a bajar


def test_free_straight_physical_mode_on_sugo():
    ds = [float(d) for d in range(0, 3560, 5)]
    slow = TeachingController(_sugo(), TeacherConfig(speed_target_kmh=40.0, lat_accel_limit=6.5))
    fast = TeachingController(_sugo(), TeacherConfig(speed_target_kmh=80.0, lat_accel_limit=6.5))
    assert all(slow.free_straight(d) for d in ds)  # a 40 km/h el teacher no pide bajar en ningún punto
    share = sum(fast.free_straight(d) for d in ds) / len(ds)
    assert 0.3 < share < 0.95  # a 80 hay rectas libres y tramos donde ya pide bajar


def test_physical_curve_target_follows_a_lat_accel_limit_changed_on_the_fly():
    """A1.3 sube `lat_accel_limit` en marcha: los límites en curva no pueden quedarse con los del valor anterior (H53)."""
    teacher = TeachingController(_sugo(), TeacherConfig(speed_target_kmh=90.0, lat_accel_limit=6.5))
    ds = [float(d) for d in range(228, 600, 10)]
    base = [teacher.physical_curve_target(d) for d in ds]
    teacher.config.lat_accel_limit = 60.0
    free = [teacher.physical_curve_target(d) for d in ds]
    assert min(free) > min(base) * 1.5 and min(free) >= 90.0 / 3.6
    teacher.config.lat_accel_limit = 6.5
    assert [teacher.physical_curve_target(d) for d in ds] == base


def test_free_straight_without_physical_model_uses_curvature():
    straight = TeachingController(_straight_ref(), TeacherConfig(speed_target_kmh=40.0))
    assert straight.free_straight(10.0)
    curved = TeachingController(_curved_ref(), TeacherConfig(speed_target_kmh=40.0))
    assert not curved.free_straight(10.0)


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


def _steer_in_sugo_bend(gain: float, speed_kmh: float, **cfg) -> float:
    """Volante del teacher parado en la línea de Sugo, justo antes de las curvas de 228-600 m, con la velocidad indicada (H58)."""
    teacher = TeachingController(_sugo(), TeacherConfig(speed_target_kmh=speed_kmh, ff_speed_gain=gain, **cfg))
    telem = _on_line(speed_kmh / 3.6)
    steering, _ = teacher.compute_steering(telem, 330.0, 0.0, 0.0)
    return steering


def test_steer_ff_gain_zero_keeps_the_production_steering_at_any_speed():
    for kmh in (20.0, 60.0, 85.0, 100.0):
        base = TeachingController(_sugo(), TeacherConfig(speed_target_kmh=kmh))
        telem = _on_line(kmh / 3.6)
        expected = base.compute_steering(telem, 330.0, 0.0, 0.0)[0]
        assert _steer_in_sugo_bend(0.0, kmh) == expected


def test_steer_ff_factor_is_one_up_to_v0_and_grows_with_v_squared():
    teacher = TeachingController(_sugo(), TeacherConfig(ff_speed_gain=0.003))
    assert teacher.ff_speed_factor(10.0) == 1.0
    assert teacher.ff_speed_factor(60.0 / 3.6) == 1.0
    assert teacher.ff_speed_factor(80.0 / 3.6) == pytest.approx(1.65, abs=0.01)
    assert teacher.ff_speed_factor(85.0 / 3.6) == pytest.approx(1.84, abs=0.01)
    assert teacher.ff_speed_factor(90.0 / 3.6) == pytest.approx(2.04, abs=0.01)


def test_steer_ff_gain_leaves_the_steering_unchanged_up_to_v0_and_adds_it_above():
    assert _steer_in_sugo_bend(0.003, 50.0) == _steer_in_sugo_bend(0.0, 50.0)
    base = _steer_in_sugo_bend(0.0, 85.0)
    more = _steer_in_sugo_bend(0.003, 85.0)
    assert base != 0.0 and more * base > 0.0 and abs(more) > abs(base)  # mismo signo y más volante
    assert -1.0 <= more <= 1.0


def _sliding(beta_deg: float, speed: float = 25.0) -> TelemetryFrame:
    """Coche en la línea con deriva `beta_deg` (convención del juego: v lateral = eje 0, v longitudinal = −eje 2)."""
    telem = _on_line(speed)
    telem.local_velocity = (speed * math.tan(math.radians(beta_deg)), 0.0, -speed)
    return telem


def _steer_slip(beta_deg: float, gain: float, cte: float = 0.0, **cfg) -> float:
    cfg.setdefault("steer_smooth", 1.0)  # sin filtro: se mira la orden de este tick
    teacher = TeachingController(_straight_ref(), TeacherConfig(speed_target_kmh=90.0, slip_steer_gain=gain, **cfg))
    return teacher.compute_steering(_sliding(beta_deg), 100.0, cte, 0.0)[0]


def test_slip_angle_sign_and_low_speed_guard():
    from teacher_controller import slip_angle

    assert slip_angle(_sliding(0.0)) == 0.0
    assert slip_angle(_sliding(8.0)) == pytest.approx(math.radians(8.0))
    assert slip_angle(_sliding(-8.0)) == pytest.approx(-math.radians(8.0))
    slow = _on_line(2.0)
    slow.local_velocity = (1.5, 0.0, -2.0)
    assert slip_angle(slow) == 0.0  # parado o casi: el ángulo no significa nada


def test_slip_gain_zero_keeps_the_production_steering_even_when_sliding():
    for beta in (-12.0, -5.0, 0.0, 5.0, 12.0):
        assert _steer_slip(beta, 0.0, cte=1.0) == _steer_slip(0.0, 0.0, cte=1.0)


def test_slip_inside_the_deadzone_changes_nothing():
    assert _steer_slip(2.5, 5.0, cte=1.0) == _steer_slip(0.0, 5.0, cte=1.0)
    assert _steer_slip(-2.5, 5.0, cte=1.0) == _steer_slip(0.0, 5.0, cte=1.0)


def test_countersteer_goes_against_the_slide_with_the_games_sign():
    """Cola fuera girando a la izquierda (deriva negativa) → volante a la derecha (positivo) y al revés (V17)."""
    base = _steer_slip(0.0, 5.0)
    assert _steer_slip(-8.0, 5.0) > base + 0.1
    assert _steer_slip(8.0, 5.0) < base - 0.1
    assert _steer_slip(-8.0, 5.0) == pytest.approx(-_steer_slip(8.0, 5.0), abs=1e-6)  # simétrico en una recta sin CTE
    assert _steer_slip(-8.0, 5.0) == pytest.approx(5.0 * (math.radians(8.0) - math.radians(3.0)), abs=1e-6)  # ganancia × (deriva − zona muerta)


def test_cte_gain_is_cut_in_a_slide_so_it_does_not_push_the_slide():
    """Con el coche a la izquierda de la línea (CTE < 0) el CTE pide girar a la derecha; con 8° de deriva positiva ese volante empeora el derrape."""
    no_slip = _steer_slip(0.0, 5.0, cte=-4.0)
    assert no_slip > 0.9  # sin deriva, el CTE manda y casi llega al tope
    in_slide = _steer_slip(8.0, 5.0, cte=-4.0)
    assert in_slide < 0.0  # con deriva +8° el contravolante gana
    assert _steer_slip(8.0, 0.0, cte=-4.0) > 0.9  # sin la opción, el teacher sigue tirando a tope hacia el lado equivocado (el fallo de V16)


def test_slip_correction_also_applies_in_the_safety_branch():
    teacher = TeachingController(_straight_ref(), TeacherConfig(speed_target_kmh=90.0, slip_steer_gain=5.0, steer_smooth=1.0))
    counter, scale = teacher.slip_correction(_sliding(8.0))
    assert counter < 0.0 and scale == 0.0
    with_safety = teacher.compute_steering(_sliding(8.0), 100.0, -4.0, 0.0, safety=True)[0]
    assert with_safety < 0.0


def _cte_term(speed_kmh: float, **cfg) -> float:
    """Volante que pide solo el CTE (recta, sin rumbo ni deriva ni filtro) con el coche 1 m a la derecha de la línea."""
    teacher = TeachingController(_straight_ref(), TeacherConfig(speed_target_kmh=speed_kmh, steer_smooth=1.0, **cfg))
    return teacher.compute_steering(_on_line(speed_kmh / 3.6), 100.0, 1.0, 0.0)[0]


def test_lat_gain_v0_zero_keeps_the_production_cte_gain_at_any_speed():
    for kmh in (30.0, 60.0, 100.0, 130.0):
        assert _cte_term(kmh, lat_gain_v0_kmh=0.0) == pytest.approx(-0.12)


def test_lat_gain_v0_scales_the_cte_gain_by_v0_over_v_squared_above_v0():
    assert _cte_term(40.0, lat_gain_v0_kmh=60.0) == pytest.approx(-0.12)  # por debajo de v0 no cambia
    assert _cte_term(60.0, lat_gain_v0_kmh=60.0) == pytest.approx(-0.12)
    assert _cte_term(100.0, lat_gain_v0_kmh=60.0) == pytest.approx(-0.12 * (60.0 / 100.0) ** 2)
    assert _cte_term(130.0, lat_gain_v0_kmh=60.0) == pytest.approx(-0.12 * (60.0 / 130.0) ** 2)


def test_lat_gain_v0_also_scales_the_safety_branch():
    teacher = TeachingController(_straight_ref(), TeacherConfig(speed_target_kmh=100.0, steer_smooth=1.0, lat_gain_v0_kmh=60.0))
    safe = teacher.compute_steering(_on_line(100.0 / 3.6), 100.0, 1.0, 0.0, safety=True)[0]
    assert safe == pytest.approx(-0.12 * 1.5 * (60.0 / 100.0) ** 2)


def test_ff_speed_cap_freezes_the_factor_above_the_cap_and_zero_changes_nothing():
    """V57: con tope, el factor no crece por encima; por debajo (y con tope 0) es el de siempre."""
    sin = TeachingController(_sugo(), TeacherConfig(ff_speed_gain=0.003, ff_speed_v0_kmh=0.0))
    con = TeachingController(_sugo(), TeacherConfig(ff_speed_gain=0.003, ff_speed_v0_kmh=0.0, ff_speed_cap_kmh=100.0))
    cero = TeachingController(_sugo(), TeacherConfig(ff_speed_gain=0.003, ff_speed_v0_kmh=0.0, ff_speed_cap_kmh=0.0))
    for kmh in (0.0, 30.0, 72.0, 90.0, 100.0):
        assert con.ff_speed_factor(kmh / 3.6) == sin.ff_speed_factor(kmh / 3.6)
    for kmh in (72.0, 108.0, 125.0, 150.0):
        assert cero.ff_speed_factor(kmh / 3.6) == sin.ff_speed_factor(kmh / 3.6)
    tope = sin.ff_speed_factor(100.0 / 3.6)
    for kmh in (101.0, 108.0, 119.0, 140.0):
        assert con.ff_speed_factor(kmh / 3.6) == pytest.approx(tope)
        assert sin.ff_speed_factor(kmh / 3.6) > tope
    assert tope == pytest.approx(1.0 + 0.003 * (100.0 / 3.6) ** 2)


def test_ff_speed_cap_changes_the_steering_only_above_the_cap():
    for kmh, igual in ((60.0, True), (95.0, True), (120.0, False)):
        sin = _steer_in_sugo_bend(0.003, kmh, ff_speed_v0_kmh=0.0)
        con = _steer_in_sugo_bend(0.003, kmh, ff_speed_v0_kmh=0.0, ff_speed_cap_kmh=100.0)
        assert (sin == con) is igual
        if not igual:
            assert abs(con) < abs(sin)  # menos anticipación a 120 km/h


def test_ff_factor_with_v0_zero_matches_the_measured_steering_need_of_h58():
    """H58: la curva pide ≈ 2,77 + 0,0183 · v² de volante por unidad de κ y la anticipación fija da 4,3; con G = 0,0035 y v0 = 0 el factor sigue esa curva (V21)."""
    teacher = TeachingController(_sugo(), TeacherConfig(ff_speed_gain=0.0035, ff_speed_v0_kmh=0.0))
    for kmh in (60.0, 80.0, 100.0):
        v = kmh / 3.6
        needed = (2.77 + 0.0183 * v * v) / 4.3
        assert teacher.ff_speed_factor(v) == pytest.approx(needed, rel=0.12)
    assert teacher.ff_speed_factor(0.0) == 1.0


def _sugo_spot_before_a_bend():
    """Un punto de Sugo donde la curva está a 30 m pero no a unos 6 m: una recta que acaba en una curva."""
    ref = _sugo()
    for d in range(0, 3500):
        if abs(ref.curvature(d + 30.0)) > 0.015 and abs(ref.curvature(d + 6.0)) < 0.003 and abs(ref.curvature(float(d))) < 0.003:
            return ref, float(d)
    raise AssertionError("no hay un punto así en Sugo")


def test_heading_gain_scales_only_the_heading_term():
    ref, d = _sugo_spot_before_a_bend()
    telem = _on_line(80.0 / 3.6)
    base = TeachingController(ref, TeacherConfig(speed_target_kmh=80.0, steer_smooth=1.0))
    alta = TeachingController(ref, TeacherConfig(speed_target_kmh=80.0, steer_smooth=1.0, k_heading=0.7))
    assert base.config.k_heading == 0.55  # producción
    # sin error de rumbo, el volante es el mismo
    assert base.compute_steering(telem, d, 0.0, 0.0)[0] == alta.compute_steering(telem, d, 0.0, 0.0)[0]
    # con 0,05 rad de error de rumbo, la diferencia es (0,7 − 0,55) · 0,05
    diff = alta.compute_steering(telem, d, 0.0, 0.05)[0] - base.compute_steering(telem, d, 0.0, 0.05)[0]
    assert abs(diff - 0.15 * 0.05) < 1e-9


def test_steer_preview_zero_keeps_the_30_m_lookahead():
    ref, d = _sugo_spot_before_a_bend()
    base = TeachingController(ref, TeacherConfig(speed_target_kmh=80.0, steer_smooth=1.0))
    same = TeachingController(ref, TeacherConfig(speed_target_kmh=80.0, steer_smooth=1.0, steer_preview_s=0.0))
    telem = _on_line(80.0 / 3.6)
    assert base.compute_steering(telem, d, 0.0, 0.0)[0] == same.compute_steering(telem, d, 0.0, 0.0)[0]


def test_steer_preview_by_time_does_not_steer_into_a_bend_30_m_early():
    ref, d = _sugo_spot_before_a_bend()
    telem = _on_line(80.0 / 3.6)
    old = TeachingController(ref, TeacherConfig(speed_target_kmh=80.0, steer_smooth=1.0))
    new = TeachingController(ref, TeacherConfig(speed_target_kmh=80.0, steer_smooth=1.0, steer_preview_s=0.3))
    s_old, ahead_old = old.compute_steering(telem, d, 0.0, 0.0)
    s_new, ahead_new = new.compute_steering(telem, d, 0.0, 0.0)
    assert abs(s_old) > 0.02  # con 30 m fijos ya gira antes de la curva (1,8 · κ ≥ 0,027)
    assert abs(s_new) < 0.4 * abs(s_old)  # con 0,3 s (6,7 m a 80 km/h) casi no gira todavía
    assert ahead_old == ahead_new  # la curvatura a 30 m que se devuelve para los pedales no cambia


def test_steer_preview_has_a_minimum_distance_at_low_speed():
    ref, d = _sugo_spot_before_a_bend()
    slow = TeachingController(ref, TeacherConfig(speed_target_kmh=10.0, steer_smooth=1.0, steer_preview_s=0.3))
    telem = _on_line(1.0)  # 1 m/s · 0,3 s = 0,3 m: se usa el mínimo de 4 m
    expected = slow.config.k_curvature * ref.curvature(d) + slow.config.k_lookahead * ref.curvature(d + 4.0)
    assert slow.compute_steering(telem, d, 0.0, 0.0)[0] == pytest.approx(max(-1.0, min(1.0, -expected)), abs=1e-9)


def _gas_pidiendo_acelerar(**cfg) -> float:
    """Gas del teacher en la recta de 100 m con el coche muy por debajo de la consigna (acelerando a fondo según el teacher)."""
    teacher = TeachingController(_straight_ref(), TeacherConfig(speed_target_kmh=90.0, lat_accel_limit=6.5, **cfg))
    gas = 0.0
    for _ in range(600):
        gas = teacher.decide(_on_line(5.0), _timings()).throttle
    return gas


def test_throttle_max_defaults_to_the_production_cap_of_085():
    assert TeacherConfig().throttle_max == 0.85
    assert _gas_pidiendo_acelerar() == pytest.approx(0.85, abs=1e-6)


def test_throttle_max_one_lets_the_teacher_floor_it():
    assert _gas_pidiendo_acelerar(throttle_max=1.0) > 0.95
    assert _gas_pidiendo_acelerar(throttle_max=0.6) == pytest.approx(0.6, abs=1e-6)


def _freno_con_exceso(ref, d: float, speed_ms: float, target_kmh: float, **cfg) -> float:
    """Pedal de freno tras 90 ticks con el coche sobre la línea en `d`, a `speed_ms` y con la consigna dada."""
    teacher = TeachingController(ref, TeacherConfig(speed_target_kmh=target_kmh, lat_accel_limit=9.0, **cfg))
    telem = _on_line(speed_ms)
    p = ref.lookup(d)
    telem.position = (p.position[0], p.position[1], p.position[2])
    timings = _timings()
    timings.lap_distance = d
    brake = 0.0
    for _ in range(90):
        brake = teacher.decide(telem, timings).brake
    return brake


def test_brake_options_default_to_the_production_law():
    cfg = TeacherConfig()
    assert cfg.brake_decel_straight == 0.0 and cfg.brake_overspeed_straight_ms == 8.0
    ref = _sugo()  # recta 1 de Sugo: a 3150 m no hay curva en los 150 m de anticipación
    assert _freno_con_exceso(ref, 3150.0, 19.2, 60.0) == _freno_con_exceso(ref, 3150.0, 19.2, 60.0, brake_decel_straight=0.0, brake_overspeed_straight_ms=8.0)
    assert 0.25 < _freno_con_exceso(ref, 3150.0, 19.2, 60.0) < 0.4  # exceso de 2,5 m/s / 8 ≈ 0,31


def test_stronger_straight_braking_presses_the_pedal_harder_only_on_a_straight():
    ref = _sugo()  # recta 1 de Sugo: a 3150 m no hay curva en los 150 m de anticipación
    legacy = _freno_con_exceso(ref, 3150.0, 19.2, 60.0)
    strong = _freno_con_exceso(ref, 3150.0, 19.2, 60.0, brake_overspeed_straight_ms=2.5)
    assert strong > 0.9 and strong > 2.5 * legacy  # exceso de 2,5 m/s / 2,5 → a fondo
    assert TeachingController(ref, TeacherConfig(brake_overspeed_straight_ms=2.5)).braking_on_straight(3150.0, 0.2)
    assert not TeachingController(ref, TeacherConfig(brake_overspeed_straight_ms=2.5)).braking_on_straight(3150.0, 1.5)  # fuera de la línea: la ley de siempre
    sugo = _sugo()
    curva = next(float(d) for d in range(0, 3500) if abs(sugo.curvature(float(d))) > 0.012)
    teacher = TeachingController(sugo, TeacherConfig(brake_overspeed_straight_ms=2.5))
    assert not teacher.braking_on_straight(curva, 0.0)  # en curva se frena como siempre


def test_assumed_straight_braking_delays_the_slowdown_before_a_bend():
    ref, d = _sugo_spot_before_a_bend()
    teacher = TeachingController(ref, TeacherConfig(lat_accel_limit=9.0))
    base = teacher.physical_curve_target(d)
    fuerte = teacher.physical_curve_target(d, 8.0)
    assert fuerte > base  # suponer más frenada deja ir más rápido hasta más cerca de la curva
    assert teacher.physical_curve_target(d, None) == base
