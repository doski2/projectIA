"""
learn_guards.py
Salvaguardas del aprendizaje online (learn_driver):

- SustainedCteGuard: el teacher toma el volante cuando el BC mantiene un desvío
  lateral alto durante varios segundos, antes de que pise hierba y salte el freno de safety.
- StuckOffTrackAbort: cierra la sesión si el coche queda parado lejos de la línea (muro/hierba).
- is_poor_demo: ticks de parada/recuperación que no deben entrar al buffer de fine-tune.
"""

from __future__ import annotations

import time
from typing import Optional

from safety_monitor import CTE_RECOVERY_M, GAME_FPS, STUCK_SPEED_MS

CTE_SUSTAINED_M = 3.5
CTE_RELEASE_M = 2.5
CTE_SUSTAINED_S = 2.0
# Trompo en curso: rumbo muy desviado y ya fuera de la línea a velocidad alta.
# El umbral sostenido llega tarde (el CTE solo roza 3,5 m en cada ciclo del zigzag).
SPIN_MIN_SPEED_MS = 11.0
SPIN_HEADING_RAD = 0.6
SPIN_CTE_M = 2.5
# Suelta el trompo solo cuando el rumbo ya se ha recuperado (evita rebotar en CTE = 2,5 m).
SPIN_RELEASE_HEADING_RAD = 0.3
# Coche parado fuera de pista (contra el muro): no tiene sentido seguir grabando.
STUCK_ABORT_S = 10.0

POOR_DEMO_REASONS = frozenset({
    "safety_off_surface",
    "safety_no_progress",
    "safety_stuck",
    "safety_reverse",
    "safety_pit_box",
})


class SustainedCteGuard:
    """Histéresis: activa tras `hold_s` con CTE >= enter_m; suelta con CTE <= release_m."""

    def __init__(
        self,
        enter_m: float = CTE_SUSTAINED_M,
        release_m: float = CTE_RELEASE_M,
        hold_s: float = CTE_SUSTAINED_S,
    ) -> None:
        self.enter_m = enter_m
        self.release_m = release_m
        self.hold_steps = max(1, int(hold_s * GAME_FPS))
        self.active = False
        self._spin = False
        self._steps = 0

    def reset(self) -> None:
        self.active = False
        self._spin = False
        self._steps = 0

    def update(self, cte: float, speed_ms: float = 0.0, heading_err: float = 0.0) -> bool:
        cte = abs(cte)
        if (
            not self.active
            and speed_ms >= SPIN_MIN_SPEED_MS
            and abs(heading_err) >= SPIN_HEADING_RAD
            and cte >= SPIN_CTE_M
        ):
            self.active = self._spin = True
            return True
        if self.active:
            recovered = abs(heading_err) < SPIN_RELEASE_HEADING_RAD or not self._spin
            if cte <= self.release_m and recovered:
                self.reset()
            return self.active
        if cte >= self.enter_m:
            self._steps += 1
            if self._steps >= self.hold_steps:
                self.active = True
        else:
            self._steps = 0
        return self.active


class StuckOffTrackAbort:
    """True tras `hold_s` seguidos parado a `cte_m` o más de la línea."""

    def __init__(
        self,
        hold_s: float = STUCK_ABORT_S,
        cte_m: float = CTE_RECOVERY_M,
        speed_ms: float = STUCK_SPEED_MS,
    ) -> None:
        self.hold_s = hold_s
        self.cte_m = cte_m
        self.speed_ms = speed_ms
        self._since: Optional[float] = None

    def reset(self) -> None:
        self._since = None

    def update(self, cte: float, speed_ms: float, now: Optional[float] = None) -> bool:
        if speed_ms >= self.speed_ms or abs(cte) < self.cte_m:
            self._since = None
            return False
        t = time.monotonic() if now is None else now
        if self._since is None:
            self._since = t
        return t - self._since >= self.hold_s


def is_poor_demo(teacher_reason: str) -> bool:
    return teacher_reason in POOR_DEMO_REASONS
