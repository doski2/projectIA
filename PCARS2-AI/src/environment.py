"""
environment.py
Entorno Gymnasium para el agente de RL de PCARS2-AI.

El entorno recibe telemetría en tiempo real del juego vía UDP,
calcula la observación y la recompensa comparando con la línea
de referencia grabada, y envía acciones al juego a través del
mando virtual DS4.

Flujo de un step():
  1. El agente elige una acción (throttle, brake, steering).
  2. El controlador envía esa acción al mando virtual.
  3. Se drena el backlog UDP y se espera un CAR_PHYSICS nuevo (no timeout falso).
  4. Se calcula la observación y la recompensa (solo tras frame de física).
  5. Se detecta si el episodio ha terminado.

Uso:
    from environment import PCARS2Env
    env = PCARS2Env(reference_path="refs/spa_practica.json")
    obs, info = env.reset()
    obs, reward, terminated, truncated, info = env.step(action)
"""

import math
import time
from typing import Optional, Tuple

from auto_shift import auto_shift

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from telemetry_udp import (
    UDPListener,
    TelemetryFrame,
    TimingsFrame,
    RaceData,
    VehicleInfo,
    PACKET_CAR_PHYSICS,
    PACKET_TIMINGS,
    PACKET_RACE_DEF,
    PACKET_VEHICLE_NAMES,
)
from reference_recorder import ReferenceLine
from controller import DS4Controller, decode_action
from obs_builder import (
    MAX_ANGULAR_VEL,
    MAX_CTE,
    MAX_CURVATURE,
    MAX_HEADING_ERR,
    MAX_LAT_ACCEL,
    MAX_LONG_ACCEL,
    MAX_SPEED_DELTA,
    MAX_SPEED_MS,
    MAX_TYRE_RPS,
    TYRE_RADIUS,
    build_obs,
)

# ---------------------------------------------------------------------------
# Límites del espacio de observación
# ---------------------------------------------------------------------------

# Temperatura máxima esperada de neumáticos (°C)
MAX_TYRE_TEMP      = 120.0

# Altura de suspensión máxima (m)
MAX_RIDE_HEIGHT    = 0.15

# Recorrido de suspensión máximo (m)
MAX_SUSP_TRAVEL    = 0.12

# ---------------------------------------------------------------------------
# Parámetros de la función de recompensa
# ---------------------------------------------------------------------------

W_SPEED      = 1.5    # peso: recompensa por velocidad proyectada sobre el trazado
W_CTE        = 1.0    # peso: penalización por cross-track error (clipeada a [-1,0])
W_STEER      = 0.05   # peso: penalización por volantazos bruscos
W_PROGRESS   = 0.02   # peso: recompensa por metros avanzados en la pista
W_SLOW       = 2.0    # peso: penalización por ir más lento que la referencia
W_BRAKE      = 0.8    # peso: incentivo por frenar donde frena la referencia
W_OVERSPEED  = 2.0    # peso: penalización por exceso de velocidad en zona de frenada
W_TARGET     = 1.5    # peso: penalización por desviarse del objetivo de velocidad

# Objetivo de velocidad adaptativo (speed-target curriculum)
# Rango de velocidad en el que r_target pasa de 0 a -W_TARGET (≈40 km/h = 11.1 m/s)
SPEED_TARGET_BAND_MS  = 40.0 / 3.6
# Ventana de pasos para evaluar si el agente cumple el objetivo actual
SPEED_TARGET_WINDOW   = 10_000
# El promedio de velocidad debe estar dentro de ±SPEED_TARGET_TOL_KMH del objetivo
SPEED_TARGET_TOL_KMH  = 10.0
# Incremento de velocidad por etapa superada (km/h)
SPEED_TARGET_STEP_KMH = 5.0

# Detección de coche sin progreso (cubre marcha atrás, box y atasco lento)
# Debe avanzar al menos NO_PROGRESS_DIST_M metros en NO_PROGRESS_TIME_S (vía GAME_FPS)
NO_PROGRESS_DIST_M  = 10.0
NO_PROGRESS_TIME_S  = 12.0
# Con curriculum el agente suele ir fuera de línea: dar más margen antes de cortar.
NO_PROGRESS_CURRICULUM_TIME_S = 30.0

# Detección de sentido contrario: error de heading >160° durante >N steps → terminar
# 160° equivale a "prácticamente al revés" (180° = exactamente invertido)
WRONGWAY_ANGLE_RAD       = math.radians(160)
WRONGWAY_TIME_S          = 2.0    # referencia temporal (se convierte a steps)
WRONGWAY_NEAR_FINISH_S   = 0.3    # referencia temporal cerca de meta
PIT_ZONE_MARGIN_M        = 300.0  # metros alrededor de la línea de meta que forman la zona restringida

# FPS del juego: los contadores de terminación avanzan una vez por frame de juego
# (cada iteración del bucle interno en step(), no por decisión del agente).
GAME_FPS = 25.0

# Detección de atascado: velocidad baja durante N frames de juego consecutivos
STUCK_SPEED_MS = 1.0
STUCK_TIME_S = 8.0
# Básicos: umbrales más permisivos para no cortar episodios mientras aprende a moverse
STUCK_SPEED_BASICS_MS = 0.4   # ~1.4 km/h — solo casi parado
STUCK_TIME_BASICS_S = 15.0    # ~15 s antes de cortar (vs 8 s)
# Penalización extra de volante a baja velocidad en básicos (evita girar a tope atascado)
BASICS_LOW_SPEED_MS = 5.0 / 3.6  # 5 km/h

# Pasos iniciales de gracia al inicio del episodio (no se penaliza off-track)
# Ampliado para dar tiempo al coche a volver al trazado tras reposicionamiento
GRACE_STEPS = 250

# Vuelta máxima por episodio (evitar episodios infinitos en entrenamiento)
MAX_LAPS_PER_EPISODE = 1


def termination_frame_count(time_s: float) -> int:
    """Frames de juego equivalentes a `time_s` segundos a GAME_FPS."""
    return int(time_s * GAME_FPS)


# ---------------------------------------------------------------------------
# Entorno principal
# ---------------------------------------------------------------------------

class PCARS2Env(gym.Env):
    """
    Entorno Gymnasium que conecta el agente PPO con Project CARS 2.

    Observation Space (19 valores normalizados):
      --- Dinámica del coche ---
       0  velocidad normalizada            [0, 1]
       1  cross-track error normalizado    [0, 1]
       2  delta velocidad vs referencia    [-1, 1]
       3  slip angle                       [-1, 1]
       4  yaw rate                         [-1, 1]
       5  aceleración lateral (G)          [-1, 1]
       6  aceleración longitudinal (G)     [-1, 1]  (+frena, -acelera)
       7  RPM normalizado (rpm/max_rpm)    [0, 1]
       8  marcha normalizada               [0, 1]
      --- Error vs trazado ideal ---
       9  heading error                    [-1, 1]
      10  curvatura en punto actual        [-1, 1]
      --- Anticipación (lookahead) ---
      11  velocidad referencia +50m        [0, 1]
      12  velocidad referencia +100m       [0, 1]
      13  throttle de referencia actual    [0, 1]
      14  brake de referencia actual       [0, 1]
      --- Ruedas ---
      15  wheelspin trasero                [-1, 1]  (+>0 = desliza)
      16  bloqueo delantero                [-1, 1]  (+>0 = bloquea)
      17  throttle filtrado actual         [0, 1]
      --- Estado general ---
      18  progreso en la vuelta            [0, 1]

    Action Space (3 valores continuos en [-1, 1]):
      0  acelerador  (mapeado a [0, 1] antes de enviar al mando)
      1  freno        (mapeado a [0, 1])
      2  volante      (directo: -1=izq, +1=der)

    Nota sobre frame_skip:
      Con frame_skip > 1 el agente repite la misma acción N frames seguidos.
      Esto mejora la señal de reward pero reduce la reactividad del steering
      en curvas rápidas. Valores recomendados: 2-4. Si se necesita mayor
      reactividad, considerar interpolar el steering linealmente entre frames
      (requiere refactor de step()).
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        reference_path: str,
        udp_timeout:    float = 0.1,
        gamepad_mode:   str   = 'xbox',
        frame_skip:     int   = 1,
        warmup_steps:   int   = 0,
        curriculum:        bool  = False,
        basics:            bool  = False,
        speed_target_kmh:  float = 0.0,
        render_mode:       Optional[str] = None,
    ):
        super().__init__()

        # --- Referencia de trazado ---
        self._ref = ReferenceLine.load(reference_path)
        self._warmup_steps    = max(0, warmup_steps)
        self._curriculum      = curriculum and not basics
        self._basics          = basics
        self._speed_target_ms = max(0.0, speed_target_kmh) / 3.6  # 0 = desactivado
        self._spd_win_steps   = 0
        self._spd_win_sum     = 0.0
        print(
            f"[Env] Referencia cargada: {self._ref.track_name}\n"
            f"      {len(self._ref.points)} puntos | "
            f"Mejor: {self._ref.lap_time:.3f}s | "
            f"Longitud: {self._ref.track_length:.0f}m"
        )
        if self._warmup_steps > 0:
            print(f"[Env] Warm-up activado: {self._warmup_steps} frames de gas antes de cada episodio.")
        if self._basics:
            print(
                "[Env] Modo BÁSICOS: línea + velocidad objetivo + girar + acciones suaves.\n"
                f"      no_progress relajado: {NO_PROGRESS_CURRICULUM_TIME_S:.0f}s.\n"
                f"      stuck relajado: <{STUCK_SPEED_BASICS_MS * 3.6:.1f} km/h "
                f"durante {STUCK_TIME_BASICS_S:.0f}s."
            )
        elif self._curriculum:
            print(
                "[Env] Curriculum activo: recompensa simplificada (solo gas + velocidad).\n"
                f"      no_progress relajado: {NO_PROGRESS_CURRICULUM_TIME_S:.0f}s "
                f"(vs {NO_PROGRESS_TIME_S:.0f}s en reward completa)."
            )
        if self._speed_target_ms > 0:
            print(f"[Env] Speed-target activo: objetivo inicial {self._speed_target_ms * 3.6:.1f} km/h, "
                  f"incremento +{SPEED_TARGET_STEP_KMH:.0f} km/h cada {SPEED_TARGET_WINDOW:,} pasos.")

        # --- Spaces ---
        # 19 observaciones — esenciales para conducción
        # 0:speed 1:cte 2:delta 3:slip 4:yaw 5:lat 6:long
        # 7:rpm 8:gear 9:heading_err 10:curv
        # 11:lk50 12:lk100 13:ref_thr 14:ref_brk
        # 15:wheelspin 16:lockup 17:throttle_cur 18:progress
        _low  = np.array([
            0, 0, -1, -1, -1, -1, -1,   # 0-6  speed/cte/delta/slip/yaw/lat/long
            0, 0,                        # 7-8  rpm/gear
            -1, -1,                      # 9-10 heading_err/curvatura
            0, 0,  0,  0,               # 11-14 lookahead×2 + ref_thr/brk
            -1, -1,  0,                 # 15-17 wheelspin/lockup/throttle_cur
            0,                           # 18  progress
        ], dtype=np.float32)
        _high = np.ones(19, dtype=np.float32)
        self.observation_space = spaces.Box(low=_low, high=_high, dtype=np.float32)
        self.action_space = spaces.Box(
            low   = np.full(3, -1.0, dtype=np.float32),
            high  = np.full(3,  1.0, dtype=np.float32),
            dtype = np.float32,
        )

        # --- Componentes de hardware ---
        self._listener   = UDPListener()
        self._controller = DS4Controller(mode=gamepad_mode)
        self._udp_timeout = udp_timeout
        self._frame_skip  = max(1, frame_skip)

        # --- Estado interno del episodio ---
        self._last_telem:    Optional[TelemetryFrame] = None
        self._last_timings:  Optional[TimingsFrame]   = None
        self._race_data:     Optional[RaceData]        = None
        self._vehicle_info:  Optional[VehicleInfo]     = None
        self._prev_steering: float = 0.0
        self._start_lap:     int   = -1
        self._prev_lap_dist: float = 0.0
        self._step_count:    int   = 0
        self._episode:       int   = 0
        self._ep_reward:     float = 0.0
        self._udp_ready:     bool  = False
        self._max_cte_seen:  float = 0.0   # diagnóstico
        self._term_reason:   str   = "?"   # razón de terminación del episodio
        self._stuck_steps:       int = 0       # contador de steps con speed < 1 m/s
        self._progress_dist:     float = -999.0  # mejor lap_distance reciente
        self._progress_step:     int   = 0       # step del último progreso
        self._prev_check_lap:    int   = -1      # vuelta en el último check de progreso
        self._wrongway_steps:    int   = 0       # contador de steps en sentido contrario
        self._physics_anchor:     Optional[tuple] = None  # clave del último frame aceptado
        self._udp_stats = self._fresh_udp_stats()

        # Umbrales en frames de juego (_step_count solo avanza con CAR_PHYSICS nuevo).
        _stuck_time = STUCK_TIME_BASICS_S if self._basics else STUCK_TIME_S
        self._stuck_speed_ms = STUCK_SPEED_BASICS_MS if self._basics else STUCK_SPEED_MS
        self._stuck_max_steps = termination_frame_count(_stuck_time)
        _no_progress_time = (
            NO_PROGRESS_CURRICULUM_TIME_S
            if (self._curriculum or self._basics)
            else NO_PROGRESS_TIME_S
        )
        self._no_progress_max_steps = termination_frame_count(_no_progress_time)
        self._wrongway_max_steps = termination_frame_count(WRONGWAY_TIME_S)
        self._wrongway_finish_steps = max(1, termination_frame_count(WRONGWAY_NEAR_FINISH_S))

    @staticmethod
    def _fresh_udp_stats() -> dict:
        return {
            "physics_frames":  0,
            "backlog_dropped": 0,
            "other_packets":   0,
            "timeouts":        0,
        }

    def udp_stats_snapshot(self) -> dict:
        """Contadores UDP del rollout actual (para metricas.csv)."""
        return dict(self._udp_stats)

    def udp_stats_reset(self) -> None:
        self._udp_stats = self._fresh_udp_stats()

    @staticmethod
    def _physics_key(frame: TelemetryFrame) -> tuple:
        """Identidad ligera de un frame de física (detecta duplicados en cola UDP)."""
        return (
            round(frame.speed, 2),
            round(frame.position[0], 1),
            round(frame.position[1], 1),
            round(frame.position[2], 1),
        )

    # ------------------------------------------------------------------
    # Gymnasium API
    # ------------------------------------------------------------------

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)

        # Log de fin de episodio anterior
        if self._episode > 0:
            # Si _term_reason sigue siendo "?" → el TimeLimit wrapper externo
            # truncó el episodio (modifica truncated DESPUÉS de que step() retorna)
            if self._term_reason == "?":
                self._term_reason = "timelimit"
            dist_str = f"{self._last_timings.lap_distance:.0f}m" if self._last_timings else "?"
            print(
                f"[Ep {self._episode:>4}] "
                f"pasos={self._step_count:>5} | "
                f"reward={self._ep_reward:>8.1f} | "
                f"dist={dist_str} | "
                f"CTE_max={self._max_cte_seen:.1f}m | "
                f"fin={self._term_reason}"
            )
        self._max_cte_seen  = 0.0
        self._term_reason   = "?"

        # Reposicionar el coche en pista (botón Back = reposición en PCARS2)
        self._controller.neutral()
        time.sleep(0.3)                      # espera a que el juego procese el neutral
        self._controller.press_button('back') # reposicionar en pista
        time.sleep(1.0)                      # espera a que el juego complete la reposición

        # Bajar a 1ª MIENTRAS el motor está girando (throttle activo).
        # PCARS2 bloquea el downshift con el coche parado y motor frío;
        # con gas aplicado el juego sí acepta los cambios secuenciales.
        # La telemetría aún es válida aquí (no se ha reseteado).
        self._controller.apply_action(0.5, 0.0, 0.0)   # gas suave para rascar el motor
        time.sleep(0.1)
        if self._last_telem is not None:
            needed = max(0, self._last_telem.gear - 1)   # cuántos LB hacen falta
            for _ in range(needed):
                self._controller.apply_action(0.3, 0.0, 0.0)
                self._controller.press_button('lb')       # 80 ms interno
                time.sleep(0.15)
        time.sleep(0.2)
        self._controller.neutral()
        time.sleep(0.2)

        self._prev_steering      = 0.0
        self._stuck_steps        = 0
        self._progress_dist      = -999.0
        self._progress_step      = 0
        self._prev_check_lap     = -1
        self._wrongway_steps     = 0
        self._prev_lap_dist      = 0.0
        self._step_count         = 0
        self._ep_reward          = 0.0
        self._episode           += 1
        self._physics_anchor     = None

        # Sincronizar hasta tener un frame de telemetría y timings válidos
        self._last_telem   = None
        self._last_timings = None

        if not self._udp_ready:
            print(
                "[Env] Esperando telemetría de PCARS2...\n"
                "      → Asegúrate de estar EN PISTA (no en menús ni en boxes)\n"
                "      → UDP activado en Opciones del juego, puerto 5606\n"
            )
        _warned = False
        _t0 = time.monotonic()
        while self._last_telem is None or self._last_timings is None:
            self._ingest_pending_packets()
            if self._last_telem is None or self._last_timings is None:
                self._recv_blocking_packet()
            if not _warned and time.monotonic() - _t0 > 10:
                print("[Env] Sin datos UDP tras 10s. Comprueba la config del juego.")
                _warned = True
        self._udp_ready = True

        # ---- Warm-up: gas a fondo N frames para que el coche arranque antes de
        #              entregar el control al agente (el coche llega ~30-50 km/h).
        if self._warmup_steps > 0:
            # Gas a fondo desde 1ª (el downshift ya se hizo antes del reset de telem)
            for _ in range(self._warmup_steps):
                self._controller.apply_action(1.0, 0.0, 0.0)
                if self._last_telem is not None:
                    auto_shift(self._controller, self._last_telem, 1.0, 0.0)
                self._sync_physics_frame()

        self._physics_anchor = (
            self._physics_key(self._last_telem)
            if self._last_telem is not None else None
        )
        self._start_lap = self._last_timings.current_lap
        obs = self._build_obs()
        return obs, {}

    def step(self, action):
        throttle, brake, steering = decode_action(action)

        total_reward = 0.0
        terminated   = False
        truncated    = False

        for _ in range(self._frame_skip):
            # 1. Enviar acción al mando
            self._controller.apply_action(throttle, brake, steering)
            if self._last_telem is not None:
                auto_shift(self._controller, self._last_telem, throttle, brake)

            # 2. Esperar un frame CAR_PHYSICS nuevo (no contar timeouts como frame)
            if not self._sync_physics_frame():
                break

            self._step_count += 1

            # 3. Calcular recompensa
            reward = self._compute_reward(throttle, brake, steering)
            total_reward      += reward
            self._ep_reward   += reward

            # 4. Detectar fin de episodio (salir antes si toca)
            terminated, truncated = self._check_done()
            if terminated or truncated:
                break

        # 5. Observación del último frame
        obs = self._build_obs()

        # 6. Info de diagnóstico (para TensorBoard/logging)
        info = self._build_info(throttle, brake, steering, total_reward)
        info['term_reason'] = self._term_reason

        self._prev_steering = steering
        return obs, total_reward, terminated, truncated, info

    def close(self):
        self._controller.release()
        self._listener.close()

    # ------------------------------------------------------------------
    # Construcción de la observación
    # ------------------------------------------------------------------

    def _build_obs(self) -> np.ndarray:
        if self._last_telem is None or self._last_timings is None:
            return np.zeros(19, dtype=np.float32)
        return build_obs(self._last_telem, self._last_timings, self._ref)

    # ------------------------------------------------------------------
    # Función de recompensa
    # ------------------------------------------------------------------

    def _speed_target_reward(self, speed_ms: float, positive: bool = False) -> float:
        """
        Componente de reward por cercanía al objetivo de velocidad.
        positive=True (básicos): recompensa hasta +W_TARGET al acercarse.
        positive=False (completo): penalización hasta -W_TARGET al alejarse.
        """
        if self._speed_target_ms <= 0:
            return 0.0

        speed_err_ms = abs(speed_ms - self._speed_target_ms)
        closeness = 1.0 - min(speed_err_ms / SPEED_TARGET_BAND_MS, 1.0)
        r_target = W_TARGET * closeness if positive else -W_TARGET * (1.0 - closeness)

        self._spd_win_sum += speed_ms
        self._spd_win_steps += 1
        if self._spd_win_steps >= SPEED_TARGET_WINDOW:
            avg_ms = self._spd_win_sum / self._spd_win_steps
            avg_kmh = avg_ms * 3.6
            tgt_kmh = self._speed_target_ms * 3.6
            if abs(avg_ms - self._speed_target_ms) <= SPEED_TARGET_TOL_KMH / 3.6:
                self._speed_target_ms += SPEED_TARGET_STEP_KMH / 3.6
                print(
                    f"[SpeedTarget] ✓ avg={avg_kmh:.1f} km/h ≈ objetivo {tgt_kmh:.1f} km/h "
                    f"→ nuevo objetivo: {self._speed_target_ms * 3.6:.1f} km/h"
                )
            else:
                print(
                    f"[SpeedTarget] avg={avg_kmh:.1f} km/h  objetivo {tgt_kmh:.1f} km/h "
                    f"(±{abs(avg_kmh - tgt_kmh):.1f} km/h) — manteniendo objetivo"
                )
            self._spd_win_steps = 0
            self._spd_win_sum = 0.0

        return float(r_target)

    def _compute_reward(
        self,
        throttle: float,
        brake:    float,
        steering: float,
    ) -> float:
        """
        R = v·cos(θ) - w_cte·CTE - w_steer·Δsteer - penalizaciones

        Componentes:
          + Recompensa por velocidad (proyectada en la dirección del trazado)
          - Penalización por cross-track error
          - Penalización por movimientos bruscos del volante
          - Penalización por frenar tarde (o no frenar en zona de frenada)
          - Penalización fija grave por salir de pista
        """
        if self._last_telem is None or self._last_timings is None:
            return 0.0

        t = self._last_telem
        i = self._last_timings

        # ---- Proyección de velocidad sobre el heading del trazado ----
        heading = self._ref.heading_vector(i.lap_distance)
        if heading is not None:
            # Velocidad del coche en el mundo (ejes X y Z)
            vx = t.world_velocity[0]
            vz = t.world_velocity[2]
            # Proyección: v·cos(θ) — positivo si vamos en la dirección correcta
            speed_proj = vx * heading[0] + vz * heading[1]
        else:
            speed_proj = t.speed

        r_speed = W_SPEED * np.clip(speed_proj / MAX_SPEED_MS, -1.0, 1.0)

        # ---- Básicos: línea + velocidad objetivo + heading + acciones suaves ----
        if self._basics:
            cte = self._ref.cross_track_error(t.position, i.lap_distance)
            r_cte = -W_CTE * min(cte / MAX_CTE, 2.0)

            h_err = self._ref.heading_error(t.world_velocity, i.lap_distance)
            r_heading = -0.8 * min(abs(h_err) / MAX_HEADING_ERR, 1.0)

            delta_steer = abs(steering - self._prev_steering)
            r_steer = -W_STEER * (delta_steer + 0.5 * abs(steering))
            if t.speed < BASICS_LOW_SPEED_MS:
                r_steer -= 0.5 * abs(steering)

            r_spd = self._speed_target_reward(t.speed, positive=True)
            if self._speed_target_ms <= 0:
                r_spd = 0.4 * max(0.0, r_speed)

            r_actions = 0.15 * throttle - 0.25 * brake
            return float(r_cte + r_heading + r_steer + r_spd + r_actions)

        # ---- Curriculum: recompensa simplificada solo por acelerar ----
        # Útil en las primeras iteraciones cuando el coche nunca ha llegado a moverse.
        # El agente aprende rápido que throttle=1 → recompensa positiva.
        # Desactivar con --no-curriculum cuando el coche ya se mueve con soltura.
        if self._curriculum:
            # +3 por gas, -3 por freno, +velocidad proyectada
            # Guard CTE suave: penaliza salirse de pista sin dominar la señal de velocidad.
            # Sin esto el agente optimiza "gas a fondo en cualquier lugar" → stuck 100%.
            cte_cur = self._ref.cross_track_error(t.position, i.lap_distance)
            r_cte_guard = -0.6 * W_CTE * min(cte_cur / MAX_CTE, 3.0)  # max -1.8
            return float(3.0 * throttle - 3.0 * brake + r_speed + r_cte_guard)

        # ---- Penalización por cross-track error ----
        # Clipeada a 3×MAX_CTE: permite distinguir CTE=2m vs CTE=10m (varianza real)
        # pero evita spikes de -10 cuando el juego reposiciona el coche lejos del trazado
        cte = self._ref.cross_track_error(t.position, i.lap_distance)
        r_cte = -W_CTE * min(cte / MAX_CTE, 3.0)

        # ---- Penalización por brusquedad del volante y por bloqueo a tope ----
        delta_steer = abs(steering - self._prev_steering)
        r_steer = -W_STEER * (delta_steer + abs(steering))

        # ---- Recompensa por progreso (metros avanzados en la pista) ----
        lap_dist = i.lap_distance
        progress_m = lap_dist - self._prev_lap_dist
        # Gestionar wrap-around al final de vuelta
        if progress_m < -self._ref.track_length * 0.5:
            progress_m += self._ref.track_length
        # Solo recompensar avance positivo (penalizar ir hacia atrás ya viene del r_speed)
        r_progress = W_PROGRESS * max(0.0, progress_m)
        self._prev_lap_dist = lap_dist

        # ---- Recompensa total ----
        # Penalización por ir más lento que la referencia (speed_delta < 0 → lento)
        speed_deficit = self._ref.speed_delta(t.speed, i.lap_distance)
        r_slow = W_SLOW * np.clip(speed_deficit / MAX_SPEED_DELTA, -1.0, 0.0)

        # ---- Incentivo por frenar donde frena la referencia ----
        # r_brake es proporcional a (brake_agente × brake_referencia):
        #   · Si la referencia frena fuerte y el agente también → +W_BRAKE máximo
        #   · Si la referencia no frena → r_brake ≈ 0 (no incentiva frenar en recta)
        ref_brk_norm = self._ref.reference_brake(i.lap_distance)
        r_brake = W_BRAKE * brake * ref_brk_norm

        # ---- Penalización por exceso de velocidad en zona de frenada ----
        # Si el agente va más rápido que la referencia en zona de frenada → penalty
        # (speed_deficit > 0 significa que el agente va más rápido que la referencia)
        r_overspeed = 0.0
        if speed_deficit > 0 and self._ref.is_braking_zone(i.lap_distance):
            r_overspeed = -W_OVERSPEED * np.clip(
                speed_deficit / MAX_SPEED_DELTA, 0.0, 1.0
            )

        # ---- Objetivo de velocidad adaptativo (speed-target curriculum) ----
        r_target = self._speed_target_reward(t.speed, positive=False)

        reward = r_speed + r_cte + r_steer + r_progress + r_slow + r_brake + r_overspeed + r_target
        return float(reward)

    # ------------------------------------------------------------------
    # Detección de fin de episodio
    # ------------------------------------------------------------------

    def _check_done(self) -> Tuple[bool, bool]:
        """
        Devuelve (terminated, truncated).

        terminated = True si:
          - stuck:       speed < umbral durante N frames de juego (8s / 15s en básicos)
          - no_progress: lap_distance no crece +10 m en 12s (30s en básicos/curriculum)
          - wrong_way:   heading >160° + speed >2 m/s durante ~2s (steps)

        truncated = True si:
          - lap_done: vuelta completada
        """
        if self._last_telem is None or self._last_timings is None:
            return False, False

        t = self._last_telem
        i = self._last_timings

        # ---- CTE (para logging y terminación) ----
        cte = self._ref.cross_track_error(t.position, i.lap_distance)
        if cte > self._max_cte_seen:
            self._max_cte_seen = cte

        # ---- Pit box / garaje: CTE absurda (>20 m) CERCA de la línea de meta ----
        if self._step_count > GRACE_STEPS and cte > 20.0:
            d    = i.lap_distance
            tlen = self._ref.track_length
            near_meta = d < 100.0 or d > tlen - 100.0
            if near_meta:
                self._term_reason = "pit_box"
                return True, False

        # ---- Atascado: velocidad ~0 durante N steps (determinista) ----
        # Usa contador de steps en vez de reloj real para ser inmune a lag del juego.
        if self._step_count > GRACE_STEPS:
            if t.speed < self._stuck_speed_ms:
                self._stuck_steps += 1
                if self._stuck_steps >= self._stuck_max_steps:
                    self._term_reason = "stuck"
                    return True, False
            else:
                self._stuck_steps = 0  # se mueve → reset counter

        # ---- Sin progreso: lap_distance no crece +10m en N steps ----
        # Determinista: usa step_count en vez de time.monotonic().
        if self._step_count > GRACE_STEPS:
            lap_dist = i.lap_distance
            cur_lap  = i.current_lap
            if cur_lap != self._prev_check_lap:
                # Nueva vuelta: reiniciar tracker sin disparar el timer
                self._progress_dist  = lap_dist
                self._progress_step  = self._step_count
                self._prev_check_lap = cur_lap
            elif lap_dist > self._progress_dist + NO_PROGRESS_DIST_M:
                self._progress_dist  = lap_dist
                self._progress_step  = self._step_count
            elif (self._step_count - self._progress_step) >= self._no_progress_max_steps:
                self._term_reason = "no_progress"
                return True, False

        # ---- Sentido contrario: heading >160° durante N steps ----
        # Determinista: cuenta steps consecutivos en sentido contrario.
        if self._step_count > GRACE_STEPS and t.speed > 2.0:
            ref_yaw   = self._ref.heading_at(i.lap_distance)
            agent_yaw = t.orientation[2]
            diff      = agent_yaw - ref_yaw
            heading_err = abs(math.atan2(math.sin(diff), math.cos(diff)))
            if heading_err > WRONGWAY_ANGLE_RAD:
                self._wrongway_steps += 1
                # Cerca de la línea de meta (zona del box) → tolerancia mínima
                d    = i.lap_distance
                tlen = self._ref.track_length
                near_finish = d < PIT_ZONE_MARGIN_M or d > tlen - PIT_ZONE_MARGIN_M
                max_steps = self._wrongway_finish_steps if near_finish else self._wrongway_max_steps
                if self._wrongway_steps >= max_steps:
                    self._term_reason = "wrong_way"
                    return True, False
            else:
                self._wrongway_steps = 0

        # ---- Vuelta completada ----
        laps_done = i.current_lap - self._start_lap
        if laps_done >= MAX_LAPS_PER_EPISODE:
            self._term_reason = "lap_done"
            return False, True

        return False, False

    # ------------------------------------------------------------------
    # Polling UDP
    # ------------------------------------------------------------------

    def _viewed_index(self) -> Optional[int]:
        if self._last_telem is not None:
            return self._last_telem.viewed_participant_index
        return None

    def _apply_packet(self, ptype: int, packet) -> str:
        """Actualiza estado interno. Devuelve 'physics', 'timings' u 'other'."""
        if ptype == PACKET_CAR_PHYSICS and packet is not None:
            self._last_telem = packet  # type: ignore[assignment]
            return "physics"
        if ptype == PACKET_TIMINGS and packet is not None:
            self._last_timings = packet  # type: ignore[assignment]
            return "timings"
        if ptype == PACKET_RACE_DEF and packet is not None:
            self._race_data = packet  # type: ignore[assignment]
        elif ptype == PACKET_VEHICLE_NAMES and packet is not None:
            self._vehicle_info = packet  # type: ignore[assignment]
        return "other"

    def _ingest_pending_packets(self) -> None:
        """Drena la cola UDP y deja telemetría/timings al día (sin avanzar step_count)."""
        viewed_idx = self._viewed_index()
        pending = self._listener.drain(viewed_index=viewed_idx)
        physics_seen = 0
        for ptype, packet in pending:
            kind = self._apply_packet(ptype, packet)
            if kind == "physics":
                physics_seen += 1
            elif kind == "other":
                self._udp_stats["other_packets"] += 1
        if physics_seen > 1:
            self._udp_stats["backlog_dropped"] += physics_seen - 1
        if self._last_telem is not None:
            self._physics_anchor = self._physics_key(self._last_telem)

    def _recv_blocking_packet(self) -> None:
        """Un recv con timeout (arranque / combo cuando el socket está vacío)."""
        ptype, packet = self._listener.recv(
            timeout=self._udp_timeout,
            viewed_index=self._viewed_index(),
        )
        if ptype is None:
            return
        kind = self._apply_packet(ptype, packet)
        if kind == "other":
            self._udp_stats["other_packets"] += 1

    def _sync_physics_frame(self) -> bool:
        """
        Espera un paquete CAR_PHYSICS nuevo respecto al último frame aceptado.

        1. Drena backlog (colapsa ráfagas de paquetes viejos en el socket).
        2. Bloquea hasta recibir física con posición/velocidad distinta (nuevo tick).
        3. Devuelve False si expira udp_timeout sin frame nuevo.
        """
        self._ingest_pending_packets()
        anchor = self._physics_anchor
        viewed_idx = self._viewed_index()
        deadline = time.monotonic() + self._udp_timeout

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            ptype, packet = self._listener.recv(
                timeout=max(remaining, 0.001),
                viewed_index=viewed_idx,
            )
            if ptype is None:
                break

            kind = self._apply_packet(ptype, packet)
            if kind == "timings":
                continue
            if kind == "other":
                self._udp_stats["other_packets"] += 1
                continue

            key = self._physics_key(packet)  # type: ignore[arg-type]
            if anchor is not None and key == anchor:
                self._udp_stats["backlog_dropped"] += 1
                continue

            self._physics_anchor = key
            self._udp_stats["physics_frames"] += 1
            return True

        self._udp_stats["timeouts"] += 1
        return False

    # ------------------------------------------------------------------
    # Detección automática de combo coche+pista
    # ------------------------------------------------------------------

    @staticmethod
    def _slugify(text: str) -> str:
        """Convierte un texto libre en un slug seguro para nombres de archivo."""
        import re
        text = text.strip().lower()
        text = re.sub(r'[\s\-/]+', '_', text)   # espacios, guiones, barras → _
        text = re.sub(r'[^\w]', '', text)        # eliminar caracteres no alfanuméricos
        text = re.sub(r'_+', '_', text).strip('_')
        return text or "unknown"

    @property
    def combo_id(self) -> Optional[str]:
        """
        Devuelve un identificador único 'vehiculo__pista_variante'.
        Necesita haber recibido los paquetes UDP de tipo 1 (pista) y 8 (coche).
        Devuelve None si aún no hay datos suficientes.
        """
        if self._race_data is None:
            return None
        track = self._slugify(self._race_data.track_location)
        track_part = track  # ignora variante meteorológica; mismo modelo para toda condición

        if self._vehicle_info is not None and self._vehicle_info.vehicle_name:
            car = self._slugify(self._vehicle_info.vehicle_name)
            return f"{car}__{track_part}"
        # Sin nombre de coche: solo pista
        return track_part

    def wait_for_combo(self, timeout: float = 30.0) -> Optional[str]:
        """
        Escucha UDP hasta detectar el combo coche+pista (máx. `timeout` segundos).
        Devuelve el combo_id detectado, o None si se agotó el tiempo.
        """
        print(
            "[Env] Detectando coche y pista desde telemetría UDP...\n"
            "      → Asegúrate de estar EN PISTA con el coche que quieres entrenar.\n"
        )
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            self._ingest_pending_packets()
            if self._race_data is None or self._vehicle_info is None:
                self._recv_blocking_packet()
            cid = self.combo_id
            if cid is not None and self._vehicle_info is not None:
                print(f"[Env] Combo detectado: {cid}")
                return cid
            # Mostrar progreso parcial cada 5 s
            elapsed = time.monotonic() - t0
            if int(elapsed) % 5 == 4 and not hasattr(self, '_combo_warned'):
                self._combo_warned = True
                car_ok   = self._vehicle_info is not None
                track_ok = self._race_data is not None
                print(
                    f"[Env] Esperando... coche={'OK' if car_ok else '?'}  "
                    f"pista={'OK' if track_ok else '?'}"
                )
            elif int(elapsed) % 5 != 4:
                if hasattr(self, '_combo_warned'):
                    del self._combo_warned

        # Timeout: usar solo lo que tenemos
        cid = self.combo_id
        if cid:
            print(f"[Env] Timeout — combo parcial detectado: {cid}")
        else:
            print("[Env] Timeout — no se pudo detectar coche/pista. Usando 'base'.")
        return cid

    # ------------------------------------------------------------------
    # Info de diagnóstico
    # ------------------------------------------------------------------

    def _build_info(
        self,
        throttle: float,
        brake:    float,
        steering: float,
        reward:   float,
    ) -> dict:
        if self._last_telem is None or self._last_timings is None:
            return {}
        t = self._last_telem
        i = self._last_timings
        cte = self._ref.cross_track_error(t.position, i.lap_distance)
        return {
            "speed_kmh":      round(t.speed * 3.6, 1),
            "lap_distance":   round(i.lap_distance, 1),
            "cte":            round(cte, 3),
            "speed_delta":    round(self._ref.speed_delta(t.speed, i.lap_distance), 2),
            "throttle":       round(throttle, 3),
            "brake":          round(brake, 3),
            "steering":       round(steering, 3),
            "reward":         round(reward, 4),
            "step":           self._step_count,
            "lap":            i.current_lap,
            "sector":         i.sector,
        }
