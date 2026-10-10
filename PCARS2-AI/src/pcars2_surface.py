"""
pcars2_surface.py
Enums y helpers de sTerrain / sTyreFlags / sCarFlags (shared memory Type#9–11).

Fuente: SMS shared-memory headers (mismo enum que UDP sTerrain[4] @ offset 140).
Ver pcars2_udp_data_reference.md sección «Enums de superficie».
"""

from __future__ import annotations

from typing import Sequence

# --- sCarFlags (offset 17, 1 byte, bitmask) ---
CAR_HEADLIGHT = 1 << 0
CAR_ENGINE_ACTIVE = 1 << 1
CAR_ENGINE_WARNING = 1 << 2
CAR_SPEED_LIMITER = 1 << 3
CAR_ABS = 1 << 4
CAR_HANDBRAKE = 1 << 5

# --- sTyreFlags (per wheel, bitmask) ---
TYRE_ATTACHED = 1 << 0
TYRE_INFLATED = 1 << 1
TYRE_ON_GROUND = 1 << 2

# --- sTerrain (per wheel, enum 0..50) — nombres alineados con SharedMemory Type#11 ---
TERRAIN_ROAD = 0
TERRAIN_LOW_GRIP_ROAD = 1
TERRAIN_BUMPY_ROAD1 = 2
TERRAIN_BUMPY_ROAD2 = 3
TERRAIN_BUMPY_ROAD3 = 4
TERRAIN_MARBLES = 5
TERRAIN_GRASSY_BERMS = 6
TERRAIN_GRASS = 7
TERRAIN_GRAVEL = 8
TERRAIN_BUMPY_GRAVEL = 9
TERRAIN_RUMBLE_STRIPS = 10
TERRAIN_DRAINS = 11
TERRAIN_TYREWALLS = 12
TERRAIN_CEMENTWALLS = 13
TERRAIN_GUARDRAILS = 14
TERRAIN_SAND = 15
TERRAIN_BUMPY_SAND = 16
TERRAIN_DIRT = 17
TERRAIN_BUMPY_DIRT = 18
TERRAIN_DIRT_ROAD = 19
TERRAIN_BUMPY_DIRT_ROAD = 20
TERRAIN_PAVEMENT = 21
TERRAIN_DIRT_BANK = 22
TERRAIN_WOOD = 23
TERRAIN_DRY_VERGE = 24
TERRAIN_EXIT_RUMBLE_STRIPS = 25
TERRAIN_GRASSCRETE = 26
TERRAIN_LONG_GRASS = 27
TERRAIN_SLOPE_GRASS = 28
TERRAIN_COBBLES = 29
TERRAIN_SAND_ROAD = 30
TERRAIN_RUNOFF_ROAD = 46
TERRAIN_ILLEGAL_STRIP = 47
TERRAIN_PAINT_CONCRETE_ILLEGAL = 49

# Superficies donde el coche puede competir (lista CrewChief «racingSurfaces»).
RACING_TERRAIN_IDS = frozenset({
    TERRAIN_ROAD,
    TERRAIN_LOW_GRIP_ROAD,
    TERRAIN_BUMPY_ROAD1,
    TERRAIN_BUMPY_ROAD2,
    TERRAIN_BUMPY_ROAD3,
    TERRAIN_MARBLES,
    TERRAIN_COBBLES,
    TERRAIN_DRAINS,
    TERRAIN_EXIT_RUMBLE_STRIPS,
    TERRAIN_PAVEMENT,
    TERRAIN_RUMBLE_STRIPS,
    TERRAIN_SAND_ROAD,
    TERRAIN_BUMPY_DIRT_ROAD,
})

# Césped, gravel, arena, etc. — fuera de asfalto aunque el CTE a la referencia sea bajo.
OFF_TRACK_TERRAIN_IDS = frozenset({
    TERRAIN_GRASS,
    TERRAIN_GRASSY_BERMS,
    TERRAIN_GRAVEL,
    TERRAIN_BUMPY_GRAVEL,
    TERRAIN_SAND,
    TERRAIN_BUMPY_SAND,
    TERRAIN_DIRT,
    TERRAIN_BUMPY_DIRT,
    TERRAIN_LONG_GRASS,
    TERRAIN_SLOPE_GRASS,
    TERRAIN_RUNOFF_ROAD,
    TERRAIN_ILLEGAL_STRIP,
    TERRAIN_PAINT_CONCRETE_ILLEGAL,
})


def _wheel_terrains(terrain: Sequence[int]) -> Sequence[int]:
    if len(terrain) < 4:
        return terrain
    return terrain[:4]


def all_wheels_off_racing_surface(terrain: Sequence[int]) -> bool:
    """Las cuatro ruedas fuera de superficie de carrera (corte de pista, estilo CrewChief)."""
    wheels = _wheel_terrains(terrain)
    if len(wheels) < 4:
        return False
    return all(int(t) not in RACING_TERRAIN_IDS for t in wheels)


def any_wheel_on_off_track_terrain(terrain: Sequence[int]) -> bool:
    """Al menos una rueda en material claramente fuera de pista."""
    return count_off_track_wheels(terrain) > 0


def count_off_track_wheels(terrain: Sequence[int]) -> int:
    """Ruedas en césped/gravel/arena (OFF_TRACK_TERRAIN_IDS)."""
    return sum(int(t) in OFF_TRACK_TERRAIN_IDS for t in _wheel_terrains(terrain))


def count_off_racing_wheels(terrain: Sequence[int]) -> int:
    """Ruedas fuera de superficie de carrera (incluye muro, no solo hierba)."""
    wheels = _wheel_terrains(terrain)
    return sum(int(t) not in RACING_TERRAIN_IDS for t in wheels)


# strict: 1 rueda en hierba → safety.
# l1_margin: 1–2 ruedas = corregir volante/gas; 3 ruedas = freno.
SURFACE_PROFILE_STRICT = "strict"
SURFACE_PROFILE_L1_MARGIN = "l1_margin"
L1_MIN_OFF_TRACK_WHEELS = 3
L1_MIN_OFF_RACING_WHEELS = 3


def classify_surface(
    terrain: Sequence[int],
    profile: str = SURFACE_PROFILE_STRICT,
) -> tuple[str | None, bool]:
    """
    Una pasada por las ruedas.

    Returns:
        (safety_reason, edge_contact)
        safety_reason "off_surface" si hay que frenar (≥3 ruedas en l1_margin).
        edge_contact si 1 o 2 ruedas en hierba y aún no hay freno.
    """
    n_off = count_off_track_wheels(terrain)
    n_not_racing = count_off_racing_wheels(terrain)
    if profile == SURFACE_PROFILE_L1_MARGIN:
        hard = n_off >= L1_MIN_OFF_TRACK_WHEELS or n_not_racing >= L1_MIN_OFF_RACING_WHEELS
        return ("off_surface" if hard else None), (n_off >= 1 and not hard)
    hard = n_off >= 1 or (len(_wheel_terrains(terrain)) >= 4 and n_not_racing >= 4)
    return ("off_surface" if hard else None), False


def surface_off_track_reason(
    terrain: Sequence[int],
    profile: str = SURFACE_PROFILE_STRICT,
) -> str | None:
    """Razón de freno por UDP. None si no hay recuperación."""
    return classify_surface(terrain, profile)[0]


def surface_edge_contact(
    terrain: Sequence[int],
    profile: str = SURFACE_PROFILE_STRICT,
) -> bool:
    """1 o 2 ruedas en hierba sin freno (solo l1_margin)."""
    return classify_surface(terrain, profile)[1]
