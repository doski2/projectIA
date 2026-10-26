import struct
from types import SimpleNamespace

from telemetry_udp import (
    PACKET_GAME_STATE,
    GameStateFrame,
    apply_packet,
    parse_game_state,
    parse_telemetry,
)


def _physics_packet() -> bytearray:
    d = bytearray(556)
    d[10] = 0
    pk = struct.pack_into
    pk("4B", d, 136, 7, 7, 5, 7)            # sTyreFlags
    pk("4f", d, 180, 0.01, 0.02, 0.03, 0.04)  # sTyreHeightAboveGround
    pk("4B", d, 200, 1, 2, 3, 4)            # sBrakeDamage
    pk("4B", d, 204, 5, 6, 7, 8)            # sSuspensionDamage
    pk("4h", d, 208, 150, -20, 400, 999)    # sBrakeTempCelsius (con signo)
    pk("4f", d, 328, 0.1, -0.2, 0.3, -0.4)  # sSuspensionVelocity
    pk("4H", d, 352, 151, 152, 139, 140)    # sAirPressure
    pk("f", d, 364, 123.5)                  # sEngineTorque
    d[47] = 3                               # sCrashState
    d[555] = 200                            # sTickCount
    return d


def test_parse_telemetry_tanda_2():
    t = parse_telemetry(bytes(_physics_packet()))
    assert t is not None
    assert t.tyre_flags == (7, 7, 5, 7)
    assert [round(v, 2) for v in t.tyre_height_above_ground] == [0.01, 0.02, 0.03, 0.04]
    assert t.brake_damage == (1, 2, 3, 4) and t.suspension_damage == (5, 6, 7, 8)
    assert t.brake_temp == (150, -20, 400, 999)
    assert [round(v, 1) for v in t.suspension_velocity] == [0.1, -0.2, 0.3, -0.4]
    assert t.air_pressure == (151, 152, 139, 140)
    assert t.engine_torque == 123.5 and t.crash_state == 3 and t.tick_count == 200


def test_tanda_2_no_pisa_campos_ya_conocidos():
    d = _physics_packet()
    struct.pack_into("4B", d, 176, 80, 81, 82, 83)       # sTyreTemp
    struct.pack_into("4B", d, 196, 10, 11, 12, 13)       # sTyreWear
    struct.pack_into("4f", d, 160, 1.0, 2.0, 3.0, 4.0)   # sTyreRPS
    t = parse_telemetry(bytes(d))
    assert t is not None
    assert t.tyre_temp == (80, 81, 82, 83) and t.tyre_wear == (10, 11, 12, 13)
    assert t.tyre_rps == (1.0, 2.0, 3.0, 4.0) and t.tyre_flags == (7, 7, 5, 7)


def _game_state_packet() -> bytes:
    d = bytearray(24)
    d[10] = PACKET_GAME_STATE
    struct.pack_into("b", d, 15, 14)    # ambiente
    struct.pack_into("b", d, 16, -3)    # pista
    d[17] = 120                          # lluvia
    d[18] = 0
    struct.pack_into("3b", d, 19, 12, -5, 7)
    return bytes(d)


def test_parse_game_state():
    g = parse_game_state(_game_state_packet())
    assert g == GameStateFrame(14, -3, 120, 0, 12, -5, 7, raw=_game_state_packet()[12:24])
    assert parse_game_state(b"\x00" * 10) is None


def test_apply_packet_guarda_game_state():
    s, g = SimpleNamespace(game_state=None), parse_game_state(_game_state_packet())
    assert apply_packet(s, PACKET_GAME_STATE, g) == "other" and s.game_state is g
