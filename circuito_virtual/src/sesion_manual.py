"""D1b por conducción manual (V77): grabador pasivo de una vuelta conducida por el usuario con dos ruedas sobre la hierba.

No envía ningún mando ni arranca el juego: solo escucha el UDP y escribe un log con lo que lee `bordes_logs.py` (posición, terreno de cada rueda, distancia de
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
from telemetry_udp import PACKET_CAR_PHYSICS, PACKET_TIMINGS, SMS_UDP_PORT, UDPListener  # noqa: E402

CARPETA = REPO / "PCARS2-AI" / "logs" / "manual"
MIN_SPEED_KMH = 10.0  # por debajo de esto no se cuentan los ticks en el resumen (parado o saliendo de boxes)
LADOS = {"izq": LEFT_WHEELS, "dcha": RIGHT_WHEELS}


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
        self._file.write(json.dumps(fila, ensure_ascii=False) + "\n")
        if self.ticks % 100 == 0:
            self._file.flush()
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
    args = ap.parse_args(argv)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ruta = args.carpeta / f"{ts}_{args.track.lower()}_mapeo_{args.lado}.jsonl"
    grabador = GrabadorManual(ruta, args.lado, args.laps, args.track)
    grabador.abrir()
    print(f"Grabando {ruta} (lado {args.lado}, {args.laps} vueltas). Conduce tú; Ctrl+C para terminar antes.", flush=True)
    ultimo_aviso = time.monotonic()
    try:
        with UDPListener(args.puerto) as escucha:
            while not grabador.terminado:
                ptype, paquete = escucha.recv(timeout=1.0)
                grabador.procesar(ptype, paquete)
                if time.monotonic() - ultimo_aviso > 5.0:
                    ultimo_aviso = time.monotonic()
                    print(f"  {grabador.ticks} ticks, {grabador.vueltas_completas}/{args.laps} vueltas", flush=True)
    except KeyboardInterrupt:
        print("Interrumpido.")
    finally:
        grabador.cerrar()
    print(grabador.resumen())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
