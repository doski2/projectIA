"""
reference_recorder.py
Graba una vuelta de referencia del piloto (humano o IA del juego) y la
almacena como línea de trazado para el agente de RL.

Modos de grabación (--source):
  human  → graba al participante observado solo si es humano.
  ai     → graba al participante observado solo si es la IA del juego.
           Flujo sin ayuda humana:
             1. Abre PCARS2 y crea una carrera con pilotos IA al máximo nivel.
             2. En la carrera, pulsa el botón de espectador para seguir al
                coche de la IA (ej. P1 del grid).
             3. Ejecuta este script → graba automáticamente sin conducir.
  auto   → acepta cualquier piloto (humano o IA) [por defecto].

Self-improvement automático (--improve):
  Si ya existe un archivo de referencia en --output, guarda la nueva vuelta
  solo si supera el mejor tiempo registrado. Así el agente puede mejorar su
  propia referencia de forma continua.

Uso desde línea de comandos:
    # Grabar IA del juego (sin conducir)
    python reference_recorder.py --source ai --laps 3 --output refs/spa_ai.json

    # Grabar mi mejor vuelta y actualizar solo si mejoro
    python reference_recorder.py --source human --improve --output refs/spa.json

Uso programático (para importar desde environment.py):
    from reference_recorder import ReferenceLine
    ref = ReferenceLine.load("refs/spa_ai.json")
    cte = ref.cross_track_error(agent_position, agent_lap_distance)
    spd = ref.speed_delta(agent_speed, agent_lap_distance)
"""

import argparse
import json
import math
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DISTANCE_RESOLUTION = 1.0   # metros por punto de referencia grabado

# Modos de fuente de datos
SOURCE_HUMAN = "human"
SOURCE_AI    = "ai"
SOURCE_AUTO  = "auto"


def slugify(text: str) -> str:
    """Convierte un texto libre en un slug seguro para nombres de archivo."""
    import re
    text = text.strip().lower()
    text = re.sub(r'[\s\-/]+', '_', text)
    text = re.sub(r'[^\w]', '', text)
    text = re.sub(r'_+', '_', text).strip('_')
    return text or "unknown"


# ---------------------------------------------------------------------------
# Estructuras de datos
# ---------------------------------------------------------------------------

class ReferencePoint:
    """
    Un punto de la línea de referencia en una distancia concreta de la vuelta.
    Usa __slots__ para minimizar memoria (miles de instancias).

    Campos guardados:
      Básicos  : lap_distance, position, speed, throttle, brake, steering, gear, orientation
      Telemetría adicional para pretrain realista:
        local_velocity   → slip angle, aceleración lateral
        angular_velocity → yaw rate
        local_accel      → aceleración longitudinal
        rpm, max_rpm     → ratio de RPM
        tyre_rps         → wheelspin / bloqueo
        sector           → sector de pista
    """
    __slots__ = (
        "lap_distance", "position", "speed",
        "throttle", "brake", "steering", "gear", "orientation",
        "local_velocity", "angular_velocity", "local_accel",
        "rpm", "max_rpm", "tyre_rps", "sector",
    )

    def __init__(
        self,
        lap_distance:    float,
        position:        Tuple[float, float, float],
        speed:           float,
        throttle:        int,
        brake:           int,
        steering:        int,
        gear:            int,
        orientation:     Tuple[float, float, float],
        local_velocity:  Tuple[float, float, float] = (0.0, 0.0, 0.0),
        angular_velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        local_accel:     Tuple[float, float, float] = (0.0, 0.0, 0.0),
        rpm:             int   = 0,
        max_rpm:         int   = 1,
        tyre_rps:        Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
        sector:          int   = 1,
    ):
        self.lap_distance    = lap_distance
        self.position        = position
        self.speed           = speed
        self.throttle        = throttle
        self.brake           = brake
        self.steering        = steering
        self.gear            = gear
        self.orientation     = orientation
        self.local_velocity  = local_velocity
        self.angular_velocity = angular_velocity
        self.local_accel     = local_accel
        self.rpm             = rpm
        self.max_rpm         = max_rpm if max_rpm > 0 else 1
        self.tyre_rps        = tyre_rps
        self.sector          = sector

    def to_dict(self) -> dict:
        return {
            "d":      round(self.lap_distance, 2),
            "pos":    [round(v, 3) for v in self.position],
            "spd":    round(self.speed, 3),
            "thr":    self.throttle,
            "brk":    self.brake,
            "steer":  self.steering,
            "gear":   self.gear,
            "ori":    [round(v, 5) for v in self.orientation],
            "lvel":   [round(v, 3) for v in self.local_velocity],
            "avel":   [round(v, 4) for v in self.angular_velocity],
            "lacc":   [round(v, 3) for v in self.local_accel],
            "rpm":    self.rpm,
            "maxrpm": self.max_rpm,
            "trps":   [round(v, 2) for v in self.tyre_rps],
            "sec":    self.sector,
        }

    @staticmethod
    def from_dict(d: dict) -> "ReferencePoint":
        return ReferencePoint(
            lap_distance    = d["d"],
            position        = tuple(d["pos"]),
            speed           = d["spd"],
            throttle        = d["thr"],
            brake           = d["brk"],
            steering        = d["steer"],
            gear            = d["gear"],
            orientation     = tuple(d["ori"]),
            local_velocity  = tuple(d.get("lvel", (0.0, 0.0, 0.0))),
            angular_velocity = tuple(d.get("avel", (0.0, 0.0, 0.0))),
            local_accel     = tuple(d.get("lacc", (0.0, 0.0, 0.0))),
            rpm             = d.get("rpm", 0),
            max_rpm         = d.get("maxrpm", 1),
            tyre_rps        = tuple(d.get("trps", (0.0, 0.0, 0.0, 0.0))),
            sector          = d.get("sec", 1),
        )


class LapBuffer:
    """
    Almacena los ReferencePoints de la vuelta en progreso.
    Solo guarda un punto por cada "bucket" de DISTANCE_RESOLUTION metros
    para evitar duplicados.
    """

    def __init__(self, resolution: float = DISTANCE_RESOLUTION):
        self._resolution = resolution
        self._points: Dict[int, ReferencePoint] = {}
        self._last_bucket = -1

    def add(self, t: TelemetryFrame, i: TimingsFrame):
        bucket = int(i.lap_distance / self._resolution)
        if bucket == self._last_bucket:
            return   # mismo bucket → ignorar, ya tenemos este tramo
        self._last_bucket = bucket
        self._points[bucket] = ReferencePoint(
            lap_distance    = i.lap_distance,
            position        = t.position,
            speed           = t.speed,
            throttle        = t.throttle,
            brake           = t.brake,
            steering        = t.steering,
            gear            = t.gear,
            orientation     = t.orientation,
            local_velocity  = t.local_velocity,
            angular_velocity = t.angular_velocity,
            local_accel     = t.local_acceleration,
            rpm             = t.rpm,
            max_rpm         = t.max_rpm,
            tyre_rps        = t.tyre_rps,
            sector          = i.sector,
        )

    def to_sorted_list(self) -> List[ReferencePoint]:
        return [self._points[k] for k in sorted(self._points)]

    def point_count(self) -> int:
        return len(self._points)

    def reset(self):
        self._points.clear()
        self._last_bucket = -1


# ---------------------------------------------------------------------------
# Línea de referencia (objeto central del módulo)
# ---------------------------------------------------------------------------

class ReferenceLine:
    """
    Línea de referencia completa de una vuelta.

    Proporciona:
      - cross_track_error(): distancia del agente respecto al trazado ideal.
      - speed_delta(): diferencia de velocidad vs el piloto de referencia.
      - is_braking_zone(): True si en ese punto el piloto de referencia frena.
      - save() / load(): persistencia en JSON.

    Ejemplo de uso en environment.py:
        ref = ReferenceLine.load("refs/spa_full.json")
        obs_cte    = ref.cross_track_error(agent.position, agent.lap_distance)
        obs_spddlt = ref.speed_delta(agent.speed, agent.lap_distance)
        reward += -1.5 * obs_cte - 0.5 * max(0, -obs_spddlt)
    """

    def __init__(
        self,
        points:       List[ReferencePoint],
        track_length: float,
        track_name:   str,
        lap_time:     float,
        all_laps:     Optional[List[dict]] = None,
    ):
        self.points       = points
        self.track_length = track_length
        self.track_name   = track_name
        self.lap_time     = lap_time
        # all_laps: lista de todas las vueltas grabadas [{lap_num, lap_time, points},...]
        # None = archivo de formato antiguo (solo la vuelta rápida)
        self.all_laps: List[dict] = all_laps if all_laps is not None else []

        # Índice rápido: bucket entero → ReferencePoint (lookup O(1))
        self._index: Dict[int, ReferencePoint] = {
            int(p.lap_distance): p for p in points
        }
        # Lista ordenada de claves para búsqueda por cercanía (fallback)
        self._sorted_keys = sorted(self._index.keys())

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def lookup(self, lap_distance: float) -> Optional[ReferencePoint]:
        """
        Devuelve el ReferencePoint más cercano a una distancia de vuelta dada.
        Maneja el wrap-around al final de la vuelta.
        """
        if not self._index:
            return None

        # Normalizar la distancia dentro del rango [0, track_length)
        if self.track_length > 0:
            lap_distance = lap_distance % self.track_length

        key = int(lap_distance)
        if key in self._index:
            return self._index[key]

        # Fallback: clave más cercana (bisect para O(log n))
        import bisect
        pos = bisect.bisect_left(self._sorted_keys, key)
        candidates = []
        if pos < len(self._sorted_keys):
            candidates.append(self._sorted_keys[pos])
        if pos > 0:
            candidates.append(self._sorted_keys[pos - 1])
        nearest = min(candidates, key=lambda k: abs(k - key))
        return self._index[nearest]

    def cross_track_error(
        self,
        position:     Tuple[float, float, float],
        lap_distance: float,
    ) -> float:
        """
        Distancia (metros) entre la posición del agente y el trazado ideal.
        Usa solo los ejes X y Z (horizontal), ignora la altitud Y.
        Retorna 0.0 si no hay punto de referencia disponible.
        """
        ref = self.lookup(lap_distance)
        if ref is None:
            return 0.0
        dx = position[0] - ref.position[0]
        dz = position[2] - ref.position[2]
        return math.sqrt(dx * dx + dz * dz)

    def speed_delta(self, speed: float, lap_distance: float) -> float:
        """
        Diferencia de velocidad (m/s) respecto a la referencia.
        Negativo  → el agente va más lento que la referencia (penalizar).
        Positivo  → el agente va más rápido (generalmente bueno).
        """
        ref = self.lookup(lap_distance)
        if ref is None:
            return 0.0
        return speed - ref.speed

    def is_braking_zone(self, lap_distance: float, threshold: int = 30) -> bool:
        """
        True si en ese punto el piloto de referencia frena significativamente.
        threshold: valor mínimo de brake (0-255) para considerar frenada.
        """
        ref = self.lookup(lap_distance)
        if ref is None:
            return False
        return ref.brake >= threshold

    def reference_throttle(self, lap_distance: float) -> float:
        """
        Valor de acelerador del piloto de referencia en ese punto (0.0–1.0).
        Útil para reward shaping: penalizar si el agente acelera en zona de frenada.
        """
        ref = self.lookup(lap_distance)
        if ref is None:
            return 0.0
        return ref.throttle / 255.0

    def heading_at(self, lap_distance: float) -> float:
        """
        Yaw (radianes) del trazado de referencia en esa distancia.
        Devuelve 0.0 si no hay punto de referencia disponible.
        """
        ref = self.lookup(lap_distance)
        if ref is None:
            return 0.0
        return ref.orientation[2]

    def reference_brake(self, lap_distance: float) -> float:
        """Valor de freno del piloto de referencia en ese punto (0.0–1.0)."""
        ref = self.lookup(lap_distance)
        if ref is None:
            return 0.0
        return ref.brake / 255.0

    def heading_vector(self, lap_distance: float) -> Optional[Tuple[float, float]]:
        """
        Vector de dirección (dx, dz normalizado) del trazado en ese punto.
        Útil para calcular el ángulo de desviación del agente respecto a la pista.
        """
        ref_a = self.lookup(lap_distance)
        ref_b = self.lookup(lap_distance + DISTANCE_RESOLUTION * 2)
        if ref_a is None or ref_b is None:
            return None
        dx = ref_b.position[0] - ref_a.position[0]
        dz = ref_b.position[2] - ref_a.position[2]
        length = math.sqrt(dx * dx + dz * dz)
        if length < 1e-6:
            return None
        return (dx / length, dz / length)

    def orientation_heading_error(
        self,
        orientation: Tuple[float, float, float],
        lap_distance: float,
    ) -> float:
        """Ángulo yaw del coche vs trazado (no usa velocidad; válido en marcha atrás)."""
        ref_yaw = self.heading_at(lap_distance)
        agent_yaw = orientation[2]
        diff = agent_yaw - ref_yaw
        return math.atan2(math.sin(diff), math.cos(diff))

    def heading_error(
        self,
        world_velocity: Tuple[float, float, float],
        lap_distance:   float,
    ) -> float:
        """
        Ángulo (radianes) entre la dirección real del coche y el trazado ideal.
        Se calcula desde la velocidad en el mundo (no desde el yaw) para que
        incluya el deslizamiento lateral.
        0 = el coche apunta exactamente al trazado.
        ±π = gira en dirección contraria.
        """
        hv = self.heading_vector(lap_distance)
        if hv is None:
            return 0.0
        vx = world_velocity[0]
        vz = world_velocity[2]
        speed_xz = math.sqrt(vx * vx + vz * vz)
        if speed_xz < 0.5:   # coche parado — ángulo no tiene sentido
            return 0.0
        # Cross product (sin) y dot product (cos) entre vel y heading
        sin_a = vz * hv[0] - vx * hv[1]
        cos_a = vx * hv[0] + vz * hv[1]
        return math.atan2(sin_a, cos_a)

    def speed_lookahead(self, lap_distance: float, lookahead_m: float = 50.0) -> float:
        """
        Velocidad de referencia a `lookahead_m` metros por delante del punto actual.
        Permite al agente anticipar frenadas antes de llegar a la curva.
        Devuelve la velocidad actual de referencia si no hay punto adelante.
        """
        ref = self.lookup(lap_distance + lookahead_m)
        if ref is None:
            ref = self.lookup(lap_distance)
        if ref is None:
            return 0.0
        return ref.speed

    def curvature(self, lap_distance: float, step: float = 3.0) -> float:
        """
        Curvatura aproximada del trazado en ese punto (1/radio).
        Positivo = giro a la izquierda, negativo = giro a la derecha.
        0 = recto.
        """
        h_a = self.heading_vector(lap_distance - step)
        h_b = self.heading_vector(lap_distance + step)
        if h_a is None or h_b is None:
            return 0.0
        # Cambio de ángulo por metro recorrido
        angle_a = math.atan2(h_a[1], h_a[0])
        angle_b = math.atan2(h_b[1], h_b[0])
        d_angle = angle_b - angle_a
        # Normalizar a [-π, π]
        while d_angle >  math.pi:
            d_angle -= 2 * math.pi
        while d_angle < -math.pi:
            d_angle += 2 * math.pi
        return d_angle / (2 * step)

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

    def save(self, path: str):
        """Guarda la línea de referencia en un archivo JSON."""
        # Limpiar bytes nulos / caracteres no imprimibles del nombre de pista
        clean_name = self.track_name.split('\x00')[0].strip()
        payload = {
            "track_name":   clean_name,
            "track_length": round(self.track_length, 2),
            "lap_time":     round(self.lap_time, 3),
            "resolution":   DISTANCE_RESOLUTION,
            "point_count":  len(self.points),
            "points":       [p.to_dict() for p in self.points],
        }
        if self.all_laps:
            payload["all_laps"] = self.all_laps
            payload["lap_count"] = len(self.all_laps)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))
        lap_info = f"{len(self.all_laps)} vueltas" if self.all_laps else "1 vuelta"
        print(
            f"[OK] Referencia guardada: {path}\n"
            f"     {len(self.points)} puntos  |  {self.lap_time:.3f} s  |  {lap_info}  |  {clean_name}"
        )

    @staticmethod
    def load(path: str) -> "ReferenceLine":
        """Carga una línea de referencia desde un archivo JSON."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        points = [ReferencePoint.from_dict(p) for p in data["points"]]
        all_laps = data.get("all_laps", None)
        return ReferenceLine(
            points       = points,
            track_length = data["track_length"],
            track_name   = data["track_name"],
            lap_time     = data["lap_time"],
            all_laps     = all_laps,
        )


# ---------------------------------------------------------------------------
# Grabador de vueltas
# ---------------------------------------------------------------------------

class ReferenceRecorder:
    """
    Orquesta la grabación de N vueltas y guarda la más rápida como referencia.

    Modos (source):
      SOURCE_HUMAN → solo graba cuando el participante observado es humano.
      SOURCE_AI    → solo graba cuando el participante observado es IA del juego.
                     Permite grabar sin conducir: deja que la IA corra y espéctala.
      SOURCE_AUTO  → graba independientemente del tipo de piloto.

    Self-improvement (improve=True):
      Si ya existe un archivo de referencia en output_path, compara el tiempo
      de la nueva vuelta con el guardado. Solo sobreescribe si es más rápida.
    """

    def __init__(
        self,
        output_path: Optional[str],
        num_laps:    int  = 3,
        source:      str  = SOURCE_AUTO,
        improve:     bool = False,
    ):
        self._output_path = output_path   # None = auto-detectar desde combo
        self._num_laps    = num_laps
        self._source      = source
        self._improve     = improve
        self._listener    = UDPListener()

        self._race_data:      Optional[RaceData]       = None
        self._vehicle_info:   Optional[VehicleInfo]     = None
        self._last_telemetry: Optional[TelemetryFrame] = None
        self._last_timings:   Optional[TimingsFrame]   = None

        self._buffer:    LapBuffer                          = LapBuffer()
        self._completed: List[Tuple[float, List[ReferencePoint]]] = []

        self._prev_lap   = -1
        self._max_lap_t  = 0.0
        self._recording  = False

        # Mejor tiempo existente (para self-improvement)
        self._existing_best: float = float("inf")
        if improve and output_path and os.path.exists(output_path):
            try:
                existing = ReferenceLine.load(output_path)
                self._existing_best = existing.lap_time
            except (OSError, ValueError, KeyError):
                pass

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def run(self):
        source_label = {
            SOURCE_HUMAN: "Solo piloto HUMANO",
            SOURCE_AI:    "Solo IA del juego (no necesitas conducir)",
            SOURCE_AUTO:  "Cualquier piloto",
        }.get(self._source, self._source)

        improve_label = ""
        if self._improve and self._existing_best < float("inf"):
            mins = int(self._existing_best // 60)
            secs = self._existing_best % 60
            improve_label = f"\n  Superar    : {mins}:{secs:06.3f} (mejor actual)"

        output_label = self._output_path if self._output_path else "auto ({coche}__{pista}.json)"

        print("=" * 55)
        print("  PCARS2-AI \u2014 Reference Recorder")
        print("=" * 55)
        print("  Puerto UDP : 5606")
        print(f"  Fuente     : {source_label}")
        print(f"  Vueltas    : {self._num_laps}")
        print(f"  Salida     : {output_label}{improve_label}")
        print("=" * 55)

        if self._source == SOURCE_AI:
            print(
                "\n  MODO IA: No necesitas conducir.\n"
                "  1. Crea una carrera en PCARS2 con pilotos IA.\n"
                "  2. En la carrera, cambia la cámara para ESPECTADOR\n"
                "     y sigue al coche más rápido de la IA.\n"
                "  3. Este script grabará automáticamente sus vueltas.\n"
            )
        elif self._source == SOURCE_HUMAN:
            print("\n  Sal a pista y comienza a conducir TÚ el coche.\n")
        else:
            print("\n  Sal a pista (humano o IA). Ctrl+C para parar.\n")

        try:
            self._loop()
        except KeyboardInterrupt:
            print("\n[!] Detenido por el usuario.")
        finally:
            self._save_best()
            self._listener.close()

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------

    def _loop(self):
        _waiting_pilot_msg = True
        while True:
            # Pasar el índice del participante observado al receptor UDP.
            # Esto hace que los TimingsFrame devueltos correspondan al coche
            # que tenemos en cámara (IA en práctica libre, IA en carrera como
            # espectador, o nuestro propio coche). Sin esto, los tiempos y la
            # distancia de vuelta siempre serían los del jugador local,
            # incluso si la cámara está en otro participante.
            viewed_idx = (
                self._last_telemetry.viewed_participant_index
                if self._last_telemetry is not None
                else None
            )
            ptype, packet = self._listener.recv(timeout=2.0, viewed_index=viewed_idx)

            if packet is None:
                continue

            if ptype == PACKET_RACE_DEF and isinstance(packet, RaceData):
                self._on_race_data(packet)

            elif ptype == PACKET_VEHICLE_NAMES and isinstance(packet, VehicleInfo):
                if self._vehicle_info is None:
                    self._vehicle_info = packet
                    car = slugify(packet.vehicle_name) if packet.vehicle_name else "?"
                    print(f"[i] Coche    : {packet.vehicle_name}  ({car})")
                    self._announce_output_path()

            elif ptype == PACKET_CAR_PHYSICS and isinstance(packet, TelemetryFrame):
                self._last_telemetry = packet

            elif ptype == PACKET_TIMINGS and isinstance(packet, TimingsFrame):
                # Propagar el flag de IA al último TelemetryFrame
                if self._last_telemetry is not None:
                    self._last_telemetry.viewed_is_ai = packet.viewed_is_ai

                # Filtrar según el modo de fuente elegido
                if self._source == SOURCE_AI and not packet.viewed_is_ai:
                    if _waiting_pilot_msg:
                        print(
                            "[~] Esperando a que cambies la cámara a un coche de IA..."
                            "\n    (En PCARS2: botón espectador → siguiente participante)"
                        )
                        _waiting_pilot_msg = False
                    continue
                elif self._source == SOURCE_HUMAN and packet.viewed_is_ai:
                    if _waiting_pilot_msg:
                        print("[~] Esperando al piloto humano (cámara en tu coche)...")
                        _waiting_pilot_msg = False
                    continue

                _waiting_pilot_msg = True
                self._on_timings(packet)

    def _on_race_data(self, rd: RaceData):
        if self._race_data is None:
            print(f"[i] Circuito : {rd.track_location} — {rd.track_variation}")
            print(f"[i] Longitud : {rd.track_length:.0f} m")
            self._recording = True
            self._announce_output_path()
        self._race_data = rd

    def _announce_output_path(self):
        """Muestra la ruta de salida cuando ya tenemos coche y/o pista."""
        if self._output_path:
            return   # ruta manual ya mostrada en el banner
        path = self._resolve_output_path()
        if path:
            print(f"[i] Salida   : {path}")

    def _resolve_output_path(self) -> Optional[str]:
        """
        Construye la ruta de salida a partir del combo coche+pista detectado.
        Devuelve None si aún no hay datos suficientes.
        """
        if self._race_data is None:
            return None
        track     = slugify(self._race_data.track_location)
        variation = slugify(self._race_data.track_variation)
        track_part = f"{track}__{variation}" if variation and variation != track else track
        if self._vehicle_info and self._vehicle_info.vehicle_name:
            car = slugify(self._vehicle_info.vehicle_name)
            combo = f"{car}__{track_part}"
        else:
            combo = track_part
        return os.path.join("refs", f"{combo}.json")

    def _on_timings(self, t: TimingsFrame):
        if not self._recording or self._last_telemetry is None:
            return

        pilot_tag = "IA" if t.viewed_is_ai else "HU"

        # ---- Primera vez: inicializar número de vuelta ----
        if self._prev_lap == -1:
            self._prev_lap = t.current_lap
            return

        # ---- Detectar vuelta completada ----
        if t.current_lap > self._prev_lap:
            self._close_lap(pilot_tag)
            self._prev_lap = t.current_lap
            # num_laps == 0 → ilimitado (el usuario para con Ctrl+C)
            if self._num_laps > 0 and len(self._completed) >= self._num_laps:
                raise KeyboardInterrupt

        # ---- Rastrear duración de la vuelta ----
        if t.current_time > self._max_lap_t:
            self._max_lap_t = t.current_time

        # ---- Grabar punto ----
        self._buffer.add(self._last_telemetry, t)

        # ---- Mostrar progreso cada 50 puntos ----
        n = self._buffer.point_count()
        if n > 0 and n % 50 == 0 and self._race_data:
            pct     = (t.lap_distance / self._race_data.track_length) * 100
            kmh     = self._last_telemetry.speed * 3.6
            brk_str = "FRENANDO" if self._last_telemetry.brake > 30 else "       "
            print(
                f"\r  [{pilot_tag}|LAP {t.current_lap}] "
                f"{t.lap_distance:5.0f}/{self._race_data.track_length:.0f}m "
                f"({pct:5.1f}%) | "
                f"{kmh:6.1f} km/h | "
                f"S{t.sector} | "
                f"{brk_str} | "
                f"{n} pts",
                end="",
            )

    def _close_lap(self, pilot_tag: str = ""):
        """Cierra la vuelta en curso."""
        points   = self._buffer.to_sorted_list()
        lap_time = self._max_lap_t

        if len(points) > 20 and lap_time > 0:
            self._completed.append((lap_time, points))
            mins = int(lap_time // 60)
            secs = lap_time % 60
            print(
                f"\n[OK] [{pilot_tag}] Vuelta {len(self._completed)} completada: "
                f"{mins}:{secs:06.3f}  ({len(points)} puntos)"
            )
        else:
            print(f"\n[!] Vuelta descartada (datos insuficientes: {len(points)} puntos)")

        self._buffer.reset()
        self._max_lap_t = 0.0

    def _save_best(self):
        """Guarda TODAS las vueltas en el JSON y usa la más rápida como referencia principal."""
        if not self._completed:
            print("[!] No hay vueltas grabadas.")
            if self._source == SOURCE_AI:
                print("    ¿Cambiaste la cámara a un coche de IA en PCARS2?")
            return

        best_time, best_points = min(self._completed, key=lambda x: x[0])

        # Self-improvement: solo guardar si mejora el tiempo existente
        if self._improve and best_time >= self._existing_best:
            mins_new = int(best_time // 60)
            secs_new = best_time % 60
            mins_old = int(self._existing_best // 60)
            secs_old = self._existing_best % 60
            print(
                f"\n[~] Sin mejora. Referencia actual ({mins_old}:{secs_old:06.3f}) "
                f"sigue siendo mejor que la nueva ({mins_new}:{secs_new:06.3f})."
            )
            return

        track_name   = "unknown"
        track_length = 0.0
        if self._race_data:
            loc          = self._race_data.track_location.replace(" ", "_")
            var          = self._race_data.track_variation.replace(" ", "_")
            track_name   = f"{loc}_{var}"
            track_length = self._race_data.track_length

        # Determinar ruta de salida final
        output_path = self._output_path or self._resolve_output_path()
        if not output_path:
            ts = int(time.time())
            output_path = os.path.join("refs", f"reference_{ts}.json")
            print(f"[!] No se pudo detectar el combo. Guardando como: {output_path}")

        # Construir array de todas las vueltas (para pretrain multi-vuelta)
        sorted_laps = sorted(self._completed, key=lambda x: x[0])
        all_laps = [
            {
                "lap_num":  i + 1,
                "lap_time": round(t, 3),
                "points":   [p.to_dict() for p in pts],
            }
            for i, (t, pts) in enumerate(sorted_laps)
        ]

        ref = ReferenceLine(
            points       = best_points,
            track_length = track_length,
            track_name   = track_name,
            lap_time     = best_time,
            all_laps     = all_laps,
        )
        ref.save(output_path)

        # Resumen de tiempos
        print(f"\n[i] Resumen de {len(self._completed)} vuelta(s) grabadas:")
        for i, (t, _) in enumerate(sorted_laps):
            mins = int(t // 60)
            secs = t % 60
            tag  = " ← MEJOR" if t == best_time else ""
            print(f"     Vuelta {i+1:>2}: {mins}:{secs:06.3f}{tag}")

        if self._improve and self._existing_best < float("inf"):
            delta = self._existing_best - best_time
            print(f"[+] Mejora respecto a la referencia anterior: -{delta:.3f} s")


# ---------------------------------------------------------------------------
# Punto de entrada CLI
# ---------------------------------------------------------------------------

def _build_output_path(args) -> Optional[str]:
    """Devuelve la ruta de salida manual, o None para auto-detección."""
    if args.output:
        return args.output
    return None   # se resolverá automáticamente desde coche+pista


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Graba una vuelta de referencia de Project CARS 2 "
            "y la guarda como línea de trazado para el agente de RL."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Archivo de salida JSON (por defecto: refs/reference_<timestamp>.json)",
    )
    parser.add_argument(
        "--laps", "-l",
        type=int,
        default=0,
        help=(
            "Número de vueltas a grabar (todas se guardan en el JSON para BC).\n"
            "0 = ilimitado — graba hasta que pulses Ctrl+C. (por defecto: 0)"
        ),
    )
    parser.add_argument(
        "--source", "-s",
        type=str,
        choices=[SOURCE_HUMAN, SOURCE_AI, SOURCE_AUTO],
        default=SOURCE_AUTO,
        help=(
            "Fuente del piloto a grabar:\n"
            "  human → solo graba al piloto humano\n"
            "  ai    → solo graba la IA del juego (no necesitas conducir)\n"
            "  auto  → cualquier piloto [por defecto]"
        ),
    )
    parser.add_argument(
        "--improve",
        action="store_true",
        default=False,
        help=(
            "Solo sobreescribe el archivo si la nueva vuelta es más rápida.\n"
            "Permite self-improvement: el agente actualiza su propia referencia."
        ),
    )
    args = parser.parse_args()
    output_path = _build_output_path(args)

    recorder = ReferenceRecorder(
        output_path = output_path,
        num_laps    = args.laps,
        source      = args.source,
        improve     = args.improve,
    )
    recorder.run()


if __name__ == "__main__":
    main()
