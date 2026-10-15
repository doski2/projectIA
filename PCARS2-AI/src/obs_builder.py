"""
obs_builder.py
Construcción compartida del vector de observación de 19 dimensiones.

Usado por environment.py, teaching_driver, dataset_recorder y pretrain.py
para mantener el mismo contrato OBSERVATION → ACTION.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from reference_recorder import ReferenceLine
    from telemetry_udp import TelemetryFrame, TimingsFrame

# ---------------------------------------------------------------------------
# Constantes — deben coincidir con environment.py y pretrain.py
# ---------------------------------------------------------------------------

OBS_DIM = 19

MAX_SPEED_MS = 97.0
MAX_CTE = 8.0
MAX_SPEED_DELTA = 60.0
MAX_ANGULAR_VEL = 5.0
MAX_LAT_ACCEL = 4.0
MAX_LONG_ACCEL = 50.0
MAX_TYRE_RPS = 200.0
MAX_HEADING_ERR = math.pi
MAX_CURVATURE = 0.05
TYRE_RADIUS = 0.33


def wheelspin_norm(telem: TelemetryFrame) -> float:
    expected_rps = telem.speed / (2.0 * math.pi * TYRE_RADIUS)
    rear_rps = (telem.tyre_rps[2] + telem.tyre_rps[3]) / 2.0
    return (rear_rps - expected_rps) / MAX_TYRE_RPS


def build_obs(
    telem: TelemetryFrame,
    timings: TimingsFrame,
    ref: ReferenceLine,
) -> np.ndarray:
    """Construye el vector de observación de 19 floats desde telemetría en vivo."""
    t = telem
    d = timings.lap_distance

    speed_norm = np.clip(t.speed / MAX_SPEED_MS, 0.0, 1.0)

    cte = ref.cross_track_error(t.position, d)
    cte_norm = np.clip(cte / MAX_CTE, 0.0, 1.0)

    delta_norm = np.clip(ref.speed_delta(t.speed, d) / MAX_SPEED_DELTA, -1.0, 1.0)

    vx = t.local_velocity[0]
    vz = t.local_velocity[2]
    slip = math.atan2(vz, max(abs(vx), 0.1))
    slip_norm = np.clip(slip / math.pi, -1.0, 1.0)

    yaw_norm = np.clip(t.angular_velocity[1] / MAX_ANGULAR_VEL, -1.0, 1.0)
    lat_norm = np.clip(t.local_acceleration[2] / (MAX_LAT_ACCEL * 9.81), -1.0, 1.0)
    long_norm = np.clip(t.local_acceleration[0] / MAX_LONG_ACCEL, -1.0, 1.0)

    rpm_norm = np.clip(t.rpm / max(t.max_rpm, 1), 0.0, 1.0)
    gear_norm = np.clip(t.gear / max(t.num_gears, 1), 0.0, 1.0)

    h_err = ref.heading_error(t.world_velocity, d)
    heading_err_norm = np.clip(h_err / MAX_HEADING_ERR, -1.0, 1.0)

    curv = ref.curvature(d)
    curv_norm = np.clip(curv / MAX_CURVATURE, -1.0, 1.0)

    spd_lk50 = np.clip(ref.speed_lookahead(d, 50.0) / MAX_SPEED_MS, 0.0, 1.0)
    spd_lk100 = np.clip(ref.speed_lookahead(d, 100.0) / MAX_SPEED_MS, 0.0, 1.0)

    ref_thr = ref.reference_throttle(d)
    ref_brk = ref.reference_brake(d)

    front_rps_avg = (t.tyre_rps[0] + t.tyre_rps[1]) / 2.0
    expected_rps = t.speed / (2.0 * math.pi * TYRE_RADIUS)
    wheelspin_norm_val = np.clip(wheelspin_norm(t), -1.0, 1.0)
    lockup_norm = np.clip((expected_rps - front_rps_avg) / MAX_TYRE_RPS, -1.0, 1.0)

    throttle_cur_norm = t.throttle / 255.0

    progress = 0.0
    if ref.track_length > 0:
        progress = np.clip(d / ref.track_length, 0.0, 1.0)

    return np.array([
        speed_norm,
        cte_norm,
        delta_norm,
        slip_norm,
        yaw_norm,
        lat_norm,
        long_norm,
        rpm_norm,
        gear_norm,
        heading_err_norm,
        curv_norm,
        spd_lk50,
        spd_lk100,
        ref_thr,
        ref_brk,
        wheelspin_norm_val,
        lockup_norm,
        throttle_cur_norm,
        progress,
    ], dtype=np.float32)


def empty_obs() -> np.ndarray:
    return np.zeros(OBS_DIM, dtype=np.float32)


def encode_action(throttle: float, brake: float, steering: float) -> np.ndarray:
    """Codifica (throttle, brake, steering) en el espacio de acción [-1, 1]."""
    return np.array([
        2.0 * throttle - 1.0,
        2.0 * brake - 1.0,
        steering,
    ], dtype=np.float32)


def encoded_action_tuple(throttle: float, brake: float, steering: float) -> tuple:
    """Como encode_action pero devuelve tuple (para dataset_recorder / JSONL)."""
    return tuple(float(x) for x in encode_action(throttle, brake, steering))
