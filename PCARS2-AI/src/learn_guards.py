"""
learn_guards.py
Salvaguardas del aprendizaje online (learn_driver):

- SustainedCteGuard: el teacher toma el volante cuando el BC mantiene un desvío
  lateral alto durante varios segundos, antes de que pise hierba y salte el freno de safety.
- is_poor_demo: ticks de parada/recuperación que no deben entrar al buffer de fine-tune.
"""

from __future__ import annotations

from safety_monitor import GAME_FPS

CTE_SUSTAINED_M = 2.0
CTE_RELEASE_M = 1.2
CTE_SUSTAINED_S = 2.0

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
        self._steps = 0

    def reset(self) -> None:
        self.active = False
        self._steps = 0

    def update(self, cte: float) -> bool:
        cte = abs(cte)
        if self.active:
            if cte <= self.release_m:
                self.reset()
            return self.active
        if cte >= self.enter_m:
            self._steps += 1
            if self._steps >= self.hold_steps:
                self.active = True
        else:
            self._steps = 0
        return self.active


def is_poor_demo(teacher_reason: str) -> bool:
    return teacher_reason in POOR_DEMO_REASONS
