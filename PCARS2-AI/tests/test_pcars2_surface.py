"""Tests de detección de superficie UDP (sTerrain)."""

from pcars2_surface import (
    TERRAIN_GRASS,
    TERRAIN_ROAD,
    all_wheels_off_racing_surface,
    any_wheel_on_off_track_terrain,
    surface_off_track_reason,
)
from safety_monitor import SafetyStatus, session_tick_flags
from teacher_intents import encode_reason_id, normalize_reason


def test_grass_triggers_off_surface():
    terrain = (TERRAIN_ROAD, TERRAIN_ROAD, TERRAIN_GRASS, TERRAIN_ROAD)
    assert any_wheel_on_off_track_terrain(terrain)
    assert surface_off_track_reason(terrain) == "off_surface"


def test_all_wheels_off_racing_surface():
    terrain = (TERRAIN_GRASS, TERRAIN_GRASS, TERRAIN_GRASS, TERRAIN_GRASS)
    assert all_wheels_off_racing_surface(terrain)
    assert surface_off_track_reason(terrain) == "off_surface"


def test_road_only_no_surface_reason():
    terrain = (TERRAIN_ROAD,) * 4
    assert surface_off_track_reason(terrain) is None


def test_off_surface_normalizes_to_same_reason_id_as_off_track():
    assert normalize_reason("safety_off_surface") == "safety_off_track"
    assert encode_reason_id("safety_off_surface") == encode_reason_id("safety_off_track")


def test_session_tick_flags_off_surface_counts_as_off_track():
    status = SafetyStatus(active=True, reason="off_surface")
    flags = session_tick_flags(status, cte=2.0)
    assert flags.off_track is True
    assert flags.off_surface is True
    assert flags.off_track_cte is False
    assert flags.stuck is False
