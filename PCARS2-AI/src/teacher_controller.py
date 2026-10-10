"""
teacher_controller.py
Controlador por reglas que enseña conducción: steering, throttle y brake.

Patrón: ESTADO → REGLA/OBJETIVO → ACCIÓN
Cada decisión es explicable vía TeacherDecision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from obs_builder import wheelspin_norm
from safety_monitor import SAFETY_OFF_TRACK_REASONS
from obs_universal import signed_lateral_error
from reference_recorder import ReferenceLine
from safety_monitor import CTE_SAFE_M, SafetyMonitor, SafetyStatus
from telemetry_udp import TelemetryFrame, TimingsFrame

CURV_LOOKAHEAD_M = 30.0
WHEELSPIN_THRESHOLD = 0.15
STALL_RECOVERY_SPEED_MS = 1.0
STALL_RECOVERY_REASONS = frozenset({"stuck", "no_progress"})
STALL_BRAKE_REASONS = frozenset({"stuck", "wrong_way"}) | (
    SAFETY_OFF_TRACK_REASONS - {"pit_box"}
)


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


class TeachingController:
    """Driver por reglas con prioridad: seguridad → línea → velocidad → pedales."""

    def __init__(self, ref: ReferenceLine, config: Optional[TeacherConfig] = None):
        self.ref = ref
        self.config = config or TeacherConfig()
        self._prev_steering = 0.0
        self._prev_throttle = 0.0
        self._prev_brake = 0.0

    @property
    def speed_target_ms(self) -> float:
        return self.config.speed_target_kmh / 3.6

    def reset(self) -> None:
        self._prev_steering = 0.0
        self._prev_throttle = 0.0
        self._prev_brake = 0.0

    def signed_lateral_error(
        self,
        position: Tuple[float, float, float],
        lap_distance: float,
    ) -> float:
        """CTE con signo: positivo = a la derecha del trazado."""
        return signed_lateral_error(self.ref, position, lap_distance)

    def _smooth(self, prev: float, new: float, alpha: float) -> float:
        return prev + alpha * (new - prev)

    def compute_steering(
        self,
        telem: TelemetryFrame,
        lap_distance: float,
        signed_cte: float,
        heading_err: float,
        safety: bool = False,
    ) -> Tuple[float, float]:
        curv = self.ref.curvature(lap_distance)
        curv_ahead = self.ref.curvature(lap_distance + CURV_LOOKAHEAD_M)

        raw = (
            -self.config.k_cte * signed_cte
            + self.config.k_heading * heading_err
            - self.config.k_curvature * curv
            - self.config.k_lookahead * curv_ahead
        )

        if safety:
            raw = -self.config.k_cte * 1.5 * signed_cte + self.config.k_heading * heading_err

        raw = max(-1.0, min(1.0, raw))
        steering = self._smooth(self._prev_steering, raw, self.config.steer_smooth)
        steering = max(-1.0, min(1.0, steering))
        self._prev_steering = steering
        return steering, curv_ahead

    def compute_pedals(
        self,
        telem: TelemetryFrame,
        lap_distance: float,
        signed_cte: float,
        curv_ahead: float,
        safety: bool = False,
        safety_reason: str = "",
    ) -> Tuple[float, float, str]:
        speed = telem.speed
        target = self.speed_target_ms

        spd_ahead_50 = self.ref.speed_lookahead(lap_distance, 50.0)
        spd_ahead_100 = self.ref.speed_lookahead(lap_distance, 100.0)
        ref_brake = self.ref.reference_brake(lap_distance)

        curve_factor = 1.0 - min(abs(curv_ahead) * 12.0, 0.45)
        curve_target = target * max(0.4, curve_factor)

        if spd_ahead_100 < spd_ahead_50 * 0.92 or ref_brake > 0.2:
            curve_target = min(curve_target, spd_ahead_50 * self.config.curve_speed_factor)

        reason = "cruise"
        throttle = 0.0
        brake = 0.0

        if safety:
            reason = f"safety_{safety_reason}"
            if safety_reason in STALL_RECOVERY_REASONS and speed < STALL_RECOVERY_SPEED_MS:
                # Parado: gas para arrancar (auto_shift pone 1ª); freno empeora el atasco.
                throttle = 0.55 if telem.gear >= 1 else 0.45
                brake = 0.0
                throttle = self._smooth(self._prev_throttle, throttle, self.config.throttle_rate * 1.5)
                self._prev_throttle = throttle
                self._prev_brake = self._smooth(self._prev_brake, 0.0, self.config.brake_rate)
                return throttle, self._prev_brake, reason
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
            brake = self._smooth(self._prev_brake, brake, self.config.brake_rate)
            self._prev_throttle = 0.0
            self._prev_brake = brake
            return throttle, brake, reason

        wheelspin = wheelspin_norm(telem)
        if wheelspin > WHEELSPIN_THRESHOLD:
            throttle = max(0.0, self._prev_throttle - 0.15)
            reason = "wheelspin_reduce"
            throttle = self._smooth(self._prev_throttle, throttle, self.config.throttle_rate)
            self._prev_throttle = throttle
            self._prev_brake = self._smooth(self._prev_brake, 0.0, self.config.brake_rate)
            return throttle, self._prev_brake, reason

        if speed > curve_target + self.config.speed_margin_ms:
            overspeed = speed - curve_target
            brake = min(1.0, overspeed / 8.0)
            if ref_brake > 0.1:
                brake = max(brake, ref_brake * 0.5)
            reason = "brake_overspeed"
            brake = self._smooth(self._prev_brake, brake, self.config.brake_rate)
            throttle = self._smooth(self._prev_throttle, 0.0, self.config.throttle_rate)
            self._prev_throttle = throttle
            self._prev_brake = brake
            return throttle, brake, reason

        if speed < curve_target - 0.5:
            gap = curve_target - speed
            throttle = min(0.85, 0.25 + gap / 6.0)
            if abs(curv_ahead) > 0.02:
                throttle = min(throttle, 0.45)
                reason = "accel_curve_limited"
            else:
                reason = "accel_straight"
            throttle = self._smooth(self._prev_throttle, throttle, self.config.throttle_rate)
            brake = self._smooth(self._prev_brake, 0.0, self.config.brake_rate)
            self._prev_throttle = throttle
            self._prev_brake = brake
            return throttle, brake, reason

        throttle = self._smooth(self._prev_throttle, 0.2, self.config.throttle_rate)
        brake = self._smooth(self._prev_brake, 0.0, self.config.brake_rate)
        reason = "maintain_speed"
        self._prev_throttle = throttle
        self._prev_brake = brake
        return throttle, brake, reason

    def decide(
        self,
        telem: TelemetryFrame,
        timings: TimingsFrame,
        safety: bool = False,
        safety_reason: str = "",
    ) -> TeacherDecision:
        lap_distance = timings.lap_distance
        signed_cte = self.signed_lateral_error(telem.position, lap_distance)
        cte = abs(signed_cte)
        heading_err = self.ref.heading_error(telem.world_velocity, lap_distance)
        curv = self.ref.curvature(lap_distance)

        steering, curv_ahead = self.compute_steering(
            telem, lap_distance, signed_cte, heading_err, safety=safety,
        )
        throttle, brake, reason = self.compute_pedals(
            telem, lap_distance, signed_cte, curv_ahead,
            safety=safety, safety_reason=safety_reason,
        )

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
            safety_override=safety,
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
    (incluye recover_line suave a 6 m vía compute_pedals).
    """
    if status.active:
        return teacher.recovery_decision(
            telem, timings, status.reason or "off_track",
        )
    return teacher.decide(telem, timings)
