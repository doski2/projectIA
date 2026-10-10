"""
lap_session.py
Lógica compartida de cierre de vuelta (learn / imitation / teaching).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from lap_tracker import format_lap_time
from learning_curriculum import LEARN_STAGES, DEFAULT_LEARN_STAGE, evaluate_lap
from validation_phases import (
    PHASES,
    compute_lap_metrics,
    evaluate_imitation_lap,
    evaluate_teaching_lap,
)

LAP_DISTANCE_WRAP_DROP_M = 80.0
MIN_LAP_TICKS_FOR_EVAL = 10


def lap_rollover_detected(
    prev_lap: int,
    prev_d: float,
    current_lap: int,
    lap_distance: float,
    wrap_drop_m: float = LAP_DISTANCE_WRAP_DROP_M,
) -> tuple[bool, Optional[int]]:
    """
    Detecta cierre de vuelta. Devuelve (rolled, completed_lap_num).

    completed_lap_num identifica la vuelta terminada para no contar dos veces
    si UDP manda primero wrap de distancia y después incremento de current_lap.
    """
    lap_inc = prev_lap >= 0 and current_lap > prev_lap
    dist_wrap = prev_d > 0.0 and lap_distance < prev_d - wrap_drop_m
    if lap_inc:
        return True, current_lap - 1
    if dist_wrap:
        return True, prev_lap if prev_lap >= 0 else current_lap
    return False, None


def evaluate_lap_for_phase(
    ticks: List[dict],
    phase_id: str,
    speed_band_kmh: float = 0.0,
) -> dict:
    if phase_id in LEARN_STAGES:
        return evaluate_lap(ticks, phase_id, speed_band_kmh=speed_band_kmh)
    if phase_id in PHASES:
        return evaluate_teaching_lap(ticks, phase_id)
    if phase_id.startswith("imit_"):
        return evaluate_imitation_lap(ticks)
    return evaluate_lap(ticks, DEFAULT_LEARN_STAGE)


@dataclass
class LapCompleteResult:
    laps_done: int
    lap_eval: dict
    lap_time_s: float
    lap_overrides: int

    @property
    def clean(self) -> bool:
        return bool(self.lap_eval.get("clean"))


def is_settle_drive_source(drive_source: Optional[str]) -> bool:
    return bool(drive_source and str(drive_source).startswith("settle:"))


def is_settle_tick(tick: dict) -> bool:
    """Meta/fine-tune: buffer de vuelta (`settling`) o JSONL de sesión (`drive_source`)."""
    if tick.get("settling"):
        return True
    return is_settle_drive_source(tick.get("drive_source"))


def driving_ticks_for_eval(ticks: List[dict]) -> List[dict]:
    """Excluye ticks de meta/fine-tune (vel. media L2, stuck, resumen sesión)."""
    return [t for t in ticks if not is_settle_tick(t)]


def driving_ticks_for_session_eval(ticks: List[dict]) -> List[dict]:
    return driving_ticks_for_eval(ticks)


def driving_ticks_for_lap_eval(ticks: List[dict]) -> List[dict]:
    return driving_ticks_for_eval(ticks)


def lap_tick_safety_flags(
    status,
    cte: float,
    settling: bool,
):
    """Flags off_track/stuck para evaluación de vuelta (no penalizar meta/fine-tune)."""
    from safety_monitor import TickSafetyFlags, session_tick_flags

    if settling:
        return TickSafetyFlags(False, False, False, False)
    return session_tick_flags(status, cte)


def completed_lap_ticks(buffer_ticks: List[dict]) -> List[dict]:
    """Tras rollover, el último tick ya es de la vuelta nueva — excluirlo."""
    if len(buffer_ticks) <= 1:
        return []
    return buffer_ticks[:-1]


class LapCompletionTracker:
    """
    Detecta cierre de vuelta por incremento de current_lap o reset de lap_distance.

    PCARS2 a veces no incrementa current_lap al cruzar meta; lap_distance sí hace wrap.
    LapTransitionGuard ya frenaba en ese caso, pero el contador de vueltas no avanzaba.
    """

    def __init__(self, wrap_drop_m: float = LAP_DISTANCE_WRAP_DROP_M):
        self.wrap_drop_m = wrap_drop_m
        self.laps_done = 0
        self._prev_lap = -1
        self._prev_d = 0.0
        self._last_completed_lap_num = -1
        self._ready = False

    def reset(self, current_lap: int = 0, lap_distance: float = 0.0) -> None:
        self.laps_done = 0
        self._prev_lap = current_lap
        self._prev_d = lap_distance
        self._last_completed_lap_num = current_lap - 1
        self._ready = True

    def on_frame(self, current_lap: int, lap_distance: float) -> bool:
        """True si se completó una vuelta en este frame."""
        if not self._ready:
            self.reset(current_lap, lap_distance)
            return False

        rolled, completed_lap_num = lap_rollover_detected(
            self._prev_lap, self._prev_d, current_lap, lap_distance, self.wrap_drop_m,
        )
        self._prev_lap = current_lap
        self._prev_d = lap_distance

        if (
            rolled
            and completed_lap_num is not None
            and completed_lap_num > self._last_completed_lap_num
        ):
            self._last_completed_lap_num = completed_lap_num
            self.laps_done += 1
            return True
        return False


def try_complete_lap(
    buffer_ticks: List[dict],
    laps_done: int,
    stage_id: str,
    speed_band_kmh: float = 0.0,
) -> LapCompleteResult:
    """Evalúa la vuelta recién cerrada. Llamar solo tras LapCompletionTracker.on_frame()."""
    completed = completed_lap_ticks(buffer_ticks)
    driving = driving_ticks_for_lap_eval(completed)
    if len(driving) < MIN_LAP_TICKS_FOR_EVAL:
        lap_eval = {
            "clean": False,
            "avg_cte": 0.0,
            "pct_override": 0.0,
            "pct_brake": 0.0,
            "summary": (
                f"pocos datos de conducción ({len(driving)} ticks; "
                f"{len(completed)} total con meta/fine-tune)"
            ),
        }
        return LapCompleteResult(
            laps_done=laps_done,
            lap_eval=lap_eval,
            lap_time_s=0.0,
            lap_overrides=0,
        )
    lap_eval = evaluate_lap_for_phase(driving, stage_id, speed_band_kmh=speed_band_kmh)

    lap_time_s = 0.0
    if len(driving) >= 2:
        lap_time_s = max(0.0, driving[-1]["t_s"] - driving[0]["t_s"])

    m = compute_lap_metrics(driving)
    lap_overrides = m["override_count"]
    return LapCompleteResult(
        laps_done=laps_done,
        lap_eval=lap_eval,
        lap_time_s=lap_time_s,
        lap_overrides=lap_overrides,
    )


def make_lap_buffer_tick(
    t_s: float,
    speed_kmh: float,
    cte: float,
    safety_override: bool,
    off_track: bool,
    stuck: bool,
    teacher_reason: str,
    settling: bool = False,
    off_surface: bool = False,
    off_track_cte: bool = False,
) -> dict:
    return {
        "t_s": t_s,
        "speed_kmh": speed_kmh,
        "cte": cte,
        "safety_override": safety_override,
        "off_track": off_track,
        "off_surface": off_surface,
        "off_track_cte": off_track_cte,
        "stuck": stuck,
        "teacher_reason": teacher_reason,
        "settling": settling,
    }


def rotate_lap_buffer(lap_ticks: List[dict]) -> List[dict]:
    return [lap_ticks[-1]] if lap_ticks else []


def process_lap_rollover(
    lap_ticks: List[dict],
    current_lap: int,
    lap_distance: float,
    tracker: LapCompletionTracker,
    phase_id: str,
    session_rec,
    stage_id: Optional[str] = None,
    speed_band_kmh: float = 0.0,
) -> Optional[LapCompleteResult]:
    """Detecta vuelta (lap o distancia), registra evento JSONL y devuelve resultado."""
    if not tracker.on_frame(current_lap, lap_distance):
        return None
    result = try_complete_lap(
        lap_ticks, tracker.laps_done, phase_id,
        speed_band_kmh=speed_band_kmh,
    )
    session_rec.record_event(lap_event_from_result(
        result,
        stage_id=stage_id or phase_id,
        speed_band_kmh=speed_band_kmh,
    ))
    return result


def lap_event_from_result(
    result: LapCompleteResult,
    stage_id: Optional[str] = None,
    speed_band_kmh: float = 0.0,
) -> dict:
    ev = {
        "type": "lap",
        "lap_num": result.laps_done,
        "lap_time_s": round(result.lap_time_s, 3),
        "lap_time_fmt": format_lap_time(result.lap_time_s),
        "avg_cte": result.lap_eval.get("avg_cte"),
        "clean": result.clean,
        "summary": result.lap_eval.get("summary", ""),
        "overrides": result.lap_overrides,
        "pct_override": result.lap_eval.get("pct_override"),
        "pct_off_track": result.lap_eval.get("pct_off_track"),
        "pct_off_surface": result.lap_eval.get("pct_off_surface"),
        "pct_off_track_cte": result.lap_eval.get("pct_off_track_cte"),
        "pct_stuck": result.lap_eval.get("pct_stuck"),
        "avg_speed_kmh": result.lap_eval.get("avg_speed_kmh"),
    }
    if stage_id:
        ev["stage"] = stage_id
    if speed_band_kmh > 0:
        ev["speed_band_kmh"] = speed_band_kmh
    return ev
