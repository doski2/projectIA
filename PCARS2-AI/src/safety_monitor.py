"""
safety_monitor.py
Detección de condiciones de seguridad compartida entre teacher e imitation driver.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from pcars2_surface import SURFACE_PROFILE_STRICT, classify_surface
from reference_recorder import ReferenceLine
from telemetry_udp import TelemetryFrame, TimingsFrame

# Umbrales alineados con environment.py (modo básicos / teaching)
GAME_FPS = 60.0  # el juego emite a 60 Hz (t_s avanza 0,016 s por tick en los logs)
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

# Razones que marcan tick off_track en logs / evaluación (CTE geométrico o UDP sTerrain).
SAFETY_OFF_TRACK_REASONS = frozenset({"off_track", "off_surface", "pit_box"})


def _frames(seconds: float) -> int:
    return max(1, int(seconds * GAME_FPS))


@dataclass(frozen=True)
class TickSafetyFlags:
    """Flags por tick para logs, evaluación y HTML (off-track desglosado)."""

    off_track: bool
    off_surface: bool
    off_track_cte: bool
    stuck: bool


@dataclass
class SafetyStatus:
    active: bool = False
    reason: str = ""
    cte: float = 0.0
    heading_err: float = 0.0
    stuck_steps: int = 0
    wrongway_steps: int = 0
    edge_surface: bool = False


@dataclass
class SafetyMonitor:
    """Monitor de seguridad determinista por frames de juego."""

    ref: ReferenceLine
    surface_profile: str = SURFACE_PROFILE_STRICT
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

    def hold(self, timings: TimingsFrame) -> None:
        """Parada intencionada (p. ej. fine-tune): los contadores de atasco no avanzan."""
        self.stuck_steps = 0
        self.wrongway_steps = 0
        self.progress_dist = timings.lap_distance
        self.progress_step = self.step_count
        self.prev_check_lap = timings.current_lap

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
        surface_reason, edge_surface = classify_surface(telem.terrain, self.surface_profile)
        status = SafetyStatus(
            cte=cte,
            heading_err=heading_err,
            edge_surface=edge_surface,
        )

        if self.step_count <= self.grace_steps:
            return status

        # Orden relevante: cada check muta contadores y el primero que dispara corta.
        reason = (
            self._check_pit_box(cte, timings)
            or self._check_stuck(telem, status)
            or self._check_no_progress(timings)
            or self._check_wrong_way(telem, timings, status)
            or surface_reason
            or ("off_track" if cte > CTE_RECOVERY_M else None)
        )
        if reason:
            status.active = True
            status.reason = reason
            self.last_reason = reason
        return status

    def _check_pit_box(self, cte: float, timings: TimingsFrame) -> Optional[str]:
        d = timings.lap_distance
        near_meta = d < 100.0 or d > self.ref.track_length - 100.0
        return "pit_box" if cte > CTE_PIT_M and near_meta else None

    def _check_stuck(self, telem: TelemetryFrame, status: SafetyStatus) -> Optional[str]:
        if telem.speed >= self.stuck_speed_ms:
            self.stuck_steps = 0
            return None
        self.stuck_steps += 1
        status.stuck_steps = self.stuck_steps
        return "stuck" if self.stuck_steps >= self.stuck_max_steps else None

    def _check_no_progress(self, timings: TimingsFrame) -> Optional[str]:
        lap_dist = timings.lap_distance
        if timings.current_lap != self.prev_check_lap:
            self.progress_dist = lap_dist
            self.progress_step = self.step_count
            self.prev_check_lap = timings.current_lap
        elif lap_dist > self.progress_dist + NO_PROGRESS_DIST_M:
            self.progress_dist = lap_dist
            self.progress_step = self.step_count
        elif (self.step_count - self.progress_step) >= self.no_progress_max_steps:
            return "no_progress"
        return None

    def _check_wrong_way(
        self, telem: TelemetryFrame, timings: TimingsFrame, status: SafetyStatus
    ) -> Optional[str]:
        if telem.speed <= 2.0:
            return None
        d = timings.lap_distance
        diff = telem.orientation[2] - self.ref.heading_at(d)
        h_err_abs = abs(math.atan2(math.sin(diff), math.cos(diff)))
        if h_err_abs <= WRONGWAY_ANGLE_RAD:
            self.wrongway_steps = 0
            return None
        self.wrongway_steps += 1
        status.wrongway_steps = self.wrongway_steps
        tlen = self.ref.track_length
        near_finish = d < PIT_ZONE_MARGIN_M or d > tlen - PIT_ZONE_MARGIN_M
        max_steps = self.wrongway_finish_steps if near_finish else self.wrongway_max_steps
        return "wrong_way" if self.wrongway_steps >= max_steps else None


def session_tick_flags(status: SafetyStatus, cte: float) -> TickSafetyFlags:
    """Flags off_track (total), off_surface (UDP), off_track_cte (geometría) y stuck."""
    # edge_surface (1 rueda) no entra en off_surface: si no, la vuelta sigue penalizada.
    off_surface = status.reason == "off_surface"
    pit = status.reason == "pit_box"
    off_track_cte = status.reason == "off_track" or (
        cte >= CTE_RECOVERY_M and not off_surface and not pit
    )
    off_track = off_surface or off_track_cte or pit
    stuck = status.reason in ("stuck", "no_progress")
    return TickSafetyFlags(
        off_track=off_track,
        off_surface=off_surface,
        off_track_cte=off_track_cte,
        stuck=stuck,
    )


def tick_off_surface(tick: dict) -> bool:
    if tick.get("off_surface"):
        return True
    if tick.get("safety_event") == "off_surface":
        return True
    return tick.get("teacher_reason") == "safety_off_surface"


def tick_off_track_cte(tick: dict) -> bool:
    if tick.get("off_track_cte"):
        return True
    if tick_off_surface(tick):
        return False
    if tick.get("safety_event") == "off_track":
        return True
    if tick.get("safety_event") == "pit_box":
        return False
    if tick.get("off_track"):
        return True
    return abs(float(tick.get("cte", 0.0))) >= CTE_RECOVERY_M


def pct(count: int, total: int) -> float:
    return round(100.0 * count / total, 1) if total > 0 else 0.0


def off_track_pct_breakdown(ticks: List[dict]) -> dict:
    """Porcentajes off_surface / off_track_cte / total (union) para métricas y HTML."""
    n = len(ticks)
    if n == 0:
        return {
            "pct_off_track": 0.0,
            "pct_off_surface": 0.0,
            "pct_off_track_cte": 0.0,
        }
    n_surface = sum(1 for t in ticks if tick_off_surface(t))
    n_cte = sum(1 for t in ticks if tick_off_track_cte(t))
    n_total = sum(
        1 for t in ticks
        if t.get("off_track") or tick_off_surface(t) or tick_off_track_cte(t)
    )

    return {
        "pct_off_track": pct(n_total, n),
        "pct_off_surface": pct(n_surface, n),
        "pct_off_track_cte": pct(n_cte, n),
    }
