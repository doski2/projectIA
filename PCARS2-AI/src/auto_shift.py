"""
auto_shift.py
Gestión automática de marchas compartida entre teaching_driver y environment.

PCARS2 en manual: no spamear RB/LB cada frame — cooldown y prioridad
neutral/alta → 1ª antes de upshift en movimiento.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Protocol

from pcars2_gear import is_driving_backward
from telemetry_udp import TelemetryFrame

UPSHIFT_RPM_RATIO = 0.87
DOWNSHIFT_RPM_RATIO = 0.40
THROTTLE_ACTIVE = 0.05
BRAKE_ACTIVE = 0.1
STALL_SPEED_MS = 0.5
SHIFT_COOLDOWN_S = 0.18


class ShiftController(Protocol):
    def press_button(self, button: str) -> None: ...
    def apply_action(self, throttle: float, brake: float, steering: float) -> None: ...


def rpm_ratio(telem: TelemetryFrame) -> float:
    if telem.max_rpm <= 0:
        return 0.0
    return telem.rpm / telem.max_rpm


@dataclass
class AutoShifter:
    """Estado de cambios: un botón por cooldown y sin RB/LB contradictorios."""

    cooldown_s: float = SHIFT_COOLDOWN_S
    last_shift_t: float = 0.0

    def ready(self) -> bool:
        return time.monotonic() - self.last_shift_t >= self.cooldown_s

    def _press(self, controller: ShiftController, button: str) -> None:
        controller.press_button(button)
        self.last_shift_t = time.monotonic()

    def shift(
        self,
        controller: ShiftController,
        telem: TelemetryFrame,
        throttle: float,
        brake: float,
    ) -> Optional[str]:
        """
        Devuelve: from_reverse, to_first, down_to_first, up, down, o None.

        Prioridad: marcha atrás → neutro+gas → parado en marcha alta → cambios en marcha.
        """
        if telem.max_rpm == 0:
            return None

        ratio = rpm_ratio(telem)
        gear = telem.gear
        num_gears = telem.num_gears or 6
        stalled = telem.speed < STALL_SPEED_MS

        if not self.ready():
            return None

        # RB hacia 1ª: atrás (sin LB) o neutro con gas (también con velocidad residual tras esses).
        backward = is_driving_backward(telem)
        if backward or (gear <= 0 and throttle > THROTTLE_ACTIVE):
            self._press(controller, "rb")
            return "from_reverse" if backward else "to_first"

        # Parado en marcha alta: bajar (nunca RB y LB en el mismo tick).
        if stalled and throttle > THROTTLE_ACTIVE and gear > 1:
            self._press(controller, "lb")
            return "down_to_first"

        if throttle > THROTTLE_ACTIVE and ratio > UPSHIFT_RPM_RATIO and gear < num_gears:
            self._press(controller, "rb")
            return "up"

        if (
            brake > BRAKE_ACTIVE
            and gear > 1
            and ratio < DOWNSHIFT_RPM_RATIO
            and telem.speed >= STALL_SPEED_MS
        ):
            self._press(controller, "lb")
            return "down"

        return None


def auto_shift(
    controller: ShiftController,
    telem: TelemetryFrame,
    throttle: float,
    brake: float,
    shifter: AutoShifter,
) -> Optional[str]:
    return shifter.shift(controller, telem, throttle, brake)


def maybe_engage_first_gear(
    controller: ShiftController,
    shifter: AutoShifter,
    get_telem,
    sync_frame,
    enabled: bool,
    label: str = "Driver",
) -> None:
    """Arranque compartido teaching / imitation."""
    if not enabled:
        return
    telem = get_telem()
    if telem is None or telem.gear == 1:
        return
    print(f"[{label}] Engaging 1st gear (current gear={telem.gear})...")
    ok = engage_first_gear(controller, shifter, get_telem, sync_frame)
    print(f"[{label}] 1st gear: {'OK' if ok else 'still trying — check manual mode'}")


def engage_first_gear(
    controller: ShiftController,
    shifter: AutoShifter,
    get_telem,
    sync_frame,
    max_steps: int = 80,
) -> bool:
    """
    Secuencia de arranque (como environment reset): gas + bajar a 1ª.
    get_telem() → TelemetryFrame | None; sync_frame() → bool.
    """
    for _ in range(max_steps):
        if not sync_frame():
            continue
        telem = get_telem()
        if telem is None:
            continue
        backward = is_driving_backward(telem)
        if telem.gear == 1 and telem.speed >= STALL_SPEED_MS and not backward:
            return True
        if backward:
            controller.apply_action(0.0, 0.45, 0.0)
            shifter.shift(controller, telem, 0.0, 0.45)
        else:
            controller.apply_action(0.45, 0.0, 0.0)
            shifter.shift(controller, telem, 0.45, 0.0)
    telem = get_telem()
    return telem is not None and telem.gear == 1
