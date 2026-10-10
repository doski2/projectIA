"""Tests de observación universal e intenciones."""

import math

import numpy as np
import pytest

from obs_universal import OBS_UNIVERSAL_DIM, build_obs_universal
from reference_recorder import ReferenceLine, ReferencePoint
from teacher_intents import (
    NUM_REASONS,
    build_conditioned_obs,
    encode_reason_id,
    normalize_reason,
    rule_for_reason,
)
from telemetry_udp import TelemetryFrame, TimingsFrame


def _straight_ref(length: int = 80) -> ReferenceLine:
    points = [
        ReferencePoint(
            lap_distance=float(d),
            position=(float(d), 0.0, 0.0),
            speed=15.0,
            throttle=180,
            brake=0,
            steering=0,
            gear=3,
            orientation=(0.0, 0.0, 0.0),
            local_velocity=(15.0, 0.0, 0.0),
        )
        for d in range(length)
    ]
    return ReferenceLine(points=points, track_length=float(length), track_name="test", lap_time=5.0)


def _telem(d: float = 20.0, z: float = 0.0) -> TelemetryFrame:
    return TelemetryFrame(
        position=(d, 0.0, z),
        orientation=(0.0, 0.0, 0.0),
        local_velocity=(12.0, 0.0, 0.0),
        world_velocity=(12.0, 0.0, 0.0),
        angular_velocity=(0.0, 0.0, 0.0),
        local_acceleration=(0.0, 0.0, 0.0),
        speed=12.0,
        throttle=100,
        brake=0,
        steering=0,
        clutch=0,
        gear=3,
        num_gears=6,
        raw_throttle=100,
        raw_brake=0,
        raw_steering=0,
        tyre_temp=(80, 80, 80, 80),
        tyre_tread_temp=(80, 80, 80, 80),
        tyre_wear=(0, 0, 0, 0),
        tyre_rps=(12.0, 12.0, 12.0, 12.0),
        terrain=(0, 0, 0, 0),
        ride_height=(0.1, 0.1, 0.1, 0.1),
        suspension_travel=(0.05, 0.05, 0.05, 0.05),
        rpm=5000,
        max_rpm=8000,
        fuel_level=0.8,
        aero_damage=0,
        engine_damage=0,
        car_flags=0,
        brake_bias=50,
        viewed_participant_index=0,
        viewed_is_ai=False,
    )


def _timings(d: float = 20.0) -> TimingsFrame:
    return TimingsFrame(
        lap_distance=d,
        current_lap=1,
        current_time=10.0,
        current_sector_time=10.0,
        sector=1,
        race_position=1,
        event_time_remaining=-1.0,
    )


def test_universal_obs_shape():
    ref = _straight_ref()
    obs = build_obs_universal(_telem(), _timings(), ref, target_speed_ms=20.0 / 3.6)
    assert obs.shape == (OBS_UNIVERSAL_DIM,)


def test_signed_cte_positive_when_right():
    ref = _straight_ref()
    obs = build_obs_universal(_telem(z=-3.0), _timings(), ref, target_speed_ms=5.0)
    assert obs[1] > 0.0  # signed_cte_norm > 0 a la derecha (-Z con heading +X)


def test_no_ref_throttle_in_universal():
    """Universal obs no tiene features de memoria de pedales de referencia."""
    assert OBS_UNIVERSAL_DIM == 17


def test_reason_vocab_and_rule():
    rid = encode_reason_id("accel_straight")
    assert rid > 0
    rule = rule_for_reason("accel_straight")
    assert rule["when"] == "speed_below_target"
    assert rule["why"] == "straight_low_curvature"
    assert normalize_reason("safety_stuck") == "safety_stuck"


def test_conditioned_obs_size():
    ref = _straight_ref()
    obs = build_obs_universal(_telem(), _timings(), ref, target_speed_ms=5.0)
    cond = build_conditioned_obs(obs, "accel_straight")
    assert cond.shape == (OBS_UNIVERSAL_DIM + NUM_REASONS,)
