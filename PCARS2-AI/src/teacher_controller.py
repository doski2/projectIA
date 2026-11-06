"""
teacher_controller.py
Controlador por reglas que enseña conducción: steering, throttle y brake.

Patrón: ESTADO → REGLA/OBJETIVO → ACCIÓN
Cada decisión es explicable vía TeacherDecision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from obs_builder import wheelspin_norm
from pcars2_gear import (
    ENGAGE_FIRST_STUCK_MAX_FRAMES,
    ENGAGE_FIRST_THROTTLE,
    TEACHING_MAX_GEAR,
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
STEER_PREVIEW_MIN_M = 4.0  # anticipación mínima del volante con `steer_preview_s` (V22)
# «Recta» para frenar más fuerte (V31): curvatura y CTE por debajo de estos valores. Fuera de ella se frena como siempre.
STRAIGHT_BRAKE_KAPPA = 0.004
STRAIGHT_BRAKE_CTE_M = 1.0
LEGACY_BRAKE_OVERSPEED_MS = 8.0  # exceso de velocidad (m/s) con el que el pedal llega a 1,0 en la ley de siempre
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
# Deriva (V17): por debajo de esta velocidad el ángulo atan2(v lateral, v longitudinal) no significa nada.
SLIP_MIN_SPEED_MS = 5.0
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
# Técnica de pedales (V65): si el coche va tanto por debajo de la consigna que ya no hace falta frenar, se deja de esperar la curva y se vuelve a acelerar.
LIFT_RESUME_MS = 4.0
PEDAL_TICK_S = 1.0 / 60.0
# Pedal de freno que da cada deceleración en recta, sin bloqueo (m/s², pedal); medido en V55-V66 con `resumen_sesion.py` (0,40-0,55 → 8,3-8,9; 0,55-0,70 → 9,6-9,9; 0,70-1,00 → 11,6-11,7).
PEDAL_DECEL_TABLE = ((0.0, 0.0), (3.5, 0.11), (6.2, 0.30), (8.6, 0.475), (9.7, 0.625), (11.65, 0.85), (13.0, 1.0))


def exit_gas_cap(lat_accel: float, circle: float, throttle_max: float, floor: float) -> float:
    """Tope del gas en la salida de curva por el círculo de adherencia (V72, F3): `throttle_max · √(1 − (lateral / círculo)²)`, nunca por debajo de `floor` (el gas que mantiene la velocidad)."""
    if circle <= 0.0:
        return throttle_max
    frac = min(1.0, abs(lat_accel) / circle)
    return max(floor, throttle_max * math.sqrt(1.0 - frac * frac))


def pedal_for_decel(decel: float) -> float:
    """Pedal de freno (0-1) que da `decel` m/s² en recta según `PEDAL_DECEL_TABLE` (interpolación lineal)."""
    if decel <= PEDAL_DECEL_TABLE[0][0]:
        return PEDAL_DECEL_TABLE[0][1]
    for (d0, p0), (d1, p1) in zip(PEDAL_DECEL_TABLE, PEDAL_DECEL_TABLE[1:]):
        if decel <= d1:
            return p0 + (p1 - p0) * (decel - d0) / (d1 - d0)
    return PEDAL_DECEL_TABLE[-1][1]


def slip_angle(telem: TelemetryFrame) -> float:
    """Ángulo de deriva del coche en radianes: atan2(v lateral, v longitudinal) con los ejes del coche (`local_velocity`, H1).

    Con la convención del juego sale **negativo cuando el coche gira a la izquierda con la cola fuera** y positivo con la cola fuera girando a la derecha,
    es decir, de signo contrario a la guiñada del sobreviraje. 0 por debajo de `SLIP_MIN_SPEED_MS`."""
    v_long = -float(telem.local_velocity[2])
    if v_long < SLIP_MIN_SPEED_MS:
        return 0.0
    return math.atan2(float(telem.local_velocity[0]), v_long)


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
    # Anticipación de volante escalada con la velocidad (H58): la curva pide ≈ 2,77 + 0,0183 · v² unidades de volante por unidad de κ
    # y la anticipación fija da ≈ 4,3. Factor f(v) = 1 + ff_speed_gain · max(0, v² − v0²). 0 = como siempre (producción).
    ff_speed_gain: float = 0.0  # (m/s)⁻²
    max_gear: int = TEACHING_MAX_GEAR  # marcha más alta que se acepta sin pedir 1ª (A2.0-b, X24; 2 = producción)
    # Contravolante por deriva (V17): con |deriva| por encima de `slip_deadzone_deg` el volante recibe −slip_steer_gain · (deriva − zona muerta) y la ganancia
    # de CTE baja linealmente a 0 al llegar a `slip_cte_cut_deg`, porque en un derrape corregir la posición con más volante lo empeora. 0 = como siempre (producción).
    slip_steer_gain: float = 0.0  # unidades de volante por radián de deriva
    # Ganancia de CTE programada por velocidad (V18): por encima de `lat_gain_v0_kmh` el k_cte se multiplica por (v0 / v)². Con el retardo del coche (≈ 0,15 s) la frecuencia
    # natural del lazo crece con v y a 100 km/h el balanceo lateral crece (V18); con (v0/v)² la frecuencia queda como a v0. 0 = como siempre (producción).
    lat_gain_v0_kmh: float = 0.0
    # Anticipación del volante por tiempo (V22): con `steer_preview_s` > 0 la curvatura «por delante» del volante se lee a v · steer_preview_s metros (mínimo 4 m) y no a los 30 m fijos.
    # 30 m son 1,35 s a 80 km/h, mucho más que el retardo del coche (≈ 0,2 s): el volante entra en la curva antes de tiempo y el coche se desvía hacia el interior en la recta anterior. 0 = como siempre.
    steer_preview_s: float = 0.0
    # Tope del gas al acelerar (V24): 0,85 de siempre (producción). Con 0,85 el coche acelera un 15-20 % menos que a gas a fondo (A1) y el solver de A2, que usa las tablas de A1, queda optimista.
    throttle_max: float = 0.85
    # Frenada fuerte en recta (V31). Hoy el teacher supone 4 m/s² para anticipar la curva (`brake_decel`) y pisa el pedal a exceso / 8 m/s: en la práctica 0,25 de pedal y 4-5 m/s²,
    # un 40 % de lo que da el coche (11,5-11,8 m/s² a pedal 1,0 sin bloqueo en G3). Con estas dos opciones, **solo en recta** (|κ| < 0,004 y |CTE| < 1 m) la anticipación usa
    # `brake_decel_straight` y el pedal es exceso / `brake_overspeed_straight_ms`; en curva todo sigue igual. 0 / 8 = como siempre (producción).
    brake_decel_straight: float = 0.0
    brake_overspeed_straight_ms: float = LEGACY_BRAKE_OVERSPEED_MS
    slip_deadzone_deg: float = 3.0
    slip_cte_cut_deg: float = 8.0
    ff_speed_v0_kmh: float = 60.0
    # Tope de velocidad en el factor de la anticipación (V41, V57): por encima de `ff_speed_cap_kmh` el factor 1 + G · (v² − v0²) deja de crecer. Medido con el modelo del volante, a más de 100 km/h la
    # anticipación se pasa de lo que pide el coche (×1,10 a 90, ×1,35 a 108, ×1,51 a 119 km/h) y bajar la ganancia para todos estropea las curvas lentas. 0 = sin tope (producción).
    ff_speed_cap_kmh: float = 0.0
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
    # Técnica de pedales (V65), opt-in, solo con el modelo físico (`lat_accel_limit`). Fases: «drive» (el PI de siempre), «entry» (la consigna que viene obliga a bajar: el gas se corta del todo
    # y queda cortado, el freno entra al pasar el margen y se suelta en proporción al exceso hasta llegar a la consigna, es decir, hasta el vértice) y «exit» (desde el vértice el gas solo sube,
    # con pendiente limitada, mientras la velocidad esté por debajo de la consigna; la consigna no baja). False = como siempre (producción).
    pedal_technique: bool = False
    lift_band_ms: float = 0.5  # se corta el gas cuando la velocidad llega a (consigna − esto) con una curva por delante
    lift_drop_ms: float = 3.0  # «curva por delante» = su límite está al menos esto por debajo de la velocidad actual (los baches de curvatura no cuentan)
    lift_rate: float = 0.4  # suavizado del corte de gas (el de siempre, 0,08, tarda ≈ 0,45 s)
    # Frenada de entrada con perfil continuo (V68, F1), opt-in y solo con `pedal_technique`: la consigna es un perfil v*(s) por barrido hacia atrás desde los límites laterales, con la deceleración
    # disponible a_frenada = a_b · √(1 − (a_lat / brake_circle)²) (a_b = `brake_decel_straight`, 8 si es 0): sin el salto de 8 a 4 m/s² al entrar en la curva. El freno sigue el perfil por avance
    # (deceleración necesaria a `brake_ff_ahead_m` metros → pedal por la tabla medida) más `brake_profile_gain` de pedal por m/s de exceso, sin margen. False = como siempre.
    brake_profile: bool = False
    brake_circle: float = 14.6  # radio del círculo de adherencia (m/s², cota lateral de D21)
    brake_ff_ahead_m: float = 10.0
    brake_profile_gain: float = 0.12
    brake_profile_offset_ms: float = 1.0  # el perfil se eleva esta velocidad (m/s): la ley de siempre toma las curvas por encima del límite (frena al pasar un margen de 1,5 m/s); con 1,0 el coche de juguete entra a las curvas igual que ella y tarda 0,2 s más (con 1,5 entraba 1 m/s más rápido y tardaba 1,2 s menos)
    # Recorte de picos cortos de la consigna (V79, F13), opt-in y solo con `brake_profile`: quita del perfil los picos más estrechos que estos metros (se aplanan al valle más alto de alrededor), de modo que el
    # coche no acelera en un tramo corto entre dos curvas para frenar enseguida (gas, freno, gas de C5-C6, C9, C10 y C12-C14). Solo baja el perfil, nunca lo sube. 0 = sin recorte.
    profile_peak_min_m: float = 0.0
    # Umbral de prominencia del recorte (V81), solo con `profile_peak_min_m`: un pico solo se aplana si sobresale al menos estos km/h por encima del valle de alrededor (medido sobre el perfil
    # lateral, antes del barrido hacia atrás). Con 60 m sin umbral, el pico de 1,4 km/h que hay en 735-746 m, justo antes de C4, se igualaba al valle: el coche seguía con el gas unos 7 m más, entraba a C4
    # 1,3 km/h más rápido y la deriva subía (V80-V81). Los picos de C5-C6 sobresalen ≫ 100 km/h. 0 = sin umbral.
    profile_peak_min_kmh: float = 0.0
    brake_profile_lift_drop_ms: float = 1.5  # con perfil, una curva por delante cuenta si su límite está al menos esto por debajo de la velocidad (los baches de la curvatura de Sugo hacen mínimos de ≈ 3 m/s)
    # Tope del gas en la salida por el círculo de adherencia (V72, F3), opt-in y solo con `pedal_technique`: en «exit» el gas no pasa de `throttle_max · √(1 − (a_lat / exit_circle)²)` con la aceleración
    # lateral **medida** (suavizada), y nunca baja de `exit_circle_floor`. A 11,7 m/s² con círculo 14,6 el tope es 0,60 (la sesión 170252Z salía a 0,93-1,00 en C11). 0 = sin tope.
    exit_circle: float = 0.0
    exit_circle_floor: float = 0.3
    exit_lat_alpha: float = 0.3  # suavizado (EMA por tick) del lateral medido
    brake_on_ms2: float = 0.8  # deceleración necesaria a partir de la cual empieza a frenar (por debajo, gas cortado y sin freno)
    trail_offset_ms: float = 1.0  # la suelta del freno termina con este exceso sobre la consigna (0 = hasta llegar a la consigna; la ley de siempre soltaba a 1,5; con 1,0 el coche de juguete no pierde tiempo)
    exit_slew_per_s: float = 1.5  # subida máxima del gas por segundo desde el vértice (el gas llega a fondo en ≈ 0,7 s)


def open_profile_peaks(prof, width_m: float, min_drop_ms: float = 0.0):
    """Apertura morfológica circular de un perfil de velocidad por metro (V79): quita los picos más estrechos que `width_m` metros.

    Un pico entre dos mínimos cercanos (p. ej. el tramo de 35 m entre C5 y C6) se aplana al valle más alto de alrededor: el resultado nunca supera al perfil de entrada y los tramos
    anchos (rectas largas, curvas largas) no cambian. `width_m` <= 0 devuelve una copia sin tocar.

    `min_drop_ms` > 0 (V81): solo se aplanan los picos que el recorte baja al menos esos m/s en algún metro; los demás se dejan como estaban. Un pico es cada tramo seguido de metros
    que el recorte bajaría.
    """
    n = len(prof)
    half = int(width_m // 2)
    if half <= 0 or n == 0:
        return list(prof)
    half = min(half, n // 2)
    eroded = [min(prof[(i + k) % n] for k in range(-half, half + 1)) for i in range(n)]
    opened = [max(eroded[(i + k) % n] for k in range(-half, half + 1)) for i in range(n)]
    if min_drop_ms <= 0.0:
        return opened
    drop = [prof[i] - opened[i] for i in range(n)]
    start = min(range(n), key=lambda i: prof[i])  # el mínimo del perfil nunca se recorta: de ahí se recorre la vuelta sin partir ningún tramo
    out = list(prof)
    i = 0
    while i < n:
        a = (start + i) % n
        if drop[a] <= 1e-9:
            i += 1
            continue
        j = i
        while j < n and drop[(start + j) % n] > 1e-9:
            j += 1
        idx = [(start + k) % n for k in range(i, j)]
        if max(drop[x] for x in idx) >= min_drop_ms:
            for x in idx:
                out[x] = opened[x]
        i = j
    return out


class TeachingController:
    """Driver por reglas con prioridad: seguridad → línea → velocidad → pedales."""

    def __init__(self, ref: ReferenceLine, config: Optional[TeacherConfig] = None):
        self.ref = ref
        self.config = config or TeacherConfig()
        self._prev_steering = 0.0
        self._prev_throttle = 0.0
        self._prev_brake = 0.0
        self._gear_engagement_frames = 0
        self._vlim_cache: Dict[float, List[float]] = {}  # límite lateral por metro de vuelta, uno por cada `lat_accel_limit` usado
        self._profile_cache: Dict[Tuple[float, ...], List[float]] = {}  # perfil de frenada v*(s) por metro (V68)
        self._lat_scales: Optional[List[float]] = None  # multiplicador del límite lateral por metro de vuelta (--lat-adapt); None = el mismo límite en toda la vuelta
        self._speed_i = self.config.pi_ff  # integral del PI de velocidad (solo modo físico)
        self._pi_axis: Optional[float] = None  # eje de pedal pedido por el PI en este tick (None = no pasó por el PI)
        self._phase = "drive"  # técnica de pedales (V65): "drive", "entry" o "exit"
        self._exit_target = 0.0  # consigna que no baja durante «exit»
        self._lat_ema = 0.0  # |aceleración lateral| medida y suavizada (tope del gas por el círculo, V72)
        self._exit_scales: Optional[List[float]] = None  # multiplicador del radio del círculo de salida por metro de vuelta (--exit-adapt); None = el mismo radio en toda la vuelta
        self.exit_bound = False  # en este tick el tope del círculo de salida estaba recortando el gas (lo lee exit_adapt.py)
        self._brake_scales: Optional[List[float]] = None  # multiplicador de la deceleración de frenada (`a_b`) por metro de vuelta (--brake-adapt); None = la misma en toda la vuelta
        self._brake_scales_version = 0  # cambia con cada `set_brake_scales`: forma parte de la clave de la caché del perfil

    @property
    def entry_phase(self) -> bool:
        """True mientras la técnica de pedales está en la fase de entrada (frenada) de una curva."""
        return self._phase == "entry"

    def set_brake_scales(self, scales: Optional[Sequence[float]]) -> None:
        """Fija el multiplicador de la deceleración de frenada por metro de vuelta (`--brake-adapt`, ver `brake_adapt.py`) o lo quita con None. Obliga a recalcular el perfil de frenada."""
        self._brake_scales = None if scales is None else [float(x) for x in scales]
        self._brake_scales_version += 1
        self._profile_cache.clear()

    @property
    def exit_phase(self) -> bool:
        """True mientras la técnica de pedales está en la fase de salida de curva."""
        return self._phase == "exit"

    def set_exit_scales(self, scales: Optional[Sequence[float]]) -> None:
        """Fija el multiplicador del radio de `exit_circle` por metro de vuelta (`--exit-adapt`, ver `exit_adapt.py`) o lo quita con None. No hace falta recalcular nada: se lee en cada tick."""
        self._exit_scales = None if scales is None else [float(x) for x in scales]

    def _exit_circle_at(self, lap_distance: float) -> float:
        """Radio del círculo de salida en este punto de la vuelta (0 = sin tope)."""
        circle = self.config.exit_circle
        scales = self._exit_scales
        if circle <= 0.0 or not scales:
            return circle
        return circle * scales[int(lap_distance) % len(scales)]

    def _lateral_speed_limits(self) -> List[float]:
        """`v_lim(d) = sqrt(a_lat / |κ(d)|)` en m/s, un valor por metro, con la curvatura suavizada (±7 m)."""
        a_lat = self.config.lat_accel_limit
        assert a_lat is not None, "el modelo físico de curva necesita lat_accel_limit"
        scales = self._lat_scales
        if scales is None:
            return [min(MAX_CURVE_SPEED_MS, math.sqrt(a_lat / k)) for k in self._smoothed_kappa()]
        n = len(scales)
        return [min(MAX_CURVE_SPEED_MS, math.sqrt(a_lat * scales[d % n] / k)) for d, k in enumerate(self._smoothed_kappa())]

    def set_lat_scales(self, scales: Optional[Sequence[float]]) -> None:
        """Fija el multiplicador del límite lateral por metro de vuelta (`--lat-adapt`, ver `lat_adapt.py`) o lo quita con None. Obliga a recalcular el perfil."""
        self._lat_scales = None if scales is None else [float(s) for s in scales]
        self._vlim_cache.clear()
        self._profile_cache.clear()

    def _smoothed_kappa(self) -> List[float]:
        """|κ| por metro de vuelta, suavizada (±7 m) y con suelo `MIN_CURVATURE`."""
        n = max(1, int(self.ref.track_length))
        kappa = [abs(self.ref.curvature(float(d))) for d in range(n)]
        half = 7
        out = []
        for d in range(n):
            window = [kappa[(d + i) % n] for i in range(-half, half + 1)]
            out.append(max(sum(window) / len(window), MIN_CURVATURE))
        return out

    def braking_profile(self) -> List[float]:
        """Perfil de velocidad de frenada v*(s) en m/s, uno por metro (V68, F1): `v*(i) = min(v_lim(i), √(v*(i+1)² + 2 · a_frenada(i) · 1 m))` hacia atrás, dos vueltas al circuito.

        `a_frenada(i) = a_b · √(1 − (a_lat / brake_circle)²)` con `a_lat = v*(i+1)² · |κ(i)|`: cuanto más giro, menos freno disponible (círculo de adherencia)."""
        cfg = self.config
        a_lat = cfg.lat_accel_limit
        assert a_lat is not None, "el perfil de frenada necesita lat_accel_limit"
        a_b = cfg.brake_decel_straight if cfg.brake_decel_straight > 0.0 else 8.0
        off = cfg.brake_profile_offset_ms
        key = (a_lat, a_b, cfg.brake_circle, off, cfg.profile_peak_min_m, cfg.profile_peak_min_kmh, self._brake_scales_version)
        prof = self._profile_cache.get(key)
        if prof is None:
            vlim = self._vlim_cache.get(a_lat)
            if vlim is None:
                vlim = self._vlim_cache[a_lat] = self._lateral_speed_limits()
            kappa = self._smoothed_kappa()
            prof = [v if v >= MAX_CURVE_SPEED_MS else min(MAX_CURVE_SPEED_MS, v + off) for v in vlim]
            if cfg.profile_peak_min_m > 0.0:
                prof = open_profile_peaks(prof, cfg.profile_peak_min_m, cfg.profile_peak_min_kmh / 3.6)
            n = len(prof)
            bs = self._brake_scales
            for _ in range(2):
                for i in range(n - 1, -1, -1):
                    nxt = prof[(i + 1) % n]
                    lat = min(cfg.brake_circle, nxt * nxt * kappa[i])
                    a_long = a_b * (bs[i % len(bs)] if bs else 1.0) * math.sqrt(max(0.0, 1.0 - (lat / cfg.brake_circle) ** 2))
                    cand = math.sqrt(nxt * nxt + 2.0 * a_long)
                    if cand < prof[i]:
                        prof[i] = cand
            self._profile_cache[key] = prof
        return prof

    def profile_at(self, lap_distance: float, ahead_m: float = 0.0) -> float:
        """v*(s) en m/s a `ahead_m` metros por delante de `lap_distance` (interpolación lineal entre metros)."""
        prof = self.braking_profile()
        n = len(prof)
        x = lap_distance + ahead_m
        i = int(math.floor(x))
        f = x - i
        return prof[i % n] * (1.0 - f) + prof[(i + 1) % n] * f

    def profile_info(self, lap_distance: float) -> Tuple[float, float, float]:
        """(consigna, distancia, velocidad) del próximo mínimo del perfil por delante: distancia 0 = el perfil sube o está plano aquí; > 0 = una curva que viene."""
        prof = self.braking_profile()
        n = len(prof)
        i0 = int(lap_distance)
        best = self.profile_at(lap_distance)
        limit = int(self.config.curve_lookahead_m)
        for d in range(limit + 1):
            a, b = prof[(i0 + d) % n], prof[(i0 + d + 1) % n]
            if a <= b:
                return best, float(d), a
        return best, float(limit), prof[(i0 + limit) % n]

    def physical_curve_target(self, lap_distance: float, decel: Optional[float] = None) -> float:
        """Velocidad máxima ahora para poder bajar, con `brake_decel` (o `decel`), a la `v_lim` de cada punto que viene."""
        return self.physical_curve_info(lap_distance, decel)[0]

    def physical_curve_info(self, lap_distance: float, decel: Optional[float] = None) -> Tuple[float, float, float]:
        """(consigna, distancia, `v_lim`) del punto que fija la consigna: distancia 0 = el límite de aquí mismo; > 0 = una curva que viene."""
        decel = self.config.brake_decel if decel is None else decel
        a_lat = self.config.lat_accel_limit
        assert a_lat is not None, "el modelo físico de curva necesita lat_accel_limit"
        vlim = self._vlim_cache.get(a_lat)  # la rampa de A1.3 cambia el límite en marcha: no reutilizar el de otro valor
        if vlim is None:
            vlim = self._vlim_cache[a_lat] = self._lateral_speed_limits()
        n = len(vlim)
        best = MAX_CURVE_SPEED_MS
        s_bind, v_bind = 0.0, MAX_CURVE_SPEED_MS
        s = 0.0
        while s <= self.config.curve_lookahead_m:
            v_lim = vlim[int(lap_distance + s) % n]
            cand = math.sqrt(v_lim * v_lim + 2.0 * decel * s)
            if cand < best:
                best, s_bind, v_bind = cand, s, v_lim
            s += CURVE_SAMPLE_M
        return best, s_bind, v_bind

    def braking_on_straight(self, lap_distance: float, signed_cte: float) -> bool:
        """True si hay que usar la frenada fuerte de recta (V31): activada en la configuración y el coche va recto y sobre la línea."""
        cfg = self.config
        if cfg.brake_decel_straight <= 0.0 and cfg.brake_overspeed_straight_ms >= LEGACY_BRAKE_OVERSPEED_MS:
            return False
        return abs(self.ref.curvature(lap_distance)) < STRAIGHT_BRAKE_KAPPA and abs(signed_cte) < STRAIGHT_BRAKE_CTE_M

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
        self._phase = "drive"
        self._exit_target = 0.0
        self._lat_ema = 0.0
        self.exit_bound = False

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

    def _effective_k_cte(self, signed_cte: float, safety: bool, edge_surface: bool = False, cte_scale: float = 1.0, speed_ms: float = 0.0) -> float:
        """Ganancia lateral única: safety ×1.5, boost si |CTE|>2.5 m, extra si 1 rueda en hierba; `cte_scale` la baja en un derrape (V17) y la velocidad (V18)."""
        k = self.config.k_cte * (1.5 if safety else 1.0)
        v0 = self.config.lat_gain_v0_kmh / 3.6
        if v0 > 0.0 and speed_ms > v0:
            k *= (v0 / speed_ms) ** 2
        if abs(signed_cte) > LATERAL_WARN_M:
            k *= LATERAL_K_CTE_BOOST
        if edge_surface and not safety:
            k *= EDGE_K_CTE_MULT
        return k * cte_scale

    def slip_correction(self, telem: TelemetryFrame) -> Tuple[float, float]:
        """(volante añadido, factor de la ganancia de CTE) por la deriva; (0, 1) sin `slip_steer_gain` o dentro de la zona muerta."""
        cfg = self.config
        if cfg.slip_steer_gain <= 0.0:
            return 0.0, 1.0
        beta = slip_angle(telem)
        dead = math.radians(cfg.slip_deadzone_deg)
        excess = math.copysign(max(0.0, abs(beta) - dead), beta)
        if excess == 0.0:
            return 0.0, 1.0
        span = max(math.radians(cfg.slip_cte_cut_deg) - dead, 1e-6)
        return -cfg.slip_steer_gain * excess, max(0.0, 1.0 - abs(excess) / span)

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
        if not needs_gear_engagement(telem, self.config.max_gear):
            self._gear_engagement_frames = 0
            return False
        self._gear_engagement_frames += 1
        if telem.gear > 1 and (
            self._gear_engagement_frames > ENGAGE_FIRST_STUCK_MAX_FRAMES
            and telem.speed > 0.5
        ):
            return False
        return True

    def ff_speed_factor(self, speed_ms: float) -> float:
        """Factor de la anticipación de volante por la velocidad: 1 hasta `ff_speed_v0_kmh` y creciente con v² por encima."""
        v0 = self.config.ff_speed_v0_kmh / 3.6
        if self.config.ff_speed_cap_kmh > 0.0:
            speed_ms = min(speed_ms, self.config.ff_speed_cap_kmh / 3.6)
        return 1.0 + self.config.ff_speed_gain * max(0.0, speed_ms * speed_ms - v0 * v0)

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
        preview = curv_ahead
        if self.config.steer_preview_s > 0.0:
            preview = self.ref.curvature(lap_distance + max(STEER_PREVIEW_MIN_M, telem.speed * self.config.steer_preview_s))

        if reversing:
            raw = -REVERSE_K_CTE * signed_cte + REVERSE_K_HEADING * heading_err
            smooth = REVERSE_STEER_SMOOTH
        elif safety:
            counter, cte_scale = self.slip_correction(telem)
            k_cte = self._effective_k_cte(signed_cte, safety=True, cte_scale=cte_scale, speed_ms=telem.speed)
            raw = -k_cte * signed_cte + self.config.k_heading * heading_err + counter
            smooth = self.config.steer_smooth
        else:
            counter, cte_scale = self.slip_correction(telem)
            k_cte = self._effective_k_cte(signed_cte, safety=False, edge_surface=edge_surface, cte_scale=cte_scale, speed_ms=telem.speed)
            feed_forward = self.config.k_curvature * curv + self.config.k_lookahead * preview
            if self.config.ff_speed_gain:
                feed_forward *= self.ff_speed_factor(telem.speed)
            raw = -k_cte * signed_cte + self.config.k_heading * heading_err - feed_forward + counter
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

    def _pi_target(self, speed: float, curve_target: float) -> Tuple[float, float]:
        """(gas pedido por el PI, error de velocidad). Actualiza la integral."""
        cfg = self.config
        err = curve_target - speed
        if abs(err) < cfg.pi_i_window_ms:
            self._speed_i = max(0.0, min(cfg.pi_i_max, self._speed_i + cfg.pi_ki * err))
        target = max(0.0, min(cfg.throttle_max, self._speed_i + cfg.pi_kp * err))
        self._pi_axis = target
        return target, err

    def _pi_speed_pedals(self, speed: float, curve_target: float, curv_ahead: float) -> Tuple[float, float, str]:
        """Gas por PI sobre el error de velocidad; entre la consigna y el margen de exceso se suelta el gas sin frenar."""
        target, err = self._pi_target(speed, curve_target)
        reason = "maintain_speed"
        if err > 0.5:
            if abs(curv_ahead) > 0.02:
                target = min(target, 0.45)
                reason = "accel_curve_limited"
            else:
                reason = "accel_straight"
        throttle, brake = self._pedals_from_axis(target)
        return throttle, brake, reason

    def _technique_pedals(
        self, speed: float, curve_target: float, curv_ahead: float, s_bind: float, v_bind: float, on_straight: bool, ref_brake: float, v_ahead: Optional[float] = None,
        lat_accel: float = 0.0, lap_distance: float = 0.0,
    ) -> Tuple[float, float, str]:
        """Pedales con la técnica de curva (V65): gas cortado del todo antes de frenar, freno que se suelta hasta el vértice y gas que solo sube desde el vértice."""
        cfg = self.config
        self.exit_bound = False
        self._lat_ema += cfg.exit_lat_alpha * (abs(lat_accel) - self._lat_ema)
        # «Curva por delante»: la consigna la fija una curva que viene (no la banda de velocidad) y su límite está claramente por debajo de la velocidad actual.
        approaching = curve_target < self.speed_target_ms - 0.01 and s_bind >= CURVE_SAMPLE_M and speed - v_bind > (cfg.brake_profile_lift_drop_ms if v_ahead is not None else cfg.lift_drop_ms)
        over = speed - curve_target  # siempre con la consigna real: levantar y frenar no pueden depender de la consigna «congelada» de la salida (si no, la curva que viene llega sin aviso)
        pi_target = curve_target
        if self._phase == "exit" and s_bind < CURVE_SAMPLE_M:  # límite local (un bache de la curvatura): la consigna del PI no baja durante la salida
            pi_target = max(curve_target, self._exit_target)
            self._exit_target = pi_target
        free = curve_target >= self.speed_target_ms - 0.3
        if self._phase == "entry":
            leave = (not approaching or over < -LIFT_RESUME_MS) and self._prev_brake <= 0.02 and over <= max(0.3, cfg.trail_offset_ms)
            if leave:
                self._phase = "exit"
                self._exit_target = curve_target
                pi_target = curve_target
        elif (approaching and over >= -cfg.lift_band_ms) or over > (0.3 if v_ahead is not None else cfg.speed_margin_ms):  # con perfil el margen ya está en la consigna (`brake_profile_offset_ms`)
            self._phase = "entry"
        elif self._phase == "exit" and free:
            self._phase = "drive"

        if self._phase == "entry" and v_ahead is not None:  # frenada por perfil (V68): por avance más corrección, sin margen
            a_nec = max(0.0, (speed * speed - v_ahead * v_ahead) / (2.0 * cfg.brake_ff_ahead_m))
            if a_nec > cfg.brake_on_ms2 or over > 0.3:
                pedal = min(1.0, pedal_for_decel(a_nec) + cfg.brake_profile_gain * max(0.0, over))
                if pedal > 0.0:
                    throttle, brake = self._pedals_from_axis(-pedal)
                    return throttle, brake, "brake_overspeed"
            throttle, brake = self._pedals_from_axis(0.0, cfg.lift_rate)
            return throttle, brake, "lift_lock"

        if self._phase == "entry":
            if over > cfg.speed_margin_ms or self._prev_brake > 0.02:
                gain_ms = cfg.brake_overspeed_straight_ms if on_straight else LEGACY_BRAKE_OVERSPEED_MS
                trail = cfg.trail_offset_ms if self._prev_brake > 0.02 else 0.0  # el arranque es el de siempre; solo la suelta termina antes
                brake = min(1.0, max(0.0, over - trail) / gain_ms)
                if ref_brake > 0.1 and over > cfg.speed_margin_ms:
                    brake = max(brake, ref_brake * 0.5)
                if brake > 0.0:
                    throttle, brake = self._pedals_from_axis(-brake)
                    return throttle, brake, "brake_overspeed"
            throttle, brake = self._pedals_from_axis(0.0, cfg.lift_rate)
            return throttle, brake, "lift_lock"

        if self._phase == "exit":
            pi_gas, err = self._pi_target(speed, pi_target)
            cap = exit_gas_cap(self._lat_ema, self._exit_circle_at(lap_distance), cfg.throttle_max, cfg.exit_circle_floor)
            if err > 0.0:
                prev = self._prev_throttle
                axis = min(max(pi_gas, prev), prev + cfg.exit_slew_per_s * PEDAL_TICK_S)
                if err > 0.5 and abs(curv_ahead) > 0.02:
                    axis = min(axis, max(0.45, prev))  # el tope de curva cerrada no baja un gas que ya subía
                self.exit_bound = axis > cap + 1e-6
                axis = min(axis, cap)  # el círculo de adherencia: con el coche aún girando el gas no pasa de lo que deja el lateral (V72)
                throttle, brake = self._pedals_from_axis(axis, 1.0 if axis >= prev else 0.25)
            else:
                self.exit_bound = pi_gas > cap + 1e-6
                throttle, brake = self._pedals_from_axis(min(pi_gas, cap))
            return throttle, brake, "accel_exit"

        return self._pi_speed_pedals(speed, curve_target, curv_ahead)

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

        s_bind, v_bind = 0.0, MAX_CURVE_SPEED_MS
        if self.config.lat_accel_limit is not None:
            straight = self.braking_on_straight(lap_distance, signed_cte)
            decel = self.config.brake_decel_straight if straight and self.config.brake_decel_straight > 0.0 else None
            if self.config.pedal_technique and self.config.brake_profile:
                best, s_bind, v_bind = self.profile_info(lap_distance)
            else:
                best, s_bind, v_bind = self.physical_curve_info(lap_distance, decel)
            curve_target = min(target, max(MIN_CURVE_TARGET_MS, best))
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

        if self.config.pedal_technique and self.config.lat_accel_limit is not None:
            v_ahead = self.profile_at(lap_distance, self.config.brake_ff_ahead_m) if self.config.brake_profile else None
            return self._technique_pedals(
                speed, curve_target, curv_ahead, s_bind, v_bind, self.braking_on_straight(lap_distance, signed_cte), ref_brake, v_ahead,
                abs(telem.local_acceleration[0]), lap_distance,
            )

        if speed > curve_target + self.config.speed_margin_ms:
            overspeed = speed - curve_target
            gain_ms = self.config.brake_overspeed_straight_ms if self.braking_on_straight(lap_distance, signed_cte) else LEGACY_BRAKE_OVERSPEED_MS
            brake = min(1.0, overspeed / gain_ms)
            if ref_brake > 0.1:
                brake = max(brake, ref_brake * 0.5)
            reason = "brake_overspeed"
            throttle, brake = self._pedals_from_axis(-brake)
            return throttle, brake, reason

        if self.config.lat_accel_limit is not None:
            return self._pi_speed_pedals(speed, curve_target, curv_ahead)

        if speed < curve_target - 0.5:
            gap = curve_target - speed
            throttle = min(self.config.throttle_max, 0.25 + gap / 6.0)
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
