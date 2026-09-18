"""
teaching_diag.py
Logs de diagnóstico en consola y eventos JSONL para sesiones Teaching.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from auto_shift import rpm_ratio
from safety_monitor import SafetyStatus
from telemetry_udp import TelemetryFrame, TimingsFrame


@dataclass
class TeachingDiagnostics:
    """Detecta transiciones y emite logs útiles para corregir comportamiento."""

    log_every: int = 50
    prev_safety_reason: str = ""
    prev_gear: int = -1
    shift_count: int = 0
    safety_events: int = 0
    frame: int = 0

    def on_shift(self, shift_event: str, telem: TelemetryFrame) -> None:
        self.shift_count += 1
        ratio = rpm_ratio(telem) * 100.0
        print(
            f"[Shift] {shift_event} | gear {telem.gear}/{telem.num_gears or 6} "
            f"| rpm={telem.rpm} ({ratio:.0f}%) | spd={telem.speed * 3.6:.1f} km/h"
        )

    def frame_events(
        self,
        status: SafetyStatus,
        telem: TelemetryFrame,
        timings: TimingsFrame,
        cte: float,
        shift_event: Optional[str],
    ) -> List[dict]:
        """Eventos JSONL del frame (sin duplicar safety + stuck)."""
        events: List[dict] = []
        safety_ev = self._safety_change(status, telem, timings, cte)
        if safety_ev:
            events.append(safety_ev)
        if shift_event:
            events.append({
                "type": "event",
                "event": "shift",
                "shift": shift_event,
                "lap": timings.current_lap,
                "lap_distance": round(timings.lap_distance, 1),
                "gear": telem.gear,
                "rpm": telem.rpm,
            })
        if self._gear_changed(telem) and not shift_event:
            events.append({
                "type": "event",
                "event": "gear_change",
                "gear": telem.gear,
                "lap_distance": round(timings.lap_distance, 1),
            })
        return events

    def _safety_change(
        self,
        status: SafetyStatus,
        telem: TelemetryFrame,
        timings: TimingsFrame,
        cte: float,
    ) -> Optional[dict]:
        reason = status.reason if status.active else ""
        if reason == self.prev_safety_reason:
            return None

        event_type = "safety_on" if status.active else "safety_off"
        detail = {
            "type": "event",
            "event": event_type,
            "safety_reason": reason or self.prev_safety_reason,
            "lap": timings.current_lap,
            "lap_distance": round(timings.lap_distance, 1),
            "speed_kmh": round(telem.speed * 3.6, 2),
            "gear": telem.gear,
            "rpm": telem.rpm,
            "cte": round(cte, 3),
            "stuck_steps": status.stuck_steps,
        }
        label = reason or self.prev_safety_reason or "clear"
        print(
            f"[Safety] {event_type} → {label} | lap={timings.lap_distance:.0f}m "
            f"| {telem.speed * 3.6:.1f} km/h | gear={telem.gear} | CTE={cte:.1f}m "
            f"| stuck_steps={status.stuck_steps}"
        )
        self.prev_safety_reason = reason
        if status.active:
            self.safety_events += 1
        return detail

    def periodic_log(
        self,
        telem: TelemetryFrame,
        timings: TimingsFrame,
        decision_reason: str,
        cte: float,
        avg_cte: float,
        shift_event: Optional[str],
        dataset_samples: Optional[int] = None,
    ) -> None:
        self.frame += 1
        if self.frame % self.log_every != 0:
            return
        ratio = rpm_ratio(telem) * 100.0
        shift_txt = f" | shift={shift_event}" if shift_event else ""
        ds_txt = f" | DS={dataset_samples}" if dataset_samples is not None else ""
        print(
            f"  f={self.frame} | {telem.speed * 3.6:5.1f} km/h | "
            f"gear={telem.gear}/{telem.num_gears or 6} rpm={telem.rpm}({ratio:.0f}%) | "
            f"lap={timings.lap_distance:6.0f}m | CTE={cte:4.1f}m | {decision_reason}"
            f"{shift_txt}{ds_txt} | avg_cte={avg_cte:.2f}"
        )

    def _gear_changed(self, telem: TelemetryFrame) -> bool:
        changed = self.prev_gear >= 0 and telem.gear != self.prev_gear
        self.prev_gear = telem.gear
        return changed
