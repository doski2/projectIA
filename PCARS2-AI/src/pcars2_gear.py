"""
pcars2_gear.py
Marcha / sentido longitudinal (UDP sLocalVelocity X = adelante del coche).

Heurísticas compartidas teacher + auto_shift.

- RB en PCARS2 = subir marcha; LB = bajar. `should_rb_to_first` solo neutro/inválido.
- `should_downshift_toward_first`: 2..N a crawl → LB.
- `backward_allows_rb_shift`: retroceso sin 1..N enganchada (evita subir en 1ª).
- `needs_gear_engagement`: solo teacher (`engage_first`).
- `choose_bc_drive_pedals`: learn/imitation — pedales BC vs teacher (marcha).
"""

from __future__ import annotations

from typing import Tuple

from telemetry_udp import TelemetryFrame

PedalTuple = Tuple[float, float, float]

# sSpeed es magnitud; el signo real va en local_velocity[0] (longitudinal).
BACKWARD_VEL_MS = 0.35
MIN_SPEED_FOR_BACKWARD = 0.12

# Teaching ~20 km/h: no pasar de 2ª; arrancar en 1ª.
TEACHING_MAX_GEAR = 2
ENGAGE_FIRST_MAX_SPEED_MS = 2.5
ENGAGE_FIRST_THROTTLE = 0.45
# gear=0 por encima de esto avanzando = fallo del UDP (en logs aparece a 10-60 km/h).
UDP_GEAR_GLITCH_MIN_SPEED_MS = 4.0
ENGAGE_FIRST_STUCK_MAX_FRAMES = 90


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


def num_gears_safe(telem: TelemetryFrame) -> int:
    return telem.num_gears or 6


# Nibble 0xF en sGearNumGears: marcha atrás en PCARS2, no una marcha inválida.
REVERSE_GEAR = 15


def is_reverse_gear(gear: int) -> bool:
    return gear == REVERSE_GEAR


def is_forward_gear(telem: TelemetryFrame) -> bool:
    """Marcha de avance válida en UDP (1..N)."""
    n = num_gears_safe(telem)
    return 1 <= telem.gear <= n


def backward_allows_rb_shift(telem: TelemetryFrame) -> bool:
    """Retroceso longitudinal: RB solo si no hay marcha de avance (RB subiría)."""
    return is_driving_backward(telem) and not is_forward_gear(telem)


def is_udp_gear_glitch(telem: TelemetryFrame) -> bool:
    """
    UDP marca gear=0 estando en 2ª y avanzando (rpm/velocidad siguen igual de coherentes).
    Un punto muerto real no acelera: por encima de UDP_GEAR_GLITCH_MIN_SPEED_MS es un fallo
    del dato, no hay que pedir 1ª ni tomar los pedales al BC.
    """
    if telem.gear != 0 or telem.speed < UDP_GEAR_GLITCH_MIN_SPEED_MS:
        return False
    return longitudinal_velocity_ms(telem) > 0.0


def should_rb_to_first(telem: TelemetryFrame) -> bool:
    """
    Neutro o byte de marcha inválido → RB (en N engancha 1ª).
    Marcha de avance 2..N: RB sube marcha en PCARS2 — usar LB vía
    should_downshift_toward_first, no RB aunque UDP marque 6ª a crawl.
    """
    n = num_gears_safe(telem)
    g = telem.gear
    if g <= 0 or g > n:
        return True
    return False


def should_downshift_toward_first(telem: TelemetryFrame) -> bool:
    """Marcha >1ª a velocidad teaching: LB (RB desde 2ª subiría de marcha)."""
    if not is_forward_gear(telem) or telem.gear <= 1:
        return False
    if telem.gear > TEACHING_MAX_GEAR:
        return True
    return telem.speed < ENGAGE_FIRST_MAX_SPEED_MS


def needs_gear_engagement(telem: TelemetryFrame) -> bool:
    """Teacher: priorizar 1ª antes de cruise (neutro o marcha alta a crawl)."""
    if telem.gear == 1 or is_udp_gear_glitch(telem):
        return False
    if telem.gear > 1:
        return should_downshift_toward_first(telem)
    return True


def should_use_teacher_pedals(
    telem: TelemetryFrame,
    safety_override: bool,
    settling: bool = False,
) -> bool:
    """
    BC/imitation: en neutro o bajando a 1ª el teacher debe mandar gas/freno
    (engage_first). safety_override no incluye engage_first — sin esto el juego
    recibe pedales del BC y puede quedarse en N con etiqueta engage_first en log.
    """
    if settling:
        return False
    if safety_override:
        return True
    return needs_gear_engagement(telem)


def choose_bc_drive_pedals(
    bc_tuple: PedalTuple,
    teacher_tuple: PedalTuple,
    telem: TelemetryFrame,
    safety_override: bool,
    settling: bool = False,
) -> tuple[PedalTuple, str, bool]:
    """
    Pedales aplicados cuando el BC predice pero el teacher define engage_first.
    Devuelve (pedales, drive_source, incrementar contador override).
    """
    if should_use_teacher_pedals(telem, safety_override, settling):
        src = "teacher" if safety_override else "teacher:gear"
        return teacher_tuple, src, safety_override
    return bc_tuple, "bc", False


# ~1,4 km/h por encima del objetivo antes de cortar el gas del BC.
SPEED_CAP_GRACE_MS = 0.4


def cap_bc_to_speed_target(
    proposed: PedalTuple,
    speed_ms: float,
    target_ms: float,
) -> tuple[PedalTuple, bool]:
    """
    El BC no puede pasar el objetivo de la banda: gas a 0 y freno según el exceso.
    El volante del propuesto se mantiene (en L1 la línea sigue siendo del BC).
    """
    if target_ms <= 0 or speed_ms <= target_ms + SPEED_CAP_GRACE_MS:
        return proposed, False
    over_ms = speed_ms - target_ms
    brake = min(1.0, 0.25 + over_ms / 6.0)
    return (0.0, max(proposed[1], brake), proposed[2]), True


def throttle_for_shift(telem: TelemetryFrame, throttle: float) -> float:
    """
    Gas mínimo para auto_shift en neutro (RB a 1ª).
    El teacher ya usa ENGAGE_FIRST_THROTTLE en engage_first; esto cubre rampas
    suaves, safety_reverse→cruise y stall sin etiqueta engage_first.
    """
    if telem.gear <= 0:
        return max(throttle, ENGAGE_FIRST_THROTTLE)
    return throttle
