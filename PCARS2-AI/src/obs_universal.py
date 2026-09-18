"""
obs_universal.py
Observación agnóstica de pista para políticas universales.

No incluye ref_throttle, ref_brake ni progress de una vuelta concreta.
La referencia solo aporta geometría relativa (CTE, curvatura, lookahead).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from obs_builder import (
    MAX_ANGULAR_VEL,
    MAX_CTE,
    MAX_CURVATURE,
    MAX_HEADING_ERR,
    MAX_LAT_ACCEL,
    MAX_LONG_ACCEL,
    MAX_SPEED_DELTA,
    MAX_SPEED_MS,
    MAX_TYRE_RPS,
    TYRE_RADIUS,
)

if TYPE_CHECKING:
    from reference_recorder import ReferenceLine
    from telemetry_udp import TelemetryFrame, TimingsFrame

OBS_UNIVERSAL_DIM = 17
CURV_LOOKAHEAD_30 = 30.0
CURV_LOOKAHEAD_50 = 50.0
SPEED_LOOKAHEAD_M = 50.0

OBS_SCHEMA = "universal_v1"


def signed_lateral_error(
    ref: ReferenceLine,
    position: tuple,
    lap_distance: float,
) -> float:
    """CTE con signo: positivo = a la derecha del trazado."""
    ref_pt = ref.lookup(lap_distance)
    hv = ref.heading_vector(lap_distance)
    if ref_pt is None or hv is None:
        return 0.0
    dx = position[0] - ref_pt.position[0]
    dz = position[2] - ref_pt.position[2]
    # Proyección sobre el eje "derecha" del trazado: right = (hv_z, -hv_x)
    return dx * hv[1] - dz * hv[0]


def build_obs_universal(
    telem: TelemetryFrame,
    timings: TimingsFrame,
    ref: ReferenceLine,
    target_speed_ms: float,
) -> np.ndarray:
    """
    Vector de 17 features transferibles entre pistas.

    0  speed_norm
    1  signed_cte_norm
    2  heading_err_norm
    3  curvature_norm
    4  curv_ahead_30_norm
    5  curv_ahead_50_norm
    6  speed_delta_lookahead_norm  (velocidad futura - actual)
    7  slip_norm
    8  yaw_norm
    9  lat_norm
    10 long_norm
    11 wheelspin_norm
    12 lockup_norm
    13 throttle_cur_norm
    14 target_speed_norm
    15 rpm_norm
    16 gear_norm
    """
    d = timings.lap_distance
    speed = telem.speed

    speed_norm = np.clip(speed / MAX_SPEED_MS, 0.0, 1.0)

    signed_cte = signed_lateral_error(ref, telem.position, d)
    signed_cte_norm = np.clip(signed_cte / MAX_CTE, -1.0, 1.0)

    h_err = ref.heading_error(telem.world_velocity, d)
    heading_err_norm = np.clip(h_err / MAX_HEADING_ERR, -1.0, 1.0)

    curv = ref.curvature(d)
    curv_norm = np.clip(curv / MAX_CURVATURE, -1.0, 1.0)

    curv_30 = ref.curvature(d + CURV_LOOKAHEAD_30)
    curv_50 = ref.curvature(d + CURV_LOOKAHEAD_50)
    curv_ahead_30_norm = np.clip(curv_30 / MAX_CURVATURE, -1.0, 1.0)
    curv_ahead_50_norm = np.clip(curv_50 / MAX_CURVATURE, -1.0, 1.0)

    spd_ahead = ref.speed_lookahead(d, SPEED_LOOKAHEAD_M)
    speed_delta_lk = np.clip((spd_ahead - speed) / MAX_SPEED_DELTA, -1.0, 1.0)

    vx = telem.local_velocity[0]
    vz = telem.local_velocity[2]
    slip = math.atan2(vz, max(abs(vx), 0.1))
    slip_norm = np.clip(slip / math.pi, -1.0, 1.0)

    yaw_norm = np.clip(telem.angular_velocity[1] / MAX_ANGULAR_VEL, -1.0, 1.0)
    lat_norm = np.clip(telem.local_acceleration[2] / (MAX_LAT_ACCEL * 9.81), -1.0, 1.0)
    long_norm = np.clip(telem.local_acceleration[0] / MAX_LONG_ACCEL, -1.0, 1.0)

    expected_rps = speed / (2.0 * math.pi * TYRE_RADIUS)
    rear_rps = (telem.tyre_rps[2] + telem.tyre_rps[3]) / 2.0
    front_rps = (telem.tyre_rps[0] + telem.tyre_rps[1]) / 2.0
    wheelspin_norm = np.clip((rear_rps - expected_rps) / MAX_TYRE_RPS, -1.0, 1.0)
    lockup_norm = np.clip((expected_rps - front_rps) / MAX_TYRE_RPS, -1.0, 1.0)

    throttle_cur_norm = telem.throttle / 255.0
    target_speed_norm = np.clip(target_speed_ms / MAX_SPEED_MS, 0.0, 1.0)
    rpm_norm = np.clip(telem.rpm / max(telem.max_rpm, 1), 0.0, 1.0)
    gear_norm = np.clip(telem.gear / max(telem.num_gears, 1), 0.0, 1.0)

    return np.array([
        speed_norm,
        signed_cte_norm,
        heading_err_norm,
        curv_norm,
        curv_ahead_30_norm,
        curv_ahead_50_norm,
        speed_delta_lk,
        slip_norm,
        yaw_norm,
        lat_norm,
        long_norm,
        wheelspin_norm,
        lockup_norm,
        throttle_cur_norm,
        target_speed_norm,
        rpm_norm,
        gear_norm,
    ], dtype=np.float32)
