"""SafetyMonitor + sTerrain."""

from pcars2_surface import TERRAIN_GRASS, TERRAIN_ROAD
from reference_recorder import ReferenceLine, ReferencePoint
from safety_monitor import SafetyMonitor
from telemetry_udp import TelemetryFrame, TimingsFrame


def _ref() -> ReferenceLine:
    points = [
        ReferencePoint(
            lap_distance=float(d),
            position=(float(d), 0.0, 0.0),
            speed=15.0,
            throttle=100,
            brake=0,
            steering=0,
            gear=2,
            orientation=(0.0, 0.0, 0.0),
            local_velocity=(15.0, 0.0, 0.0),
        )
        for d in (0, 1000)
    ]
    return ReferenceLine(points=points, track_length=1000.0, track_name="test", lap_time=60.0)


def _telem(terrain) -> TelemetryFrame:
    return TelemetryFrame(
        position=(0.0, 0.0, 0.0),
        orientation=(0.0, 0.0, 0.0),
        local_velocity=(10.0, 0.0, 0.0),
        world_velocity=(10.0, 0.0, 0.0),
        angular_velocity=(0.0, 0.0, 0.0),
        local_acceleration=(0.0, 0.0, 0.0),
        speed=10.0,
        throttle=100,
        brake=0,
        steering=0,
        clutch=0,
        gear=2,
        num_gears=5,
        raw_throttle=100,
        raw_brake=0,
        raw_steering=0,
        tyre_temp=(80, 80, 80, 80),
        tyre_tread_temp=(80, 80, 80, 80),
        tyre_wear=(0, 0, 0, 0),
        tyre_rps=(10.0, 10.0, 10.0, 10.0),
        terrain=terrain,
        ride_height=(0.1, 0.1, 0.1, 0.1),
        suspension_travel=(0.05, 0.05, 0.05, 0.05),
        rpm=4000,
        max_rpm=7000,
        fuel_level=1.0,
        aero_damage=0,
        engine_damage=0,
        car_flags=0,
        brake_bias=50,
        viewed_participant_index=0,
        viewed_is_ai=False,
    )


def _timings() -> TimingsFrame:
    return TimingsFrame(
        lap_distance=500.0,
        current_lap=1,
        current_time=30.0,
        current_sector_time=10.0,
        sector=2,
        race_position=1,
        event_time_remaining=-1.0,
    )


def test_safety_triggers_off_surface_on_grass_before_cte():
    mon = SafetyMonitor(ref=_ref(), grace_steps=0)
    terrain = (TERRAIN_ROAD, TERRAIN_ROAD, TERRAIN_GRASS, TERRAIN_ROAD)
    status = mon.update(_telem(terrain), _timings())
    assert status.active is True
    assert status.reason == "off_surface"
