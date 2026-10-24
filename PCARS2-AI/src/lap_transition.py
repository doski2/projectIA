"""
lap_transition.py
Durante el fine-tune el coche frena y se queda parado.
Si al parar no está la 1ª, da gas hasta engranarla y no arranca antes.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Tuple

from pcars2_gear import ENGAGE_FIRST_THROTTLE, is_reverse_gear


@dataclass
class SettleDecision:
    active: bool
    throttle: float
    brake: float
    steering: float
    skip_bc: bool
    reason: str = ""


class LapTransitionGuard:
    """Freno de meta solo mientras dura el fine-tune."""

    HOLD_BRAKE = 0.7
    STOPPED_SPEED_MS = 0.6
    # ~5 s a 60 Hz sin lograr la 1ª: soltar gas y reintentar en vez de revolucionar en N.
    ENGAGE_TIMEOUT_FRAMES = 300
    ENGAGE_RECOVER_FRAMES = 60

    def __init__(self, track_length: float = 0.0, settle_frames: int = 0):
        self.track_length = track_length
        self.settle_frames = settle_frames
        self._fine_tuning: bool = False
        self._engaging_gear: bool = False
        self._engage_frames: int = 0
        self._recover_frames: int = 0
        self.engage_timeouts: int = 0

    def reset(self, current_lap: int = 0, lap_distance: float = 0.0) -> None:
        _ = current_lap, lap_distance
        self._fine_tuning = False
        self._engaging_gear = False
        self._engage_frames = 0
        self._recover_frames = 0
        self.engage_timeouts = 0

    @property
    def active(self) -> bool:
        return self._fine_tuning

    @property
    def fine_tuning(self) -> bool:
        return self._fine_tuning

    def set_fine_tuning(self, active: bool) -> None:
        self._fine_tuning = active
        if not active:
            self._engaging_gear = False
            self._engage_frames = 0
            self._recover_frames = 0

    def on_frame(self, current_lap: int, lap_distance: float) -> bool:
        """El cruce de meta no frena. La parada la abre set_fine_tuning."""
        _ = current_lap, lap_distance
        return self.active

    def apply(
        self,
        teacher_tuple: Tuple[float, float, float],
        proposed: Tuple[float, float, float],
        speed_ms: float = 0.0,
        gear: int = 1,
    ) -> SettleDecision:
        if not self._fine_tuning:
            return SettleDecision(
                active=False,
                throttle=proposed[0],
                brake=proposed[1],
                steering=proposed[2],
                skip_bc=False,
            )

        if gear == 1 or is_reverse_gear(gear):
            self._engaging_gear = False
            self._engage_frames = 0
        elif speed_ms < self.STOPPED_SPEED_MS:
            self._engaging_gear = True

        if self._engaging_gear and self._recover_frames == 0:
            self._engage_frames += 1
            if self._engage_frames > self.ENGAGE_TIMEOUT_FRAMES:
                self._engage_frames = 0
                self._recover_frames = self.ENGAGE_RECOVER_FRAMES
                self.engage_timeouts += 1
                print(
                    f"[Settle] No engrana 1ª (gear={gear}); suelto gas y reintento "
                    f"(fallo {self.engage_timeouts}). Si persiste, mete la 1ª a mano.",
                    file=sys.stderr,
                )

        if self._recover_frames > 0:
            self._recover_frames -= 1
            return self._decision(teacher_tuple, 0.0, self.HOLD_BRAKE, "fine_tune")
        if self._engaging_gear:
            return self._decision(teacher_tuple, ENGAGE_FIRST_THROTTLE, 0.0, "fine_tune_gear")
        return self._decision(teacher_tuple, 0.0, self.HOLD_BRAKE, "fine_tune")

    @staticmethod
    def _decision(
        teacher_tuple: Tuple[float, float, float],
        throttle: float,
        brake: float,
        reason: str,
    ) -> SettleDecision:
        return SettleDecision(
            active=True,
            throttle=throttle,
            brake=brake,
            steering=teacher_tuple[2],
            skip_bc=True,
            reason=reason,
        )
