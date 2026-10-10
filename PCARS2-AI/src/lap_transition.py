"""
lap_transition.py
Detecta el cruce de meta. No frena el coche: el fine-tune es asíncrono y un
freno a 0 en la línea deja la marcha en punto muerto.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class SettleDecision:
    active: bool
    throttle: float
    brake: float
    steering: float
    skip_bc: bool
    reason: str = ""


class LapTransitionGuard:
    """Sigue el cruce de meta sin frenar. Un freno a 0 en la línea deja punto muerto."""

    DEFAULT_SETTLE_FRAMES = 90

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
        """Actualiza la vuelta anterior. Cruzar meta no activa el freno."""
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

        _ = teacher_tuple
        reason = "fine_tune" if self._fine_tuning else "finish_line"
        return SettleDecision(
            active=True,
            throttle=proposed[0],
            brake=proposed[1],
            steering=proposed[2],
            skip_bc=True,
            reason=reason,
        )
