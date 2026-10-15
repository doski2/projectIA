"""
track_deviation.py
Diagnóstico de desviación respecto a la referencia (posición, CTE, terreno UDP).

Sirve para localizar por qué hay hierba con CTE moderado (~3 m): deriva lateral,
desfase lap_distance vs posición, o rueda concreta fuera de asfalto.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from obs_universal import signed_lateral_error
from pcars2_surface import (
    OFF_TRACK_TERRAIN_IDS,
    RACING_TERRAIN_IDS,
    TERRAIN_GRASS,
    any_wheel_on_off_track_terrain,
)
from reference_recorder import ReferenceLine
from telemetry_udp import TelemetryFrame, TimingsFrame

WHEEL_LABELS = ("FL", "FR", "RL", "RR")


def closest_on_reference(
    ref: ReferenceLine,
    position: Tuple[float, float, float],
    hint_lap_distance: float,
    window_m: float = 120.0,
) -> Tuple[float, float, float]:
    """
    Busca el punto de la polyline más cercano a `position` cerca de `hint_lap_distance`.

    Returns:
        (best_lap_distance, signed_lateral_m, euclidean_m)
    """
    if ref.track_length <= 0:
        return hint_lap_distance, 0.0, 0.0

    hint = hint_lap_distance % ref.track_length
    lo = int(max(0, hint - window_m))
    hi = int(min(ref.track_length - 1, hint + window_m))

    best_d = hint
    best_eucl = float("inf")
    best_signed = 0.0

    for d in range(lo, hi + 1):
        pt = ref.lookup(float(d))
        if pt is None:
            continue
        dx = position[0] - pt.position[0]
        dz = position[2] - pt.position[2]
        eucl = math.sqrt(dx * dx + dz * dz)
        if eucl < best_eucl:
            best_eucl = eucl
            best_d = float(d)
            best_signed = signed_lateral_error(ref, position, float(d))

    return best_d, best_signed, best_eucl


def _terrain_summary(terrain: Sequence[int]) -> Dict[str, Any]:
    wheels = list(terrain[:4]) if len(terrain) >= 4 else list(terrain)
    while len(wheels) < 4:
        wheels.append(0)
    off_ids: List[str] = []
    grass_wheels: List[str] = []
    for label, tid in zip(WHEEL_LABELS, wheels, strict=True):
        t = int(tid)
        if t in OFF_TRACK_TERRAIN_IDS:
            off_ids.append(label)
        if t == TERRAIN_GRASS:
            grass_wheels.append(label)
    on_racing = sum(1 for t in wheels if int(t) in RACING_TERRAIN_IDS)
    return {
        "terrain": wheels,
        "wheels_off": off_ids,
        "wheels_grass": grass_wheels,
        "wheels_on_racing": on_racing,
        "any_off_track_terrain": any_wheel_on_off_track_terrain(wheels),
    }


def build_track_diag(
    telem: TelemetryFrame,
    timings: TimingsFrame,
    ref: ReferenceLine,
    window_m: float = 120.0,
    signed_cte_hint: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Métricas extra por tick (--diag-track). No duplica signed_cte del tick salvo
    que no se pase signed_cte_hint (p. ej. análisis offline).

    - closest_*: proyección espacial (desfase UDP lap_distance vs XY).
    - terrain: por rueda (complementa off_surface del safety).
    """
    d_hint = timings.lap_distance
    pos = telem.position
    ref_pt = ref.lookup(d_hint)

    signed_at_hint = (
        signed_cte_hint
        if signed_cte_hint is not None
        else signed_lateral_error(ref, pos, d_hint)
    )
    eucl_at_hint = ref.cross_track_error(pos, d_hint)

    closest_d, closest_signed, closest_eucl = closest_on_reference(
        ref, pos, d_hint, window_m=window_m,
    )
    dist_mismatch = closest_d - (d_hint % ref.track_length if ref.track_length else d_hint)

    diag: Dict[str, Any] = {
        "pos_x": round(pos[0], 2),
        "pos_z": round(pos[2], 2),
        "cte_euclidean": round(eucl_at_hint, 3),
        "closest_lap_distance": round(closest_d, 1),
        "closest_signed_cte": round(closest_signed, 3),
        "closest_euclidean": round(closest_eucl, 3),
        "lap_distance_mismatch_m": round(dist_mismatch, 2),
        "local_vel_x": round(float(telem.local_velocity[0]), 3),
    }
    if signed_cte_hint is None:
        diag["signed_cte"] = round(signed_at_hint, 3)

    if ref_pt is not None:
        diag["ref_x"] = round(ref_pt.position[0], 2)
        diag["ref_z"] = round(ref_pt.position[2], 2)
        diag["ref_speed_kmh"] = round(ref_pt.speed * 3.6, 2)

    diag.update(_terrain_summary(telem.terrain))
    return diag


def maybe_build_track_diag(
    enabled: bool,
    telem: TelemetryFrame,
    timings: TimingsFrame,
    ref: ReferenceLine,
    signed_cte: float,
) -> Optional[Dict[str, Any]]:
    """Un solo punto de entrada para drivers con --diag-track."""
    if not enabled:
        return None
    return build_track_diag(
        telem, timings, ref, signed_cte_hint=signed_cte,
    )
