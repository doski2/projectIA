"""
telemetry_udp.py
Parser de paquetes UDP para Project CARS 2.

Protocolo: SMS_UDP_Definitions.hpp  |  Puerto: 5606
Referencia completa: pcars2_udp_data_reference.md
"""

import errno
import socket
import struct
from dataclasses import dataclass
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Constantes del protocolo
# ---------------------------------------------------------------------------
SMS_UDP_PORT        = 5606
SMS_UDP_BUFFER_SIZE = 1500

# Tipos de paquetes (EUDPStreamerPacketHandlerType)
PACKET_CAR_PHYSICS   = 0   # sTelemetryData           — 556 bytes
PACKET_RACE_DEF      = 1   # sRaceData                — 308 bytes
PACKET_PARTICIPANTS  = 2   # sParticipantsData        — 1136 bytes
PACKET_TIMINGS       = 3   # sTimingsData             — 1059 bytes
PACKET_GAME_STATE    = 4   # sGameStateData           — 24 bytes
PACKET_TIME_STATS    = 7   # sTimeStatsData           — 1040 bytes
PACKET_VEHICLE_NAMES = 8   # sParticipantVehicleNames


# ---------------------------------------------------------------------------
# Dataclasses de datos parseados
# ---------------------------------------------------------------------------

@dataclass
class TelemetryFrame:
    """
    Datos del paquete eCarPhysics (tipo 0). 556 bytes.
    Contiene toda la física del coche del participante observado.
    """
    # --- Posición y movimiento ---
    position:            Tuple[float, float, float]   # XYZ alta precisión (sFullPosition)
    orientation:         Tuple[float, float, float]   # roll, pitch, yaw (radianes)
    local_velocity:      Tuple[float, float, float]   # velocidad en ejes del coche
    world_velocity:      Tuple[float, float, float]   # velocidad en ejes del mundo
    angular_velocity:    Tuple[float, float, float]   # velocidad angular
    local_acceleration:  Tuple[float, float, float]   # aceleración local (long, vert, lat) m/s²
    speed:               float                        # m/s (escalar)

    # --- Inputs filtrados (señal real que recibe el coche) ---
    throttle:  int    # 0–255
    brake:     int    # 0–255
    steering:  int    # -128..127
    clutch:    int    # 0–255
    gear:      int    # marcha actual (bits 0-3 de sGearNumGears)
    num_gears: int    # total de marchas (bits 4-7)

    # --- Inputs sin filtrar (entrada directa del mando) ---
    raw_throttle: int
    raw_brake:    int
    raw_steering: int

    # --- Neumáticos [FL, FR, RL, RR] ---
    tyre_temp:       Tuple[int, int, int, int]
    tyre_tread_temp: Tuple[int, int, int, int]   # temperatura banda de rodadura
    tyre_wear:       Tuple[int, int, int, int]   # desgaste 0-255
    tyre_rps:        Tuple[float, float, float, float]
    terrain:         Tuple[int, int, int, int]   # eTerrain por rueda [FL,FR,RL,RR]

    # --- Suspensión [FL, FR, RL, RR] ---
    ride_height:       Tuple[float, float, float, float]
    suspension_travel: Tuple[float, float, float, float]

    # --- Motor ---
    rpm:        int
    max_rpm:    int
    fuel_level: float   # 0.0-1.0

    # --- Daños ---
    aero_damage:   int
    engine_damage: int

    # --- Estado (paquete 0) ---
    car_flags: int    # sCarFlags @ offset 17 (bitmask, ver pcars2_surface.py)

    # --- Misc ---
    brake_bias: int   # cuantizado (0-100%)

    # --- Metadatos del participante observado ---
    viewed_participant_index: int   # sViewedParticipantIndex (offset 12)
    viewed_is_ai: bool              # True si el participante visto es IA del juego

    # --- Tanda 2 (X4b), con valor por defecto para no romper quien construya el frame a mano ---
    tyre_flags:               Tuple[int, int, int, int] = (0, 0, 0, 0)          # bit0 attached, bit1 inflated, bit2 on ground
    tyre_height_above_ground: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    brake_damage:             Tuple[int, int, int, int] = (0, 0, 0, 0)
    suspension_damage:        Tuple[int, int, int, int] = (0, 0, 0, 0)
    brake_temp:               Tuple[int, int, int, int] = (0, 0, 0, 0)          # °C
    suspension_velocity:      Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    air_pressure:             Tuple[int, int, int, int] = (0, 0, 0, 0)
    engine_torque:            float = 0.0
    crash_state:              int = 0
    tick_count:               int = 0                                            # sTickCount (offset 555), uchar cíclico


@dataclass
class TimingsFrame:
    """
    Datos del participante local extraídos del paquete eTimings (tipo 3).
    Clave para la referencia: lap_distance y current_lap.
    """
    lap_distance:        float   # metros recorridos en la vuelta actual
    current_lap:         int
    current_time:        float   # tiempo de vuelta actual (s)
    current_sector_time: float
    sector:              int     # sector actual (1/2/3)
    race_position:       int
    event_time_remaining: float  # -1 en carreras por vueltas
    # Flag de tipo de piloto para el participante observado:
    # bit 15 de sCarIndex = 1 → humano, 0 → IA del juego
    viewed_is_ai: bool = False


@dataclass
class GameStateFrame:
    """
    Paquete eGameState (tipo 4): tiempo atmosférico. Se envía cada ~10 s en carrera.
    Offsets 15-21 iguales con las dos ordenaciones documentadas de la cabecera (el estado del juego y el número de
    versión van antes y no se interpretan); `raw` guarda los bytes 12-23 para poder revisarlos.
    """
    ambient_temp: int    # °C
    track_temp:   int    # °C
    rain_density: int    # 0-255
    snow_density: int    # 0-255
    wind_speed:   int
    wind_dir_x:   int
    wind_dir_y:   int
    raw:          bytes = b""


@dataclass
class RaceData:
    """Datos del paquete eRaceDefinition (tipo 1)."""
    track_length:    float    # metros
    track_location:  str      # nombre del circuito
    track_variation: str      # variante del circuito
    personal_best:   float    # mejor vuelta personal (s)
    world_best:      float    # mejor vuelta mundial (s)


@dataclass
class VehicleInfo:
    """
    Nombre del vehículo para un participante.
    Paquete eParticipantVehicleNames (tipo 8).
    Estructura: 12 bytes header + 16 * (4 index + 4 class + 64 name) = 1164 bytes.
    """
    participant_index: int
    vehicle_name:      str
    car_class:         str


# ---------------------------------------------------------------------------
# Funciones de parseo
# ---------------------------------------------------------------------------

def _packet_type(data: bytes) -> int:
    """Devuelve el tipo de paquete desde el PacketBase (offset 10)."""
    return data[10]


def parse_telemetry(data: bytes) -> Optional[TelemetryFrame]:
    """
    Parsea un paquete eCarPhysics (tipo 0, 556 bytes).
    Offsets absolutos según SMS_UDP_Definitions.hpp con pragma pack(1).
    """
    if len(data) < 556:
        return None

    u = struct.unpack_from

    # Participante observado e indicador de IA
    # sViewedParticipantIndex (offset 12): índice del coche que vemos
    viewed_participant_index = u('b', data, 12)[0]

    # Inputs sin filtrar
    raw_throttle = u('B', data, 13)[0]
    raw_brake    = u('B', data, 14)[0]
    raw_steering = u('b', data, 15)[0]

    # Inputs filtrados
    brake    = u('B', data, 29)[0]
    throttle = u('B', data, 30)[0]
    clutch   = u('B', data, 31)[0]

    fuel_level = u('f', data, 32)[0]
    speed      = u('f', data, 36)[0]
    rpm        = u('H', data, 40)[0]
    max_rpm    = u('H', data, 42)[0]
    steering   = u('b', data, 44)[0]

    gear_byte = u('B', data, 45)[0]
    gear      = gear_byte & 0x0F
    num_gears = (gear_byte >> 4) & 0x0F

    # Vectores de movimiento
    orientation      = u('3f', data, 52)
    local_velocity   = u('3f', data, 64)
    world_velocity   = u('3f', data, 76)
    angular_velocity = u('3f', data, 88)
    local_acceleration = u('3f', data, 100)  # long(X), vert(Y), lat(Z) en m/s²

    # Neumáticos
    tyre_temp       = u('4B', data, 176)
    tyre_wear       = u('4B', data, 196)
    tyre_rps        = u('4f', data, 160)
    tyre_tread_temp = u('4H', data, 216)
    car_flags       = u('B', data, 17)[0]
    terrain         = u('4B', data, 140)   # enum Type#11 — ver pcars2_surface.py

    # Suspensión
    ride_height       = u('4f', data, 296)
    suspension_travel = u('4f', data, 312)

    # Daños
    aero_damage   = u('B', data, 371)[0]
    engine_damage = u('B', data, 372)[0]

    # Posición de alta precisión (offset 542) — clave para el trazado
    position = u('3f', data, 542)

    brake_bias = u('B', data, 554)[0]

    # Tanda 2 (X4b). Offsets deducidos de SMS_UDP_Definitions.hpp y contrastados con los ya conocidos
    # (136, 140, 160, 176, 180, 196, 216, 296, 312, 371, 372, 542, 554); se verifican con datos reales en el informe de C0.
    tyre_flags               = u('4B', data, 136)
    tyre_height_above_ground = u('4f', data, 180)
    brake_damage             = u('4B', data, 200)
    suspension_damage        = u('4B', data, 204)
    brake_temp               = u('4h', data, 208)
    suspension_velocity      = u('4f', data, 328)
    air_pressure             = u('4H', data, 352)
    engine_torque            = u('f', data, 364)[0]
    crash_state              = u('B', data, 47)[0]
    tick_count               = u('B', data, 555)[0]

    # IA humana vs juego: se resuelve en el recorder con sCarIndex del paquete Timings.
    viewed_is_ai = False

    return TelemetryFrame(
        position=position,
        orientation=orientation,
        local_velocity=local_velocity,
        world_velocity=world_velocity,
        angular_velocity=angular_velocity,
        local_acceleration=local_acceleration,
        speed=speed,
        throttle=throttle,
        brake=brake,
        steering=steering,
        clutch=clutch,
        gear=gear,
        num_gears=num_gears,
        raw_throttle=raw_throttle,
        raw_brake=raw_brake,
        raw_steering=raw_steering,
        tyre_temp=tyre_temp,
        tyre_tread_temp=tyre_tread_temp,
        tyre_wear=tyre_wear,
        tyre_rps=tyre_rps,
        terrain=terrain,
        car_flags=car_flags,
        ride_height=ride_height,
        suspension_travel=suspension_travel,
        rpm=rpm,
        max_rpm=max_rpm,
        fuel_level=fuel_level,
        aero_damage=aero_damage,
        engine_damage=engine_damage,
        brake_bias=brake_bias,
        viewed_participant_index=viewed_participant_index,
        viewed_is_ai=viewed_is_ai,
        tyre_flags=tyre_flags,
        tyre_height_above_ground=tyre_height_above_ground,
        brake_damage=brake_damage,
        suspension_damage=suspension_damage,
        brake_temp=brake_temp,
        suspension_velocity=suspension_velocity,
        air_pressure=air_pressure,
        engine_torque=engine_torque,
        crash_state=crash_state,
        tick_count=tick_count,
    )


def parse_game_state(data: bytes) -> Optional[GameStateFrame]:
    """Parsea el paquete eGameState (tipo 4): temperaturas, lluvia, nieve y viento."""
    if len(data) < 22:
        return None
    u = struct.unpack_from
    return GameStateFrame(
        ambient_temp=u('b', data, 15)[0],
        track_temp=u('b', data, 16)[0],
        rain_density=u('B', data, 17)[0],
        snow_density=u('B', data, 18)[0],
        wind_speed=u('b', data, 19)[0],
        wind_dir_x=u('b', data, 20)[0],
        wind_dir_y=u('b', data, 21)[0],
        raw=bytes(data[12:24]),
    )


def parse_timings(
    data: bytes,
    participant_index: Optional[int] = None,
) -> Optional[TimingsFrame]:
    """
    Parsea el paquete eTimings (tipo 3, 1059 bytes).

    participant_index:
      - None (por defecto) → usa sLocalParticipantIndex (jugador local).
      - int                → lee los timings del participante con ese índice.
                             Usar sViewedParticipantIndex para seguir a la IA
                             en práctica libre o como espectador en carrera.
    """
    if len(data) < 1059:
        return None

    u = struct.unpack_from

    event_time_remaining = u('f', data, 17)[0]

    if participant_index is None:
        # Jugador local (modo por defecto / sin espectador)
        local_idx = u('H', data, 1057)[0]
    else:
        local_idx = int(participant_index)

    # Validar que el índice está dentro de los 32 participantes soportados
    if local_idx < 0 or local_idx >= 32:
        local_idx = 0

    # sParticipants[32] empieza en offset 33; cada elemento mide 32 bytes
    p_offset = 33 + local_idx * 32
    if p_offset + 32 > len(data):
        return None

    lap_distance = float(u('H', data, p_offset + 12)[0])    # metros, uint
    race_pos     = u('B', data, p_offset + 14)[0] & 0x7F    # bit 7 = flag activo
    sector_byte  = u('B', data, p_offset + 15)[0]
    sector       = (sector_byte & 0x03) + 1                  # bits 0-1 → 1-based
    # sCarIndex offset 18 dentro de sParticipantInfo:
    # bit 15 = 1 → humano (local o remoto), 0 → IA del juego
    car_index    = u('H', data, p_offset + 18)[0]
    viewed_is_ai = not bool(car_index & 0x8000)
    current_lap  = u('B', data, p_offset + 21)[0]
    current_time = u('f', data, p_offset + 22)[0]
    sector_time  = u('f', data, p_offset + 26)[0]

    return TimingsFrame(
        lap_distance=lap_distance,
        current_lap=current_lap,
        current_time=current_time,
        current_sector_time=sector_time,
        sector=sector,
        race_position=race_pos,
        event_time_remaining=event_time_remaining,
        viewed_is_ai=viewed_is_ai,
    )


def parse_race_data(data: bytes) -> Optional[RaceData]:
    """Parsea el paquete eRaceDefinition (tipo 1, 308 bytes)."""
    if len(data) < 308:
        return None

    u = struct.unpack_from

    world_best    = u('f', data, 12)[0]
    personal_best = u('f', data, 16)[0]
    track_length  = u('f', data, 44)[0]

    track_location  = data[48:112].rstrip(b'\x00').decode('utf-8', errors='replace')
    track_variation = data[112:176].rstrip(b'\x00').decode('utf-8', errors='replace')

    return RaceData(
        track_length=track_length,
        track_location=track_location,
        track_variation=track_variation,
        personal_best=personal_best,
        world_best=world_best,
    )


def parse_vehicle_names(
    data: bytes,
    participant_index: int = 0,
) -> Optional[VehicleInfo]:
    """
    Parsea el paquete eParticipantVehicleNames (tipo 8).

    Estructura por entrada (offset desde inicio del bloque de datos):
      bytes 0-3  : sIndex (uint32) — índice único del participante
      bytes 4-7  : sClass (uint32) — clase / categoría
      bytes 8-71 : sName  (char[64]) — nombre del vehículo
    Cada entrada ocupa 72 bytes; hay 16 entradas; header = 12 bytes.

    participant_index: posición en el array (0..15), NO el índice de sesión.
    Para el jugador en práctica libre usar 0.
    """
    entry_size = 72
    min_size   = 12 + (participant_index + 1) * entry_size
    if len(data) < min_size:
        return None

    offset = 12 + participant_index * entry_size
    p_index = struct.unpack_from('<I', data, offset)[0]
    # class name: a partir de la segunda mitad del bloque de clases (si existe)
    # En la práctica el campo class suele ser un uint; lo omitimos como texto.
    name = data[offset + 8: offset + 8 + 64].rstrip(b'\x00').decode('utf-8', errors='replace')

    return VehicleInfo(
        participant_index=int(p_index),
        vehicle_name=name,
        car_class="",
    )


# ---------------------------------------------------------------------------
# Receptor UDP
# ---------------------------------------------------------------------------

class UDPListener:
    """
    Receptor de paquetes UDP de Project CARS 2.

    Uso recomendado como context manager:
        with UDPListener() as listener:
            ptype, packet = listener.recv()
    """

    def __init__(self, port: int = SMS_UDP_PORT, host: str = "0.0.0.0"):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))

    def recv(self, timeout: float = 1.0, viewed_index: Optional[int] = None):
        """
        Bloquea hasta recibir un paquete (o que expire el timeout).

        viewed_index:
          Índice del participante observado (sViewedParticipantIndex del último
          paquete de telemetría). Cuando se proporciona, los TimingsFrame
          devueltos corresponden a ESE participante (IA o humano que spectamos)
          en lugar del jugador local. Imprescindible para grabar en
          práctica libre con la IA o en modo espectador en carrera.

        Devuelve (packet_type: int, parsed_object) o (None, None) si timeout.
        """
        self._sock.settimeout(max(0.0, timeout))
        try:
            data, _ = self._sock.recvfrom(SMS_UDP_BUFFER_SIZE)
        except socket.timeout:
            return None, None
        except (BlockingIOError, InterruptedError):
            # Windows: timeout=0 → WinError 10035 en vez de socket.timeout
            return None, None
        except OSError as exc:
            if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                return None, None
            raise

        if len(data) < 11:
            return None, None

        ptype = _packet_type(data)

        if ptype == PACKET_CAR_PHYSICS:
            return ptype, parse_telemetry(data)
        elif ptype == PACKET_TIMINGS:
            return ptype, parse_timings(data, participant_index=viewed_index)
        elif ptype == PACKET_GAME_STATE:
            return ptype, parse_game_state(data)
        elif ptype == PACKET_RACE_DEF:
            return ptype, parse_race_data(data)
        elif ptype == PACKET_VEHICLE_NAMES:
            return ptype, parse_vehicle_names(data, participant_index=0)

        return ptype, None

    def drain(self, viewed_index: Optional[int] = None, max_packets: int = 256):
        """
        Lee todos los paquetes UDP pendientes sin bloquear (timeout 0).

        Devuelve lista de (packet_type, parsed_object). Útil para colapsar
        backlog antes de esperar el siguiente frame de física del juego.
        """
        out = []
        for _ in range(max_packets):
            ptype, packet = self.recv(timeout=0.0, viewed_index=viewed_index)
            if ptype is None:
                break
            out.append((ptype, packet))
        return out

    def close(self):
        self._sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# Paquete → atributo de estado (sin prefijo) que lo almacena.
_PACKET_SLOTS = {
    PACKET_CAR_PHYSICS:   "last_telem",
    PACKET_TIMINGS:       "last_timings",
    PACKET_RACE_DEF:      "race_data",
    PACKET_VEHICLE_NAMES: "vehicle_info",
    PACKET_GAME_STATE:    "game_state",
}


def apply_packet(state, ptype: int, packet, prefix: str = "") -> str:
    """
    Guarda `packet` en el atributo correspondiente de `state`
    (`<prefix>last_telem`, `<prefix>last_timings`, `<prefix>race_data`,
    `<prefix>vehicle_info`). Devuelve 'physics', 'timings' u 'other'.
    """
    slot = _PACKET_SLOTS.get(ptype)
    if slot is None or packet is None:
        return "other"
    setattr(state, prefix + slot, packet)
    if ptype == PACKET_CAR_PHYSICS:
        return "physics"
    if ptype == PACKET_TIMINGS:
        return "timings"
    return "other"
