"""Tests de diagnóstico de desviación lateral."""

import math

from reference_recorder import ReferenceLine, ReferencePoint
from track_deviation import build_track_diag, closest_on_reference
from telemetry_udp import TelemetryFrame, TimingsFrame


def _straight_ref(length: int = 200) -> ReferenceLine:
    points = []
    for d in range(length):
        points.append(
            ReferencePoint(
                lap_distance=float(d),
                position=(float(d), 0.0, 0.0),
                speed=15.0,
                throttle=100,
                brake=0,
                steering=0,
                gear=2,
                orientation=(0.0, 0.0, 0.0),
                local_velocity=(10.0, 0.0, 0.0),
            )
        )
    return ReferenceLine(
        points=points,
        track_length=float(length - 1),
        track_name="straight",
        lap_time=10.0,
    )


def _telem_at(x: float, z: float = 0.0, terrain=(0, 0, 0, 0)) -> TelemetryFrame:
    return TelemetryFrame(
        position=(x, 0.0, z),
        orientation=(0.0, 0.0, 0.0),
        local_velocity=(10.0, 0.0, 0.0),
        world_velocity=(10.0, 0.0, 0.0),
        angular_velocity=(0.0, 0.0, 0.0),
        local_acceleration=(0.0, 0.0, 0.0),
        speed=10.0,
        throttle=0,
        brake=0,
        steering=0,
        clutch=0,
        gear=2,
        num_gears=6,
        raw_throttle=0,
        raw_brake=0,
        raw_steering=0,
        tyre_temp=(0, 0, 0, 0),
        tyre_tread_temp=(0, 0, 0, 0),
        tyre_wear=(0, 0, 0, 0),
        tyre_rps=(0.0, 0.0, 0.0, 0.0),
        terrain=terrain,
        ride_height=(0.0, 0.0, 0.0, 0.0),
        suspension_travel=(0.0, 0.0, 0.0, 0.0),
        rpm=5000,
        max_rpm=8000,
        fuel_level=1.0,
        aero_damage=0,
        engine_damage=0,
        car_flags=0,
        brake_bias=50,
        viewed_participant_index=0,
        viewed_is_ai=False,
    )


def test_closest_on_reference_finds_lateral_offset():
    ref = _straight_ref()
    # 3 m de offset lateral en d=100 (signo según convención signed_lateral_error)
    telem = _telem_at(100.0, 3.0)
    d, signed, eucl = closest_on_reference(ref, telem.position, hint_lap_distance=100.0)
    assert abs(d - 100.0) < 1.0
    assert abs(abs(signed) - 3.0) < 0.05
    assert abs(eucl - 3.0) < 0.05


def test_build_track_diag_grass_wheel():
    ref = _straight_ref()
    telem = _telem_at(50.0, 0.0, terrain=(0, 0, 7, 0))
    timings = TimingsFrame(
        lap_distance=50.0,
        current_lap=1,
        current_time=1.0,
        current_sector_time=1.0,
        sector=1,
        race_position=1,
        event_time_remaining=-1.0,
    )
    diag = build_track_diag(telem, timings, ref)
    assert diag["wheels_grass"] == ["RL"]
    assert diag["any_off_track_terrain"] is True
