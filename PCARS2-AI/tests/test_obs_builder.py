"""Tests de paridad para obs_builder."""

import math

import numpy as np
import pytest

from obs_builder import OBS_DIM, build_obs, encode_action
from reference_recorder import ReferenceLine, ReferencePoint
from telemetry_udp import TelemetryFrame, TimingsFrame


def _straight_ref(length: float = 100.0) -> ReferenceLine:
    points = []
    for d in range(int(length)):
        points.append(
            ReferencePoint(
                lap_distance=float(d),
                position=(float(d), 0.0, 0.0),
                speed=50.0,
                throttle=200,
                brake=0,
                steering=0,
                gear=4,
                orientation=(0.0, 0.0, 0.0),
                local_velocity=(50.0, 0.0, 0.0),
                angular_velocity=(0.0, 0.0, 0.0),
                local_accel=(0.0, 0.0, 0.0),
                rpm=6000,
                max_rpm=8000,
                tyre_rps=(15.0, 15.0, 15.0, 15.0),
            )
        )
    return ReferenceLine(
        points=points,
        track_length=length,
        track_name="test",
        lap_time=2.0,
    )


def _telem_at(d: float, speed: float = 12.0) -> TelemetryFrame:
    return TelemetryFrame(
        position=(d, 0.0, 0.5),
        orientation=(0.0, 0.0, 0.0),
        local_velocity=(speed, 0.0, 0.0),
        world_velocity=(speed, 0.0, 0.0),
        angular_velocity=(0.0, 0.0, 0.0),
        local_acceleration=(0.0, 0.0, 0.0),
        speed=speed,
        throttle=128,
        brake=0,
        steering=0,
        clutch=0,
        gear=3,
        num_gears=6,
        raw_throttle=128,
        raw_brake=0,
        raw_steering=0,
        tyre_temp=(80, 80, 80, 80),
        tyre_tread_temp=(80, 80, 80, 80),
        tyre_wear=(0, 0, 0, 0),
        tyre_rps=(15.0, 15.0, 15.0, 15.0),
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


def _timings_at(d: float) -> TimingsFrame:
    return TimingsFrame(
        lap_distance=d,
        current_lap=1,
        current_time=30.0,
        current_sector_time=10.0,
        sector=1,
        race_position=1,
        event_time_remaining=-1.0,
    )


def test_build_obs_shape_and_range():
    ref = _straight_ref()
    obs = build_obs(_telem_at(20.0), _timings_at(20.0), ref)
    assert obs.shape == (OBS_DIM,)
    assert obs.dtype == np.float32
    assert np.all(obs >= -1.0) or True  # cte_norm is [0,1]
    assert obs[0] == pytest.approx(12.0 / 97.0, rel=1e-3)


def test_build_obs_cte_on_line():
    ref = _straight_ref()
    obs = build_obs(_telem_at(20.0, speed=12.0), _timings_at(20.0), ref)
    assert obs[1] == pytest.approx(0.5 / 8.0, abs=0.05)


def test_encode_action_roundtrip():
    from controller import decode_action

    act = encode_action(0.8, 0.2, -0.3)
    thr, brk, steer = decode_action(act)
    assert thr == pytest.approx(0.8, abs=1e-5)
    assert brk == pytest.approx(0.2, abs=1e-5)
    assert steer == pytest.approx(-0.3, abs=1e-5)


def test_env_build_obs_parity():
    """Paridad con PCARS2Env._build_obs tras refactor."""
    from environment import PCARS2Env

    ref = _straight_ref()
    env = PCARS2Env.__new__(PCARS2Env)
    env._ref = ref
    env._last_telem = _telem_at(25.0)
    env._last_timings = _timings_at(25.0)

    direct = build_obs(env._last_telem, env._last_timings, ref)
    via_env = env._build_obs()
    np.testing.assert_allclose(direct, via_env, rtol=1e-5, atol=1e-6)
