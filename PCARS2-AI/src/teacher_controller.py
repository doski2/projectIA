"""
teacher_controller.py
Controlador por reglas que enseña conducción: steering, throttle y brake.

Patrón: ESTADO → REGLA/OBJETIVO → ACCIÓN
Cada decisión es explicable vía TeacherDecision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from obs_builder import wheelspin_norm
from pcars2_gear import (
    ENGAGE_FIRST_STUCK_MAX_FRAMES,
    ENGAGE_FIRST_THROTTLE,
    backward_speed_ms,
    is_driving_backward,
    is_forward_gear,
    needs_gear_engagement,
)
from teacher_intents import ENGAGE_FIRST_REASON, SAFETY_REVERSE_REASON
from safety_monitor import SAFETY_OFF_TRACK_REASONS
from obs_universal import signed_lateral_error
from reference_recorder import ReferenceLine
from safety_monitor import CTE_SAFE_M, SafetyMonitor, SafetyStatus
from telemetry_udp import TelemetryFrame, TimingsFrame

CURV_LOOKAHEAD_M = 30.0
# Por debajo de recover_line (6 m): recentrar antes de que una rueda toque hierba (~3 m).
LATERAL_WARN_M = 2.5
LATERAL_K_CTE_BOOST = 2.25
EDGE_K_CTE_MULT = 1.75
# Crucero y borde: gas para no caer a 0 km/h a ~20 km/h.
MAINTAIN_THROTTLE = 0.2
WHEELSPIN_THRESHOLD = 0.15
# Modelo físico de curva: curvatura mínima (recta ≈ sin límite), techo de v_lim, paso de muestreo y suelo de la consigna.
MIN_CURVATURE = 1e-4
MAX_CURVE_SPEED_MS = 100.0
CURVE_SAMPLE_M = 5.0
MIN_CURVE_TARGET_MS = 3.0
STALL_RECOVERY_SPEED_MS = 1.0
STALL_RECOVERY_REASONS = frozenset({"stuck", "no_progress"})
STALL_BRAKE_REASONS = frozenset({"stuck", "wrong_way"}) | (
    SAFETY_OFF_TRACK_REASONS - {"pit_box"}
)
# Marcha atrás: maniobrar lento y volver hacia la línea (no saturar volante).
REVERSE_CREEP_MS = 0.7
REVERSE_K_CTE = 0.20
REVERSE_K_HEADING = 0.50
REVERSE_STEER_SMOOTH = 0.45
REVERSE_BRAKE_MIN = 0.20
REVERSE_BRAKE_MAX = 0.85


def reverse_brake_target(back_v: float) -> float:
    """Freno objetivo al retroceder: limitar a ~REVERSE_CREEP_MS."""
    if back_v > REVERSE_CREEP_MS:
        overshoot = back_v - REVERSE_CREEP_MS
        return min(REVERSE_BRAKE_MAX, REVERSE_BRAKE_MIN + overshoot / 2.0)
    return REVERSE_BRAKE_MIN * min(1.0, back_v / REVERSE_CREEP_MS)


@dataclass
class TeacherDecision:
    throttle: float
    brake: float
    steering: float
    reason: str
    target_speed_ms: float
    cte: float
    signed_cte: float
    heading_err: float
    curvature: float
    curvature_ahead: float
    safety_override: bool = False

    def as_tuple(self) -> Tuple[float, float, float]:
        return self.throttle, self.brake, self.steering


@dataclass
class TeacherConfig:
    speed_target_kmh: float = 20.0
    k_cte: float = 0.12
    k_heading: float = 0.55
    k_curvature: float = 2.5
    k_lookahead: float = 1.8
    steer_smooth: float = 0.35
    throttle_rate: float = 0.08
    brake_rate: float = 0.12
    speed_margin_ms: float = 1.5
    curve_speed_factor: float = 0.65
    # Modelo físico de la velocidad de curva (P16): v_lim = sqrt(a_lat / |κ|) con anticipación de frenada.
    # None = regla heurística de siempre (producción). a_lat en m/s²; a_brake es la deceleración que se supone
    # para empezar a bajar a tiempo (valores provisionales hasta medirlos en el plan A).
    lat_accel_limit: Optional[float] = None
    brake_decel: float = 4.0
    curve_lookahead_m: float = 150.0
    # Con el modo físico (`lat_accel_limit` fijado) el gas sigue la consigna con un PI en lugar del gas fijo de la
    # franja: gas = integral + kp·error; el freno solo entra pasado `speed_margin_ms`. Valores sin ajustar en el juego.
    pi_kp: float = 0.25  # gas por m/s de error
    pi_ki: float = 0.0004  # por tick y m/s de error (≈ 0,024 por segundo a 60 Hz)
    pi_ff: float = 0.3  # gas de partida de la integral (en C0 mantener 41 km/h pedía ≈ 0,31)
    pi_i_max: float = 0.6
    pi_i_window_ms: float = 3.0  # solo integra con |error| menor, para no acumular al arrancar
    # Anti-windup: si conduce otro (el BC) la integral no puede seguir subiendo sola, porque su etiqueta de gas se
    # corrompe (en el check del 29/10 pasó de 0,02 a 0,55 en una sesión). `track_applied_pedals` la acerca a lo aplicado:
    # por tick, `pi_kt` × (aplicado − pedido). Con el teacher al volante no hace nada.
    pi_kt: float = 0.05


class TeachingController:
    """Driver por reglas con prioridad: seguridad → línea → velocidad → pedales."""

    def __init__(self, ref: ReferenceLine, config: Optional[TeacherConfig] = None):
        self.ref = ref
        self.config = config or TeacherConfig()
        self._prev_steering = 0.0
        self._prev_throttle = 0.0
        self._prev_brake = 0.0
        self._gear_engagement_frames = 0
        self._vlim: Optional[List[float]] = None  # límite lateral por metro de vuelta, se calcula la primera vez
        self._speed_i = self.config.pi_ff  # integral del PI de velocidad (solo modo físico)
        self._pi_axis: Optional[float] = None  # eje de pedal pedido por el PI en este tick (None = no pasó por el PI)

    def _lateral_speed_limits(self) -> List[float]:
        """`v_lim(d) = sqrt(a_lat / |κ(d)|)` en m/s, un valor por metro, con la curvatura suavizada (±7 m)."""
        a_lat = self.config.lat_accel_limit
        assert a_lat is not None, "el modelo físico de curva necesita lat_accel_limit"
        n = max(1, int(self.ref.track_length))
        kappa = [abs(self.ref.curvature(float(d))) for d in range(n)]
        half = 7
        limits = []
        for d in range(n):
            window = [kappa[(d + i) % n] for i in range(-half, half + 1)]
            k = max(sum(window) / len(window), MIN_CURVATURE)
            limits.append(min(MAX_CURVE_SPEED_MS, math.sqrt(a_lat / k)))
        return limits

    def physical_curve_target(self, lap_distance: float) -> float:
        """Velocidad máxima ahora para poder bajar, con `brake_decel`, a la `v_lim` de cada punto que viene."""
        if self._vlim is None:
            self._vlim = self._lateral_speed_limits()
        n = len(self._vlim)
        best = MAX_CURVE_SPEED_MS
        s = 0.0
        while s <= self.config.curve_lookahead_m:
            v_lim = self._vlim[int(lap_distance + s) % n]
            best = min(best, math.sqrt(v_lim * v_lim + 2.0 * self.config.brake_decel * s))
            s += CURVE_SAMPLE_M
        return best

    def free_straight(self, lap_distance: float, curvature_tol: float = 0.02) -> bool:
        """True si el teacher no pide bajar de la consigna aquí ni en lo que viene (recta libre).

        Con modelo físico de curva: la velocidad máxima para poder frenar a tiempo (`physical_curve_target`) alcanza la consigna.
        Sin él: curvatura baja ahora y a `CURV_LOOKAHEAD_M`.
        """
        if self.config.lat_accel_limit is not None:
            return self.physical_curve_target(lap_distance) >= self.speed_target_ms
        return (
            abs(self.ref.curvature(lap_distance)) <= curvature_tol
            and abs(self.ref.curvature(lap_distance + CURV_LOOKAHEAD_M)) <= curvature_tol
        )

    @property
    def speed_target_ms(self) -> float:
        return self.config.speed_target_kmh / 3.6

    def reset(self) -> None:
        self._prev_steering = 0.0
        self._prev_throttle = 0.0
        self._prev_brake = 0.0
        self._gear_engagement_frames = 0
        self._speed_i = self.config.pi_ff
        self._pi_axis = None

    def signed_lateral_error(
        self,
        position: Tuple[float, float, float],
        lap_distance: float,
    ) -> float:
        """CTE con signo: positivo = a la derecha del trazado."""
        return signed_lateral_error(self.ref, position, lap_distance)

    def _smooth(self, prev: float, new: float, alpha: float) -> float:
        return prev + alpha * (new - prev)

    def _pedals_from_axis(self, target: float, gas_rate: Optional[float] = None) -> Tuple[float, float]:
        """Un solo eje de pedal (gas − freno, en [-1, 1]): la transición pasa por cero y nunca hay solape (P16).

        `target` > 0 es gas y < 0 es freno. El freno se suelta y se aplica a `brake_rate`; el gas, a `gas_rate`.
        """
        gas_rate = self.config.throttle_rate if gas_rate is None else gas_rate
        axis = self._prev_throttle - self._prev_brake
        braking_side = axis < 0 if target >= axis else target < 0
        axis = self._smooth(axis, target, self.config.brake_rate if braking_side else gas_rate)
        throttle, brake = max(0.0, axis), max(0.0, -axis)
        self._prev_throttle, self._prev_brake = throttle, brake
        return throttle, brake

    def _effective_k_cte(self, signed_cte: float, safety: bool, edge_surface: bool = False) -> float:
        """Ganancia lateral única: safety ×1.5, boost si |CTE|>2.5 m, extra si 1 rueda en hierba."""
        k = self.config.k_cte * (1.5 if safety else 1.0)
        if abs(signed_cte) > LATERAL_WARN_M:
            k *= LATERAL_K_CTE_BOOST
        if edge_surface and not safety:
            k *= EDGE_K_CTE_MULT
        return k

    def _resolve_need_first_gear(
        self,
        telem: TelemetryFrame,
        reversing: bool,
        safety: bool,
        safety_reason: str,
    ) -> bool:
        if reversing:
            self._gear_engagement_frames = 0
            return False
        if (
            safety
            and safety_reason in STALL_RECOVERY_REASONS
            and telem.speed < STALL_RECOVERY_SPEED_MS
        ):
            self._gear_engagement_frames = 0
            return False
        if not needs_gear_engagement(telem):
            self._gear_engagement_frames = 0
            return False
        self._gear_engagement_frames += 1
        if telem.gear > 1 and (
            self._gear_engagement_frames > ENGAGE_FIRST_STUCK_MAX_FRAMES
            and telem.speed > 0.5
        ):
            return False
        return True

    def compute_steering(
        self,
        telem: TelemetryFrame,
        lap_distance: float,
        signed_cte: float,
        heading_err: float,
        safety: bool = False,
        reversing: bool = False,
        edge_surface: bool = False,
    ) -> Tuple[float, float]:
        curv = self.ref.curvature(lap_distance)
        curv_ahead = self.ref.curvature(lap_distance + CURV_LOOKAHEAD_M)

        if reversing:
            raw = -REVERSE_K_CTE * signed_cte + REVERSE_K_HEADING * heading_err
            smooth = REVERSE_STEER_SMOOTH
        elif safety:
            k_cte = self._effective_k_cte(signed_cte, safety=True)
            raw = -k_cte * signed_cte + self.config.k_heading * heading_err
            smooth = self.config.steer_smooth
        else:
            k_cte = self._effective_k_cte(signed_cte, safety=False, edge_surface=edge_surface)
            raw = (
                -k_cte * signed_cte
                + self.config.k_heading * heading_err
                - self.config.k_curvature * curv
                - self.config.k_lookahead * curv_ahead
            )
            smooth = self.config.steer_smooth

        raw = max(-1.0, min(1.0, raw))
        steering = self._smooth(self._prev_steering, raw, smooth)
        steering = max(-1.0, min(1.0, steering))
        self._prev_steering = steering
        return steering, curv_ahead

    def track_applied_pedals(self, throttle: float, brake: float) -> None:
        """Anti-windup por retrocálculo: llamar cuando los pedales aplicados no son los del teacher (conduce el BC).

        Acerca la integral del PI a lo aplicado de verdad, de modo que la etiqueta de gas que graba el teacher sea la que
        corregiría el estado actual y no una integral saturada que nadie aplica.
        """
        if self._pi_axis is None:
            return
        cfg = self.config
        applied = throttle - brake
        self._speed_i = max(0.0, min(cfg.pi_i_max, self._speed_i + cfg.pi_kt * (applied - self._pi_axis)))

    def _pi_speed_pedals(self, speed: float, curve_target: float, curv_ahead: float) -> Tuple[float, float, str]:
        """Gas por PI sobre el error de velocidad; entre la consigna y el margen de exceso se suelta el gas sin frenar."""
        cfg = self.config
        err = curve_target - speed
        if abs(err) < cfg.pi_i_window_ms:
            self._speed_i = max(0.0, min(cfg.pi_i_max, self._speed_i + cfg.pi_ki * err))
        target = max(0.0, min(0.85, self._speed_i + cfg.pi_kp * err))
        self._pi_axis = target
        reason = "maintain_speed"
        if err > 0.5:
            if abs(curv_ahead) > 0.02:
                target = min(target, 0.45)
                reason = "accel_curve_limited"
            else:
                reason = "accel_straight"
        throttle, brake = self._pedals_from_axis(target)
        return throttle, brake, reason

    def compute_pedals(
        self,
        telem: TelemetryFrame,
        lap_distance: float,
        signed_cte: float,
        curv_ahead: float,
        safety: bool = False,
        safety_reason: str = "",
        reversing: bool = False,
        need_first_gear: bool = False,
    ) -> Tuple[float, float, str]:
        self._pi_axis = None
        if reversing:
            self._speed_i = self.config.pi_ff
            throttle = 0.0
            brake = self._smooth(
                self._prev_brake,
                reverse_brake_target(backward_speed_ms(telem)),
                self.config.brake_rate,
            )
            self._prev_throttle = self._smooth(self._prev_throttle, 0.0, self.config.throttle_rate)
            self._prev_brake = brake
            return throttle, brake, SAFETY_REVERSE_REASON

        if need_first_gear:
            self._speed_i = self.config.pi_ff
            throttle = self._smooth(
                self._prev_throttle,
                ENGAGE_FIRST_THROTTLE,
                self.config.throttle_rate * 1.5,
            )
            self._prev_brake = 0.0
            self._prev_throttle = throttle
            return throttle, 0.0, ENGAGE_FIRST_REASON

        speed = telem.speed
        target = self.speed_target_ms

        spd_ahead_50 = self.ref.speed_lookahead(lap_distance, 50.0)
        spd_ahead_100 = self.ref.speed_lookahead(lap_distance, 100.0)
        ref_brake = self.ref.reference_brake(lap_distance)

        if self.config.lat_accel_limit is not None:
            curve_target = min(target, max(MIN_CURVE_TARGET_MS, self.physical_curve_target(lap_distance)))
        else:
            curve_factor = 1.0 - min(abs(curv_ahead) * 12.0, 0.45)
            curve_target = target * max(0.4, curve_factor)

            if spd_ahead_100 < spd_ahead_50 * 0.92 or ref_brake > 0.2:
                curve_target = min(curve_target, spd_ahead_50 * self.config.curve_speed_factor)

        reason = "cruise"
        throttle = 0.0
        brake = 0.0

        if safety:
            self._speed_i = self.config.pi_ff
            reason = f"safety_{safety_reason}"
            if safety_reason in STALL_RECOVERY_REASONS and speed < STALL_RECOVERY_SPEED_MS:
                # Parado: gas para arrancar (auto_shift pone 1ª); freno empeora el atasco.
                throttle, brake = self._pedals_from_axis(
                    0.55 if is_forward_gear(telem) else 0.45, self.config.throttle_rate * 1.5,
                )
                return throttle, brake, reason
            throttle = 0.0
            brake = 0.6 if safety_reason in STALL_BRAKE_REASONS else 0.35
            brake = self._smooth(self._prev_brake, brake, self.config.brake_rate)
            self._prev_throttle = self._smooth(self._prev_throttle, 0.0, self.config.throttle_rate)
            self._prev_brake = brake
            return throttle, brake, reason

        if abs(signed_cte) > CTE_SAFE_M:
            throttle = 0.0
            brake = 0.25
            reason = "recover_line"
            self._speed_i = self.config.pi_ff
            brake = self._smooth(self._prev_brake, brake, self.config.brake_rate)
            self._prev_throttle = 0.0
            self._prev_brake = brake
            return throttle, brake, reason

        wheelspin = wheelspin_norm(telem)
        if wheelspin > WHEELSPIN_THRESHOLD:
            reason = "wheelspin_reduce"
            throttle, brake = self._pedals_from_axis(max(0.0, self._prev_throttle - 0.15))
            return throttle, brake, reason

        if speed > curve_target + self.config.speed_margin_ms:
            overspeed = speed - curve_target
            brake = min(1.0, overspeed / 8.0)
            if ref_brake > 0.1:
                brake = max(brake, ref_brake * 0.5)
            reason = "brake_overspeed"
            throttle, brake = self._pedals_from_axis(-brake)
            return throttle, brake, reason

        if self.config.lat_accel_limit is not None:
            return self._pi_speed_pedals(speed, curve_target, curv_ahead)

        if speed < curve_target - 0.5:
            gap = curve_target - speed
            throttle = min(0.85, 0.25 + gap / 6.0)
            if abs(curv_ahead) > 0.02:
                throttle = min(throttle, 0.45)
                reason = "accel_curve_limited"
            else:
                reason = "accel_straight"
            throttle, brake = self._pedals_from_axis(throttle)
            return throttle, brake, reason

        throttle, brake = self._pedals_from_axis(MAINTAIN_THROTTLE)
        return throttle, brake, "maintain_speed"

    def decide(
        self,
        telem: TelemetryFrame,
        timings: TimingsFrame,
        safety: bool = False,
        safety_reason: str = "",
        edge_surface: bool = False,
    ) -> TeacherDecision:
        lap_distance = timings.lap_distance
        signed_cte = self.signed_lateral_error(telem.position, lap_distance)
        cte = abs(signed_cte)
        reversing = is_driving_backward(telem)
        need_first_gear = self._resolve_need_first_gear(
            telem, reversing, safety, safety_reason,
        )
        if reversing:
            heading_err = self.ref.orientation_heading_error(telem.orientation, lap_distance)
        else:
            heading_err = self.ref.heading_error(telem.world_velocity, lap_distance)
        curv = self.ref.curvature(lap_distance)

        steering, curv_ahead = self.compute_steering(
            telem, lap_distance, signed_cte, heading_err,
            safety=safety, reversing=reversing, edge_surface=edge_surface,
        )
        throttle, brake, reason = self.compute_pedals(
            telem, lap_distance, signed_cte, curv_ahead,
            safety=safety,
            safety_reason=safety_reason,
            reversing=reversing,
            need_first_gear=need_first_gear,
        )
        if edge_surface and not safety and not reversing and reason not in (
            ENGAGE_FIRST_REASON, "recover_line",
        ):
            throttle = MAINTAIN_THROTTLE
            brake = 0.0
            reason = "edge_grass"
            self._prev_throttle = throttle
            self._prev_brake = 0.0

        return TeacherDecision(
            throttle=throttle,
            brake=brake,
            steering=steering,
            reason=reason,
            target_speed_ms=self.speed_target_ms,
            cte=cte,
            signed_cte=signed_cte,
            heading_err=heading_err,
            curvature=curv,
            curvature_ahead=curv_ahead,
            safety_override=safety or reversing,
        )

    def recovery_decision(
        self,
        telem: TelemetryFrame,
        timings: TimingsFrame,
        reason: str,
    ) -> TeacherDecision:
        return self.decide(telem, timings, safety=True, safety_reason=reason)


def resolve_teacher_decision(
    teacher: TeachingController,
    telem: TelemetryFrame,
    timings: TimingsFrame,
    safety: SafetyMonitor,
    status: SafetyStatus,
) -> TeacherDecision:
    """
    Decide acción del teacher.

    Orden: safety activa (≥8 m / stuck / wrong-way) → decide normal
    (incluye recover_line suave a 6 m y marcha atrás vía compute_pedals).
    """
    if status.active:
        return teacher.recovery_decision(
            telem, timings, status.reason or "off_track",
        )
    return teacher.decide(telem, timings, edge_surface=status.edge_surface)
