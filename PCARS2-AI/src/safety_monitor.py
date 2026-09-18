"""
safety_monitor.py
Detección de condiciones de seguridad compartida entre teacher e imitation driver.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from reference_recorder import ReferenceLine
from telemetry_udp import TelemetryFrame, TimingsFrame

# Umbrales alineados con environment.py (modo básicos / teaching)
GAME_FPS = 25.0
GRACE_STEPS = 250

NO_PROGRESS_DIST_M = 10.0
NO_PROGRESS_TIME_S = 30.0

STUCK_SPEED_MS = 0.4
STUCK_TIME_S = 15.0

WRONGWAY_ANGLE_RAD = math.radians(160)
WRONGWAY_TIME_S = 2.0
WRONGWAY_NEAR_FINISH_S = 0.3
PIT_ZONE_MARGIN_M = 300.0

CTE_SAFE_M = 6.0
CTE_RECOVERY_M = 8.0
CTE_PIT_M = 20.0


def _frames(seconds: float) -> int:
    return max(1, int(seconds * GAME_FPS))


@dataclass
class SafetyStatus:
    active: bool = False
    reason: str = ""
    cte: float = 0.0
    heading_err: float = 0.0
    stuck_steps: int = 0
    wrongway_steps: int = 0


@dataclass
class SafetyMonitor:
    """Monitor de seguridad determinista por frames de juego."""

    ref: ReferenceLine
    grace_steps: int = GRACE_STEPS
    stuck_speed_ms: float = STUCK_SPEED_MS
    stuck_max_steps: int = field(default_factory=lambda: _frames(STUCK_TIME_S))
    no_progress_max_steps: int = field(default_factory=lambda: _frames(NO_PROGRESS_TIME_S))
    wrongway_max_steps: int = field(default_factory=lambda: _frames(WRONGWAY_TIME_S))
    wrongway_finish_steps: int = field(default_factory=lambda: _frames(WRONGWAY_NEAR_FINISH_S))

    step_count: int = 0
    stuck_steps: int = 0
    wrongway_steps: int = 0
    progress_dist: float = 0.0
    progress_step: int = 0
    prev_check_lap: int = -1
    max_cte_seen: float = 0.0
    last_reason: str = ""

    def reset(self, lap_distance: float = 0.0, current_lap: int = 0) -> None:
        self.step_count = 0
        self.stuck_steps = 0
        self.wrongway_steps = 0
        self.progress_dist = lap_distance
        self.progress_step = 0
        self.prev_check_lap = current_lap
        self.max_cte_seen = 0.0
        self.last_reason = ""

    def update(
        self,
        telem: TelemetryFrame,
        timings: TimingsFrame,
    ) -> SafetyStatus:
        self.step_count += 1
        cte = self.ref.cross_track_error(telem.position, timings.lap_distance)
        if cte > self.max_cte_seen:
            self.max_cte_seen = cte

        heading_err = self.ref.heading_error(telem.world_velocity, timings.lap_distance)
        status = SafetyStatus(cte=cte, heading_err=heading_err)

        if self.step_count <= self.grace_steps:
            return status

        d = timings.lap_distance
        tlen = self.ref.track_length
        near_meta = d < 100.0 or d > tlen - 100.0
        if cte > CTE_PIT_M and near_meta:
            status.active = True
            status.reason = "pit_box"
            self.last_reason = status.reason
            return status

        if telem.speed < self.stuck_speed_ms:
            self.stuck_steps += 1
            status.stuck_steps = self.stuck_steps
            if self.stuck_steps >= self.stuck_max_steps:
                status.active = True
                status.reason = "stuck"
                self.last_reason = status.reason
                return status
        else:
            self.stuck_steps = 0

        lap_dist = timings.lap_distance
        cur_lap = timings.current_lap
        if cur_lap != self.prev_check_lap:
            self.progress_dist = lap_dist
            self.progress_step = self.step_count
            self.prev_check_lap = cur_lap
        elif lap_dist > self.progress_dist + NO_PROGRESS_DIST_M:
            self.progress_dist = lap_dist
            self.progress_step = self.step_count
        elif (self.step_count - self.progress_step) >= self.no_progress_max_steps:
            status.active = True
            status.reason = "no_progress"
            self.last_reason = status.reason
            return status

        if telem.speed > 2.0:
            ref_yaw = self.ref.heading_at(timings.lap_distance)
            agent_yaw = telem.orientation[2]
            diff = agent_yaw - ref_yaw
            h_err_abs = abs(math.atan2(math.sin(diff), math.cos(diff)))
            if h_err_abs > WRONGWAY_ANGLE_RAD:
                self.wrongway_steps += 1
                status.wrongway_steps = self.wrongway_steps
                near_finish = d < PIT_ZONE_MARGIN_M or d > tlen - PIT_ZONE_MARGIN_M
                max_steps = self.wrongway_finish_steps if near_finish else self.wrongway_max_steps
                if self.wrongway_steps >= max_steps:
                    status.active = True
                    status.reason = "wrong_way"
                    self.last_reason = status.reason
                    return status
            else:
                self.wrongway_steps = 0

        if cte > CTE_RECOVERY_M:
            status.active = True
            status.reason = "off_track"
            self.last_reason = status.reason
            return status

        return status


def session_tick_flags(status: SafetyStatus, cte: float) -> tuple[bool, bool]:
    """Flags unificados off_track / stuck para logs y validación."""
    off_track = status.reason in ("off_track", "pit_box") or cte >= CTE_RECOVERY_M
    stuck = status.reason in ("stuck", "no_progress")
    return off_track, stuck
