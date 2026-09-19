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


def evaluate_lap_for_phase(ticks: List[dict], phase_id: str) -> dict:
    if phase_id in LEARN_STAGES:
        return evaluate_lap(ticks, phase_id)
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


def completed_lap_ticks(buffer_ticks: List[dict]) -> List[dict]:
    """Tras rollover, el último tick ya es de la vuelta nueva — excluirlo."""
    if len(buffer_ticks) <= 1:
        return []
    return buffer_ticks[:-1]


def try_complete_lap(
    buffer_ticks: List[dict],
    current_lap: int,
    start_lap: int,
    laps_done: int,
    stage_id: str,
) -> Optional[LapCompleteResult]:
    """Detecta vuelta completada. Llamar después de añadir el tick del frame actual."""
    if current_lap <= start_lap + laps_done:
        return None

    completed = completed_lap_ticks(buffer_ticks)
    new_laps_done = current_lap - start_lap
    lap_eval = (
        evaluate_lap_for_phase(completed, stage_id)
        if completed
        else evaluate_lap_for_phase([], stage_id)
    )

    lap_time_s = 0.0
    if len(completed) >= 2:
        lap_time_s = max(0.0, completed[-1]["t_s"] - completed[0]["t_s"])

    m = compute_lap_metrics(completed)
    lap_overrides = m["override_count"]
    return LapCompleteResult(
        laps_done=new_laps_done,
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
) -> dict:
    return {
        "t_s": t_s,
        "speed_kmh": speed_kmh,
        "cte": cte,
        "safety_override": safety_override,
        "off_track": off_track,
        "stuck": stuck,
        "teacher_reason": teacher_reason,
    }


def rotate_lap_buffer(lap_ticks: List[dict]) -> List[dict]:
    return [lap_ticks[-1]] if lap_ticks else []


def process_lap_rollover(
    lap_ticks: List[dict],
    current_lap: int,
    start_lap: int,
    laps_done: int,
    phase_id: str,
    session_rec,
    stage_id: Optional[str] = None,
) -> Optional[LapCompleteResult]:
    """Detecta vuelta, registra evento JSONL y devuelve resultado (o None)."""
    result = try_complete_lap(lap_ticks, current_lap, start_lap, laps_done, phase_id)
    if result is None:
        return None
    session_rec.record_event(lap_event_from_result(result, stage_id=stage_id or phase_id))
    return result


def lap_event_from_result(
    result: LapCompleteResult,
    stage_id: Optional[str] = None,
) -> dict:
    ev = {
        "type": "lap",
        "lap_num": result.laps_done,
        "lap_time_s": round(result.lap_time_s, 3),
        "lap_time_fmt": format_lap_time(result.lap_time_s),
        "avg_cte": result.lap_eval.get("avg_cte"),
        "clean": result.clean,
        "overrides": result.lap_overrides,
    }
    if stage_id:
        ev["stage"] = stage_id
    return ev
