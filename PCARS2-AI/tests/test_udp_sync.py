"""Sincronización UDP: clave de física y drenado de backlog."""

from unittest.mock import MagicMock

from environment import PCARS2Env
from telemetry_udp import TelemetryFrame, UDPListener


def _frame(speed: float, x: float, y: float, z: float) -> TelemetryFrame:
    return TelemetryFrame(
        position=(x, y, z),
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
        gear=1,
        num_gears=6,
        raw_throttle=0,
        raw_brake=0,
        raw_steering=0,
        tyre_temp=(0, 0, 0, 0),
        tyre_tread_temp=(0, 0, 0, 0),
        tyre_wear=(0, 0, 0, 0),
        tyre_rps=(0.0, 0.0, 0.0, 0.0),
        terrain=(0, 0, 0, 0),
        ride_height=(0.0, 0.0, 0.0, 0.0),
        suspension_travel=(0.0, 0.0, 0.0, 0.0),
        rpm=3000,
        max_rpm=8000,
        fuel_level=1.0,
        aero_damage=0,
        engine_damage=0,
        brake_bias=0,
        viewed_participant_index=0,
        viewed_is_ai=False,
    )


def test_physics_key_detects_movement():
    a = PCARS2Env._physics_key(_frame(10.0, 1.0, 2.0, 3.0))
    b = PCARS2Env._physics_key(_frame(10.0, 1.1, 2.0, 3.0))
    assert a != b


def test_physics_key_stable_for_identical_state():
    f = _frame(10.0, 1.0, 2.0, 3.0)
    assert PCARS2Env._physics_key(f) == PCARS2Env._physics_key(f)


def test_fresh_udp_stats():
    stats = PCARS2Env._fresh_udp_stats()
    assert stats["physics_frames"] == 0
    assert stats["timeouts"] == 0


def test_drain_handles_empty_socket_windows():
    """timeout=0 sin datos: Windows lanza BlockingIOError, no socket.timeout."""
    listener = UDPListener.__new__(UDPListener)
    listener._sock = MagicMock()
    listener._sock.recvfrom.side_effect = BlockingIOError(10035, "would block")
    assert listener.drain() == []
    listener._sock.recvfrom.assert_called_once()
