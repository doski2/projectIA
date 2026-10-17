"""
auto_shift.py
Gestión automática de marchas compartida entre teaching_driver y environment.

PCARS2 en manual: no spamear RB/LB cada frame — cooldown y prioridad
neutral/alta → 1ª antes de upshift en movimiento.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Protocol, Tuple

from pcars2_gear import (
    ENGAGE_FIRST_MAX_SPEED_MS,
    ENGAGE_FIRST_THROTTLE,
    TEACHING_MAX_GEAR,
    backward_allows_rb_shift,
    is_driving_backward,
    is_forward_gear,
    is_reverse_gear,
    is_udp_gear_glitch,
    num_gears_safe,
    should_downshift_toward_first,
    should_rb_to_first,
    throttle_for_shift,
)
from telemetry_udp import TelemetryFrame

UPSHIFT_RPM_RATIO = 0.87
DOWNSHIFT_RPM_RATIO = 0.40
THROTTLE_ACTIVE = 0.05
BRAKE_ACTIVE = 0.1
STALL_SPEED_MS = 0.5
SHIFT_COOLDOWN_S = 0.18
# Un 0 de pocos frames tras ir en 2ª es un fallo del UDP, no punto muerto.
NEUTRAL_BLIP_FRAMES = 4


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
    last_forward_gear: int = 0
    neutral_frames: int = 0

    def ready(self) -> bool:
        return time.monotonic() - self.last_shift_t >= self.cooldown_s

    def _observe_gear(self, telem: TelemetryFrame) -> None:
        if is_forward_gear(telem):
            self.last_forward_gear = telem.gear
            self.neutral_frames = 0
        elif telem.gear <= 0:
            self.neutral_frames += 1

    def _press(self, controller: ShiftController, button: str) -> None:
        controller.press_button(button)
        self.last_shift_t = time.monotonic()

    def _shift_toward_first(
        self,
        controller: ShiftController,
        telem: TelemetryFrame,
    ) -> Tuple[bool, Optional[str]]:
        """
        Con gas activo: gestiona N / byte inválido / marchas por encima de 1ª.
        Devuelve (handled, acción); handled=False → seguir con up/down normales.
        """
        if is_udp_gear_glitch(telem):
            return True, None
        if should_rb_to_first(telem):
            # Punto muerto: solo RB. LB en N mete la marcha atrás.
            if telem.gear <= 0:
                if self.last_forward_gear >= 1 and self.neutral_frames <= NEUTRAL_BLIP_FRAMES:
                    return True, None
                self._press(controller, "rb")
                return True, "to_first"
            # Byte inválido tras ir en 2ª: no subir con RB.
            if self.last_forward_gear >= 2:
                if self.neutral_frames <= NEUTRAL_BLIP_FRAMES:
                    return True, None
                if telem.speed < ENGAGE_FIRST_MAX_SPEED_MS:
                    self._press(controller, "lb")
                    return True, "down_to_first"
                return True, None
            self._press(controller, "rb")
            return True, "to_first"
        if should_downshift_toward_first(telem):
            self._press(controller, "lb")
            return True, "down_to_first"
        return False, None

    def shift(
        self,
        controller: ShiftController,
        telem: TelemetryFrame,
        throttle: float,
        brake: float,
    ) -> Optional[str]:
        """
        Devuelve: from_reverse, to_first, down_to_first, up, down, o None.

        Prioridad: RB retroceso (solo N) → RB neutro → LB a 1ª → up (cap) → down freno.
        """
        if telem.max_rpm == 0:
            return None

        self._observe_gear(telem)

        ratio = rpm_ratio(telem)
        gear = telem.gear
        num_gears = num_gears_safe(telem)

        if not self.ready():
            return None

        if backward_allows_rb_shift(telem):
            self._press(controller, "rb")
            return "from_reverse"

        if is_reverse_gear(telem.gear):
            self._press(controller, "rb")
            return "from_reverse"

        shift_throttle = throttle_for_shift(telem, throttle)

        if shift_throttle > THROTTLE_ACTIVE:
            handled, action = self._shift_toward_first(controller, telem)
            if handled:
                return action

        if (
            shift_throttle > THROTTLE_ACTIVE
            and ratio > UPSHIFT_RPM_RATIO
            and gear < num_gears
            and gear < TEACHING_MAX_GEAR
        ):
            self._press(controller, "rb")
            return "up"

        if (
            brake > BRAKE_ACTIVE
            and is_forward_gear(telem)
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
    Secuencia de arranque: gas + RB/LB hasta 1ª.
    get_telem() → TelemetryFrame | None; sync_frame() → bool.
    """
    for _ in range(max_steps):
        if not sync_frame():
            continue
        telem = get_telem()
        if telem is None:
            continue
        backward = is_driving_backward(telem)
        if telem.gear == 1 and not backward:
            return True
        if backward:
            controller.apply_action(0.0, 0.45, 0.0)
            shifter.shift(controller, telem, 0.0, 0.45)
        else:
            controller.apply_action(ENGAGE_FIRST_THROTTLE, 0.0, 0.0)
            shifter.shift(controller, telem, ENGAGE_FIRST_THROTTLE, 0.0)
    telem = get_telem()
    return telem is not None and telem.gear == 1
