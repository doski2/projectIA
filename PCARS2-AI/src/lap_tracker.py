"""
lap_tracker.py
Mide tiempo de vuelta desde timestamps de sesión (monotonic).
"""

from __future__ import annotations

from typing import List, Optional


def format_lap_time(seconds: float) -> str:
    if seconds <= 0:
        return "—"
    mins = int(seconds // 60)
    secs = seconds % 60
    if mins > 0:
        return f"{mins}:{secs:06.3f}"
    return f"{secs:.3f}s"


class LapTracker:
    """Detecta cierre de vuelta por incremento de current_lap."""

    def __init__(self, start_lap: int = 0):
        self._prev_lap = start_lap
        self._lap_start_t: Optional[float] = None
        self.completed: List[dict] = []

    def on_frame(self, t_s: float, current_lap: int) -> Optional[dict]:
        if self._lap_start_t is None:
            self._lap_start_t = t_s
            self._prev_lap = current_lap
            return None

        if current_lap > self._prev_lap:
            lap_time = max(0.0, t_s - self._lap_start_t)
            event = {
                "type": "lap",
                "lap_num": self._prev_lap,
                "lap_time_s": round(lap_time, 3),
                "lap_time_fmt": format_lap_time(lap_time),
            }
            self.completed.append(event)
            self._lap_start_t = t_s
            self._prev_lap = current_lap
            return event
        return None


def lap_time_stats(lap_events: List[dict]) -> dict:
    times = [float(e["lap_time_s"]) for e in lap_events if e.get("lap_time_s")]
    if not times:
        return {
            "count": 0,
            "best_s": None,
            "best_fmt": "—",
            "avg_s": None,
            "avg_fmt": "—",
            "last_s": None,
            "last_fmt": "—",
            "delta_last_vs_best_s": None,
            "delta_last_vs_first_s": None,
            "improving_vs_prev": None,
        }

    best = min(times)
    last = times[-1]
    first = times[0]
    avg = sum(times) / len(times)
    improving = len(times) >= 2 and last < times[-2]

    return {
        "count": len(times),
        "best_s": round(best, 3),
        "best_fmt": format_lap_time(best),
        "avg_s": round(avg, 3),
        "avg_fmt": format_lap_time(avg),
        "last_s": round(last, 3),
        "last_fmt": format_lap_time(last),
        "delta_last_vs_best_s": round(last - best, 3),
        "delta_last_vs_first_s": round(last - first, 3),
        "improving_vs_prev": improving,
    }


def compute_lap_times_from_ticks(ticks: List[dict]) -> List[dict]:
    """Fallback: estima tiempos agrupando ticks por número de vuelta."""
    by_lap: dict[int, list] = {}
    for t in ticks:
        lap = int(t.get("lap", 0))
        by_lap.setdefault(lap, []).append(t)

    events: List[dict] = []
    for lap in sorted(by_lap.keys()):
        group = by_lap[lap]
        if len(group) < 10:
            continue
        t0 = group[0].get("t_s", 0.0)
        t1 = group[-1].get("t_s", 0.0)
        lap_time = max(0.0, t1 - t0)
        events.append({
            "type": "lap",
            "lap_num": lap,
            "lap_time_s": round(lap_time, 3),
            "lap_time_fmt": format_lap_time(lap_time),
            "source": "ticks",
        })
    return events
