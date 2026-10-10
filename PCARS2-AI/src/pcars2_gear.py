"""
pcars2_gear.py
Marcha / sentido longitudinal (UDP sLocalVelocity X = adelante del coche).

Usado por teacher_controller (pedales) y auto_shift (RB/LB). Una sola definición
de «marcha atrás»; no duplicar heurísticas en resolve_teacher_decision.
"""

from __future__ import annotations

from telemetry_udp import TelemetryFrame

# sSpeed es magnitud; el signo real va en local_velocity[0] (longitudinal).
BACKWARD_VEL_MS = 0.35
MIN_SPEED_FOR_BACKWARD = 0.12


def longitudinal_velocity_ms(telem: TelemetryFrame) -> float:
    return float(telem.local_velocity[0])


def is_driving_backward(telem: TelemetryFrame) -> bool:
    """Coche moviéndose hacia atrás en su eje longitudinal (marcha atrás o empuje)."""
    if telem.speed < MIN_SPEED_FOR_BACKWARD:
        return False
    return longitudinal_velocity_ms(telem) < -BACKWARD_VEL_MS


def backward_speed_ms(telem: TelemetryFrame) -> float:
    """Velocidad longitudinal hacia atrás (0 si avanza o casi parado)."""
    return max(0.0, -longitudinal_velocity_ms(telem))


def is_forward_gear(telem: TelemetryFrame) -> bool:
    """Marchas de avance (1..N). 0 = neutro; no confiar solo en UDP para R."""
    return telem.gear >= 1
