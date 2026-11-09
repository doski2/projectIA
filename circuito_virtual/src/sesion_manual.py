"""D1b por conducción manual (V77): grabador pasivo de una vuelta conducida por el usuario con dos ruedas sobre la hierba.

Por defecto no envía ningún mando ni arranca el juego (con `--velocidad-auto KMH` lleva el gas y el freno por un mando virtual y el usuario solo gira): solo escucha el UDP y escribe un log con lo que lee `bordes_logs.py` (posición, terreno de cada rueda, distancia de
vuelta). Es el equivalente a las rondas del teacher de `PLAN.md` (D1b), pero con el usuario llevando las dos ruedas de un lado fuera del asfalto: la rueda que
sigue dentro y la que ya está fuera acotan el borde con pocos centímetros.

Uso (el usuario conduce, p. ej. a 60 km/h con el limitador; no lanzar a la vez `learn_driver.py` ni `teaching_driver.py`, comparten el puerto UDP):
    python circuito_virtual/src/sesion_manual.py --lado izq --laps 3
    python circuito_virtual/src/sesion_manual.py --lado dcha --laps 3
El log queda en `PCARS2-AI/logs/manual/`; después, `python circuito_virtual/src/bordes_logs.py actualizar` lo añade a las cotas de los bordes.
Termina solo al completar `--laps` vueltas, o con Ctrl+C.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "PCARS2-AI" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from circuito_virtual.src.bordes_logs import LEFT_WHEELS, RIGHT_WHEELS  # noqa: E402
from pcars2_surface import RACING_TERRAIN_IDS  # noqa: E402
from session_log import GAME_PROFILE, LOG_SCHEMA  # noqa: E402
from telemetry_udp import PACKET_CAR_PHYSICS, PACKET_TIMINGS, SMS_UDP_PORT, TelemetryFrame, UDPListener  # noqa: E402

CARPETA = REPO / "PCARS2-AI" / "logs" / "manual"
MIN_SPEED_KMH = 10.0  # por debajo de esto no se cuentan los ticks en el resumen (parado o saliendo de boxes)
LADOS = {"izq": LEFT_WHEELS, "dcha": RIGHT_WHEELS}


class ControlVelocidad:
    """Gas y freno que mantienen una velocidad objetivo (PI con zona muerta de freno). El volante no se toca: lo lleva el usuario.

    `paso(v_kmh, dt_s, freno_usuario)` devuelve `(gas, freno)` en [0, 1]. Si el usuario pisa su propio freno, el gas se corta y la integral se reinicia.
    """

    KP = 0.05          # gas por km/h de error
    KI = 0.02          # gas por km/h·s de error acumulado
    GAS_BASE = 0.20    # gas de mantenimiento a 30 km/h en llano
    GAS_MAX = 0.70     # tope del gas (el monoplaza patina con más a baja velocidad)
    FRENO_DESDE = 6.0  # km/h por encima del objetivo desde los que se frena (por debajo basta soltar el gas)
    KF = 0.04          # freno por km/h por encima de esa zona
    FRENO_MAX = 0.50
    INTEGRAL_MAX = 15.0  # km/h·s, antiwindup

    def __init__(self, objetivo_kmh: float):
        if objetivo_kmh <= 0:
            raise ValueError("la velocidad objetivo debe ser positiva")
        self.objetivo = float(objetivo_kmh)
        self._integral = 0.0

    def paso(self, v_kmh: float, dt_s: float, freno_usuario: bool = False) -> tuple[float, float]:
        if freno_usuario:
            self._integral = 0.0
            return 0.0, 0.0
        error = self.objetivo - v_kmh
        if error < 0:
            freno = min(self.FRENO_MAX, self.KF * max(0.0, -error - self.FRENO_DESDE))
            self._integral = max(0.0, self._integral + error * dt_s)  # al pasarse, la integral solo baja
            return 0.0, freno
        gas_sin_tope = self.GAS_BASE + self.KP * error + self.KI * self._integral
        gas = min(self.GAS_MAX, gas_sin_tope)
        if gas_sin_tope < self.GAS_MAX:  # sin saturar: acumular
            self._integral = min(self.INTEGRAL_MAX, self._integral + error * dt_s)
        return max(0.0, gas), 0.0


class AvisoGasAjeno:
    """Detecta que el usuario pisa su propio gas con `--velocidad-auto` (la telemetría lleva más gas del que manda el programa).

    `paso(gas_telemetria, gas_enviado, ahora_s)` devuelve True una vez cada `REPETIR_S` mientras el exceso dure más de `DESDE_S`.
    """

    EXCESO = 0.30
    DESDE_S = 1.0
    REPETIR_S = 5.0

    def __init__(self):
        self._desde: Optional[float] = None
        self._ultimo_aviso = -1e9

    def paso(self, gas_telemetria: float, gas_enviado: float, ahora_s: float) -> bool:
        if gas_telemetria - gas_enviado <= self.EXCESO:
            self._desde = None
            return False
        if self._desde is None:
            self._desde = ahora_s
        if ahora_s - self._desde >= self.DESDE_S and ahora_s - self._ultimo_aviso >= self.REPETIR_S:
            self._ultimo_aviso = ahora_s
            return True
        return False


class GrabadorManual:
    """Convierte los paquetes de física y de tiempos en ticks del log de esquema 3. Sin red: `procesar` recibe los paquetes ya parseados."""

    def __init__(self, ruta: Path, lado: str, vueltas: int = 3, track: str = "SUGO_GP", reloj: Callable[[], float] = time.monotonic):
        if lado not in LADOS:
            raise ValueError(f"lado debe ser 'izq' o 'dcha', no {lado!r}")
        self.ruta = Path(ruta)
        self.lado = lado
        self.vueltas = vueltas
        self.track = track
        self._reloj = reloj
        self._t0: Optional[float] = None
        self._file = None
        self._telem = None
        self._timings = None
        self._vuelta_ini: Optional[int] = None
        self._vuelta_actual = 0
        self.ticks = 0
        self.ticks_ia = 0
        self.resumen_ticks: Dict[str, int] = {"en_marcha": 0, "lado_dos_fuera": 0, "lado_una_fuera": 0, "otro_lado_fuera": 0}

    def abrir(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.ruta, "w", encoding="utf-8")
        cabecera = {
            "type": "session", "ts": datetime.now(timezone.utc).isoformat(), "log_schema": LOG_SCHEMA, "origin": "manual",
            "game_profile": GAME_PROFILE, "mode": "manual_edge", "phase": f"mapeo_{self.lado}", "track": self.track, "side": self.lado,
            "laps_requested": self.vueltas,
        }
        self._file.write(json.dumps(cabecera, ensure_ascii=False) + "\n")
        self._file.flush()

    @property
    def terminado(self) -> bool:
        return self._vuelta_ini is not None and self._vuelta_actual - self._vuelta_ini >= self.vueltas

    @property
    def vueltas_completas(self) -> int:
        return 0 if self._vuelta_ini is None else max(0, self._vuelta_actual - self._vuelta_ini)

    def procesar(self, ptype: int, paquete) -> bool:
        """Guarda el paquete; con uno de física y tiempos ya conocidos escribe un tick. Devuelve True si lo escribió."""
        if paquete is None:
            return False
        if ptype == PACKET_TIMINGS:
            self._timings = paquete
            return False
        if ptype != PACKET_CAR_PHYSICS:
            return False
        self._telem = paquete
        if self._timings is None or self._file is None:
            return False
        if getattr(paquete, "viewed_is_ai", False):
            self.ticks_ia += 1  # se está viendo a una IA: esos datos no son del usuario
            return False
        self._escribir(paquete, self._timings)
        return True

    def _escribir(self, t, tm) -> None:
        ahora = self._reloj()
        if self._t0 is None:
            self._t0 = ahora
        if self._vuelta_ini is None:
            self._vuelta_ini = tm.current_lap
        self._vuelta_actual = max(self._vuelta_actual, tm.current_lap)
        self.ticks += 1
        velocidad_kmh = t.speed * 3.6
        terreno = [int(v) for v in t.terrain]
        fila = {
            "type": "tick", "tick": self.ticks, "t_s": round(ahora - self._t0, 3), "lap": tm.current_lap,
            "lap_distance": round(tm.lap_distance, 2), "speed_kmh": round(velocidad_kmh, 2),
            "throttle": round(t.throttle / 255, 3), "brake": round(t.brake / 255, 3), "steering": round(t.steering / 127, 3), "gear": t.gear,
            "vehicle": {
                "position": [round(v, 3) for v in t.position], "orientation": [round(v, 4) for v in t.orientation],
                "terrain": terreno, "tyre_rps": [round(v, 2) for v in t.tyre_rps], "tyre_flags": list(t.tyre_flags),
            },
            "timing": {"sector": tm.sector, "sector_time_s": round(tm.current_sector_time, 2), "game_time_s": round(tm.current_time, 2)},
        }
        archivo = self._file
        if archivo is None:
            return
        archivo.write(json.dumps(fila, ensure_ascii=False) + "\n")
        if self.ticks % 100 == 0:
            archivo.flush()
        if velocidad_kmh >= MIN_SPEED_KMH:
            fuera_lado = sum(terreno[i] not in RACING_TERRAIN_IDS for i in LADOS[self.lado])
            otro = LADOS["dcha" if self.lado == "izq" else "izq"]
            self.resumen_ticks["en_marcha"] += 1
            self.resumen_ticks["lado_dos_fuera"] += fuera_lado == 2
            self.resumen_ticks["lado_una_fuera"] += fuera_lado == 1
            self.resumen_ticks["otro_lado_fuera"] += any(terreno[i] not in RACING_TERRAIN_IDS for i in otro)

    def resumen(self) -> str:
        r = self.resumen_ticks
        n = max(1, r["en_marcha"])
        return (f"{self.ticks} ticks en {self.ruta.name}, {self.vueltas_completas} vueltas completas; con el coche en marcha (> {MIN_SPEED_KMH:g} km/h): "
                f"{100 * r['lado_dos_fuera'] / n:.0f} % con las dos ruedas del lado {self.lado} fuera, {100 * r['lado_una_fuera'] / n:.0f} % con una, "
                f"{100 * r['otro_lado_fuera'] / n:.0f} % con alguna del lado contrario fuera"
                + (f"; {self.ticks_ia} paquetes de una IA descartados" if self.ticks_ia else ""))

    def cerrar(self) -> None:
        if self._file is not None:
            self._file.flush()
            self._file.close()
            self._file = None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--lado", choices=sorted(LADOS), required=True, help="lado cuyas dos ruedas van sobre la hierba")
    ap.add_argument("--laps", type=int, default=3, help="vueltas completas tras las que termina solo")
    ap.add_argument("--puerto", type=int, default=SMS_UDP_PORT)
    ap.add_argument("--carpeta", type=Path, default=CARPETA)
    ap.add_argument("--track", default="SUGO_GP")
    ap.add_argument("--velocidad-auto", type=float, default=0.0, metavar="KMH",
                    help="el programa lleva el gas y el freno (mando virtual) para mantener esta velocidad y tú solo giras; 0 = conduces tú todo")
    ap.add_argument("--gamepad", choices=["xbox", "ds4"], default="xbox", help="tipo de mando virtual con --velocidad-auto")
    args = ap.parse_args(argv)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ruta = args.carpeta / f"{ts}_{args.track.lower()}_mapeo_{args.lado}.jsonl"
    grabador = GrabadorManual(ruta, args.lado, args.laps, args.track)
    grabador.abrir()
    mando = None
    control = None
    if args.velocidad_auto > 0:
        from controller import DS4Controller  # noqa: E402  (vgamepad solo hace falta con --velocidad-auto)

        control = ControlVelocidad(args.velocidad_auto)
        mando = DS4Controller(mode=args.gamepad)
    modo = f"gas y freno automáticos a {args.velocidad_auto:g} km/h, tú solo el volante" if control else "conduces tú"
    print(f"Grabando {ruta} (lado {args.lado}, {args.laps} vueltas; {modo}). Ctrl+C para terminar antes.", flush=True)
    ultimo_aviso = time.monotonic()
    t_previo = time.monotonic()
    freno_enviado = 0.0
    gas_enviado = 0.0
    aviso_gas = AvisoGasAjeno()
    try:
        with UDPListener(args.puerto) as escucha:
            while not grabador.terminado:
                ptype, paquete = escucha.recv(timeout=1.0)
                if ptype is not None:
                    grabador.procesar(ptype, paquete)
                if control is not None and mando is not None and ptype == PACKET_CAR_PHYSICS and isinstance(paquete, TelemetryFrame) \
                        and not getattr(paquete, "viewed_is_ai", False):
                    ahora = time.monotonic()
                    # el freno de la telemetría que no hemos mandado nosotros es del usuario: cede el gas
                    freno_usuario = paquete.brake / 255 > 0.15 and freno_enviado < 0.05
                    gas, freno = control.paso(paquete.speed * 3.6, min(0.2, ahora - t_previo), freno_usuario)
                    t_previo = ahora
                    freno_enviado = freno
                    if aviso_gas.paso(paquete.throttle / 255, gas_enviado, ahora):
                        print("  AVISO: se está pisando el gas por otro lado (pedales del volante); suéltalo, el programa lleva el gas", flush=True)
                    gas_enviado = gas
                    mando.apply_action(throttle=gas, brake=freno, steering=0.0)
                if time.monotonic() - ultimo_aviso > 5.0:
                    ultimo_aviso = time.monotonic()
                    print(f"  {grabador.ticks} ticks, {grabador.vueltas_completas}/{args.laps} vueltas", flush=True)
    except KeyboardInterrupt:
        print("Interrumpido.")
    finally:
        if mando is not None:
            mando.release()
        grabador.cerrar()
    print(grabador.resumen())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
