"""
ramp_gate.py
Puerta por ciclos de la rampa de velocidad (C1, D20). Lógica pura, sin juego, como `SpeedGate` de `ppo_guard.py`.

Un ciclo son 1 + `laps_per_cycle` vueltas: la primera sale desde parado tras el ajuste y no puntúa; las otras son las
vueltas lanzadas que juzga la puerta. Un ciclo es limpio si todas sus vueltas lanzadas lo son.
  - `cycles_to_rise` ciclos limpios seguidos -> sube a la banda siguiente (o termina si ya está en la última).
  - un ciclo sucio -> se repite a la misma velocidad.
  - `cycles_to_drop` ciclos sucios seguidos -> baja una banda (o para si ya está en la primera).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

CYCLE_CLEAN, CYCLE_DIRTY, RISE, DROP, TOP, STOP = "cycle_clean", "cycle_dirty", "rise", "drop", "top", "stop"
END_EVENTS = (TOP, STOP)


def bands_from(start_kmh: float, ceiling_kmh: float, step_kmh: float) -> List[float]:
    if step_kmh <= 0 or ceiling_kmh < start_kmh:
        raise ValueError("el paso debe ser positivo y el techo no puede quedar por debajo del inicio")
    bands, v = [], start_kmh
    while v <= ceiling_kmh + 1e-6:
        bands.append(round(v, 1))
        v += step_kmh
    return bands


@dataclass
class RampGate:
    bands: List[float]
    index: int = 0
    laps_per_cycle: int = 2
    cycles_to_rise: int = 2
    cycles_to_drop: int = 3
    pos: int = 0  # vueltas cerradas del ciclo en curso; 0 = la próxima es la de salida
    cycle_clean: bool = True
    clean_cycles: int = 0
    dirty_cycles: int = 0
    message: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        if not self.bands or self.laps_per_cycle < 1 or self.cycles_to_rise < 1 or self.cycles_to_drop < 1:
            raise ValueError("RampGate necesita bandas y parámetros positivos")
        self.index = max(0, min(self.index, len(self.bands) - 1))

    @property
    def band(self) -> float:
        return self.bands[self.index]

    @property
    def cycle_laps(self) -> int:
        return 1 + self.laps_per_cycle

    def on_lap(self, clean: bool) -> Optional[str]:
        """Registra una vuelta cerrada. Devuelve el evento solo al terminar el ciclo (None en las demás)."""
        if self.pos == 0:  # vuelta de salida: no puntúa
            self.pos = 1
            self.cycle_clean = True
            self.message = f"vuelta de salida a {self.band:g} km/h (no puntúa)"
            return None
        self.cycle_clean = self.cycle_clean and clean
        self.pos += 1
        if self.pos < self.cycle_laps:
            self.message = f"ciclo a {self.band:g} km/h: {self.pos - 1}/{self.laps_per_cycle} vueltas lanzadas"
            return None
        self.pos = 0
        return self._close_cycle()

    def _close_cycle(self) -> str:
        if not self.cycle_clean:
            self.clean_cycles = 0
            self.dirty_cycles += 1
            if self.dirty_cycles < self.cycles_to_drop:
                self.message = (
                    f"ciclo sucio a {self.band:g} km/h ({self.dirty_cycles}/{self.cycles_to_drop}); se repite a la misma velocidad"
                )
                return CYCLE_DIRTY
            self.dirty_cycles = 0
            if self.index == 0:
                self.message = f"{self.cycles_to_drop} ciclos sucios seguidos en la banda más baja ({self.band:g} km/h); paro"
                return STOP
            self.index -= 1
            self.message = f"{self.cycles_to_drop} ciclos sucios seguidos: baja a {self.band:g} km/h"
            return DROP
        self.dirty_cycles = 0
        self.clean_cycles += 1
        if self.clean_cycles < self.cycles_to_rise:
            self.message = f"ciclo limpio a {self.band:g} km/h ({self.clean_cycles}/{self.cycles_to_rise})"
            return CYCLE_CLEAN
        self.clean_cycles = 0
        if self.index == len(self.bands) - 1:
            self.message = f"{self.band:g} km/h dominada: techo de la rampa"
            return TOP
        self.index += 1
        self.message = f"{self.cycles_to_rise} ciclos limpios: sube a {self.band:g} km/h"
        return RISE

    def restart_cycle(self) -> None:
        """Descarta el ciclo a medias (al retomar la rampa el coche sale desde parado: la próxima vuelta es la de salida)."""
        self.pos = 0
        self.cycle_clean = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("message")
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "RampGate":
        return cls(**{k: v for k, v in d.items() if k != "message"})

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Optional["RampGate"]:
        """Estado guardado, o None si no hay o no se puede leer."""
        try:
            return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return None
