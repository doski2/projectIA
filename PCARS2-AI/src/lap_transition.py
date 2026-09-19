"""
lap_transition.py
Freno y espera al cruzar meta / durante fine-tune BC (obs inestable + cálculo bloqueante).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from lap_session import LAP_DISTANCE_WRAP_DROP_M, lap_rollover_detected


@dataclass
class SettleDecision:
    active: bool
    throttle: float
    brake: float
    steering: float
    skip_bc: bool
    reason: str = ""


class LapTransitionGuard:
    """Mantiene control seguro tras meta o mientras el BC entrena."""

    DEFAULT_SETTLE_FRAMES = 90
    WRAP_DROP_M = LAP_DISTANCE_WRAP_DROP_M

    def __init__(self, track_length: float = 0.0, settle_frames: int = DEFAULT_SETTLE_FRAMES):
        self.track_length = track_length
        self.settle_frames = settle_frames
        self._prev_lap: int = -1
        self._prev_d: float = 0.0
        self._settle_left: int = 0
        self._fine_tuning: bool = False

    def reset(self, current_lap: int = 0, lap_distance: float = 0.0) -> None:
        self._prev_lap = current_lap
        self._prev_d = lap_distance
        self._settle_left = 0
        self._fine_tuning = False

    @property
    def active(self) -> bool:
        return self._settle_left > 0 or self._fine_tuning

    def trigger_settle(self, frames: Optional[int] = None) -> None:
        self._settle_left = max(self._settle_left, frames or self.settle_frames)

    def set_fine_tuning(self, active: bool) -> None:
        self._fine_tuning = active
        if active:
            self.trigger_settle()

    def on_frame(self, current_lap: int, lap_distance: float) -> bool:
        """Detecta meta / salto de lap_distance. Devuelve True si settle activo."""
        rolled, _ = lap_rollover_detected(
            self._prev_lap, self._prev_d, current_lap, lap_distance, self.WRAP_DROP_M,
        )
        if rolled:
            self.trigger_settle()

        self._prev_lap = current_lap
        self._prev_d = lap_distance

        if self._settle_left > 0 and not self._fine_tuning:
            self._settle_left -= 1
        return self.active

    def apply(
        self,
        teacher_tuple: Tuple[float, float, float],
        proposed: Tuple[float, float, float],
    ) -> SettleDecision:
        if not self.active:
            return SettleDecision(
                active=False,
                throttle=proposed[0],
                brake=proposed[1],
                steering=proposed[2],
                skip_bc=False,
            )

        t_t, t_b, t_s = teacher_tuple
        reason = "fine_tune" if self._fine_tuning else "finish_line"
        brake = max(0.55, t_b, proposed[1])
        return SettleDecision(
            active=True,
            throttle=0.0,
            brake=brake,
            steering=t_s,
            skip_bc=True,
            reason=reason,
        )
