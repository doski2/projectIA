"""Deceleración de frenada por zona que se ajusta sola, vuelta a vuelta (opt-in, `--brake-adapt`).

Con `--brake-profile` el teacher calcula la velocidad objetivo v*(s) con un barrido hacia atrás que usa una deceleración `a_b` (`--brake-decel-straight`) igual en toda la vuelta: de
ella salen dónde empieza cada frenada y cuánto pedal pide. Aquí cada frenada (la que prepara cada curva C1-C14: desde la salida de la curva anterior hasta la salida de ésta; la
de la recta de meta es la de C1) tiene un multiplicador sobre `a_b`. Un multiplicador bajo hace que el perfil empiece a frenar antes; uno alto, más tarde. Hereda de `LatAdapter` el
mapa por zona, las vueltas congeladas y guardar / cargar con las condiciones de la pista y de las gomas (como `exit_adapt.py`): se mide al cerrar cada vuelta y el cambio va en
la siguiente.

**Qué se mide** (solo en la fase de entrada con el pedal de freno pisado): con qué velocidad sobre el perfil se **suelta** el freno (media de los 5 últimos ticks de la zona, en
m/s: positivo = se llega a la curva más rápido de lo previsto) y, como contexto, el pedal máximo y la escala mínima del limitador de deslizamiento. El limitador **no** es la señal
de «frenar menos»: en seco actúa fuerte en seis frenadas (escala mínima 0,25-0,38, deslizamiento de las delanteras 0,35 frente al objetivo de 0,25) y aun así 11 m/s² frena mejor que
10 (1:51.291 de media frente a 1:51.484); lo que cuenta es dónde acaba la frenada.

Reglas (los umbrales salen de las sesiones `215729Z` y `222024Z`, en seco: la velocidad al soltar queda entre −0,8 y +0,5 m/s sobre el perfil):

- llega pasado (> `over_bad_ms`, 1,0 m/s ≈ 3,6 km/h sobre el perfil): la deceleración baja un 8 % y se congela 2 vueltas. Es lo que pasaría en mojado, con gomas frías o con unos frenos que
  ya no dan 11 m/s²;
- llega por debajo con holgura (< `early_ms`, −0,3 m/s) y sin forzar (pedal máximo < `pedal_sat`, el limitador casi sin actuar): sube un 4 %, es decir, frena más tarde;
- en medio, o con pocos ticks de frenada: se queda como está.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from lat_adapt import LatAdaptConfig, LatAdapter, Zone


@dataclass
class BrakeAdaptConfig(LatAdaptConfig):
    min_scale: float = 0.6
    max_scale: float = 1.15
    over_bad_ms: float = 1.0  # al soltar el freno, más de esto por encima del perfil = se llega pasado
    early_ms: float = -0.3  # al soltar, por debajo de esto = se frenó más de la cuenta
    pedal_sat: float = 0.9  # con el pedal máximo por encima de esto la frenada va al límite: no se pide más
    limiter_clean: float = 0.8  # escala mínima del limitador por debajo de la cual la frenada está en su límite de agarre: no se pide más
    min_brake_ticks: int = 15  # una zona con menos ticks de frenada en la vuelta no se juzga
    last_ticks: int = 5  # los últimos ticks de la frenada que dan la velocidad con que se suelta


class _BrakeAcc:
    __slots__ = ("n", "pedal_max", "scale_min", "over", "over_max")

    def __init__(self) -> None:
        self.n = 0
        self.pedal_max = 0.0
        self.scale_min = 1.0
        self.over: List[float] = []  # exceso sobre el perfil de los últimos ticks de frenada
        self.over_max = float("-inf")


class BrakeAdapter(LatAdapter):
    """Mismo mapa y mismas condiciones que `LatAdapter`; el «límite base» es `--brake-decel-straight` y el multiplicador, el de la frenada de esa curva."""

    def __init__(self, zones: Sequence[Zone], base_limit: float, track_length: float, config: Optional[LatAdaptConfig] = None, cap_limit: Optional[float] = None):
        cfg = config or BrakeAdaptConfig()
        if not isinstance(cfg, BrakeAdaptConfig):
            raise TypeError("BrakeAdapter necesita un BrakeAdaptConfig")
        super().__init__(zones, base_limit, track_length, cfg, base_limit * cfg.max_scale if cap_limit is None else cap_limit)
        self.cfg: BrakeAdaptConfig = cfg
        self._acc: Dict[int, _BrakeAcc] = {}  # type: ignore[assignment]
        self._ends = [z.s1 for z in self.zones]  # la frenada de cada curva acaba donde acaba la curva; pasada la última, es la de C1 (recta de meta)

    @classmethod
    def from_curvas_json(cls, path: Path, base_limit: float, track_length: float, config: Optional[LatAdaptConfig] = None, cap_limit: Optional[float] = None) -> "BrakeAdapter":  # type: ignore[override]
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        zones = [Zone(int(c["id"]), float(c["s_ini"]), float(c["s_fin"])) for c in data["curvas"]]
        return cls(zones, base_limit, track_length, config, cap_limit)

    def zone_id(self, lap_distance: float) -> int:
        """Curva cuya frenada cubre esta distancia de vuelta."""
        for z, end in zip(self.zones, self._ends):
            if lap_distance <= end:
                return z.id
        return self.zones[0].id

    def _reset_lap(self, lap: Optional[int]) -> None:
        super()._reset_lap(lap)
        self._acc = {z.id: _BrakeAcc() for z in self.zones}  # type: ignore[assignment]

    def observe(  # type: ignore[override]
        self, lap: int, lap_distance: float, signed_cte: float, local_vx: float, local_vz: float, off_surface: bool, tyre_c: Optional[float] = None, *,
        braking: bool = False, pedal: float = 0.0, limiter_scale: float = 1.0, over_ms: float = 0.0,
    ) -> Optional[dict]:
        """Un tick. `braking` = fase de entrada de la técnica de pedales; `pedal` = pedal de freno que sale al juego; `limiter_scale` = escala del limitador de deslizamiento (1,0 = sin actuar);
        `over_ms` = velocidad menos v*(s) del perfil, en m/s. Devuelve el resumen del ajuste cuando este tick abre una vuelta nueva y la anterior se pudo evaluar; si no, None."""
        update = None
        if lap != self._lap:
            if self._lap is not None and self._lap >= self.cfg.first_lap:
                update = self._close_lap()
            self._reset_lap(lap)
        if lap < self.cfg.first_lap:
            return update
        if tyre_c is not None:
            self._tyre[0] += float(tyre_c)
            self._tyre[1] += 1.0
        self._d_min = min(self._d_min, lap_distance)
        self._d_max = max(self._d_max, lap_distance)
        if braking and pedal > 0.02:
            a = self._acc[self.zone_id(lap_distance)]
            a.n += 1
            a.pedal_max = max(a.pedal_max, pedal)
            a.scale_min = min(a.scale_min, limiter_scale)
            a.over.append(over_ms)
            del a.over[:-self.cfg.last_ticks]
            a.over_max = max(a.over_max, over_ms)
        return update

    def _release_over(self, a: _BrakeAcc) -> float:
        return sum(a.over) / len(a.over) if a.over else 0.0

    def _judged(self, a: _BrakeAcc) -> bool:
        return a.n >= self.cfg.min_brake_ticks

    def _is_bad(self, a: _BrakeAcc) -> bool:  # type: ignore[override]
        return self._release_over(a) > self.cfg.over_bad_ms

    def _is_clean(self, a: _BrakeAcc) -> bool:
        c = self.cfg
        return self._release_over(a) < c.early_ms and a.pedal_max < c.pedal_sat and a.scale_min >= c.limiter_clean

    def _close_lap(self) -> Optional[dict]:
        cfg = self.cfg
        if self._d_max - self._d_min < cfg.min_coverage * self.track_length:
            return None  # vuelta incompleta (reinicio, corte): no se fía
        closed = self._lap
        assert closed is not None  # solo se cierra una vuelta que estaba en curso
        tyre = self._tyre[0] / self._tyre[1] if self._tyre[1] else None
        if tyre is not None:
            self.tyre_by_lap[closed] = tyre
        g_lap = self._lap_mismatch(closed, tyre)
        up = cfg.up * (1.0 - (1.0 - cfg.climb_min_factor) * g_lap)
        bad = {z.id for z in self.zones if self._judged(self._acc[z.id]) and self._is_bad(self._acc[z.id])}
        self._bad_by_lap.append(sorted(bad))
        decisions: Dict[int, str] = {}
        for z in self.zones:
            a = self._acc[z.id]
            if not self._judged(a):
                decisions[z.id] = "sin datos"
                continue
            if not cfg.learn:
                decisions[z.id] = "fijo"
                continue
            if z.id in bad:
                self.scales[z.id] = max(cfg.min_scale, self.scales[z.id] * (1.0 - cfg.down))
                self.frozen[z.id] = cfg.freeze_laps
                decisions[z.id] = "baja"
            elif self.frozen[z.id] > 0:
                self.frozen[z.id] -= 1
                decisions[z.id] = "congelada"
            elif self._is_clean(a):
                self.scales[z.id] = min(self.max_scale, self.scales[z.id] * (1.0 + up))
                decisions[z.id] = "sube"
            else:
                decisions[z.id] = "igual"
        metrics = {str(z.id): {"brake_ticks": self._acc[z.id].n, "release_over_ms": round(self._release_over(self._acc[z.id]), 2) if self._acc[z.id].n else 0.0,
                               "over_max_ms": round(self._acc[z.id].over_max, 2) if self._acc[z.id].n else 0.0, "pedal_max": round(self._acc[z.id].pedal_max, 2),
                               "limiter_min": round(self._acc[z.id].scale_min, 2)} for z in self.zones}
        return {
            "lap": closed,
            "scales": {str(k): round(v, 4) for k, v in self.scales.items()},
            "decisions": {str(k): v for k, v in decisions.items()},
            "bad": sorted(bad), "tyre_c": None if tyre is None else round(tyre, 1), "cond_factor": None if self.prior is None else round(g_lap, 2),
            "metrics": metrics,
        }

    def scales_per_m(self, n: Optional[int] = None) -> List[float]:
        """Multiplicador de la deceleración por metro de vuelta: cada metro lleva el de la frenada de la curva que viene (la de C1 incluye la recta de meta)."""
        import math

        n = int(n or math.ceil(self.track_length))
        return [self.scales[self.zone_id(float(d))] for d in range(n)]

    def limits(self) -> Dict[int, float]:
        """Deceleración de frenada resultante de cada curva en m/s² (con la misma unidad que `--brake-decel-straight`)."""
        return {k: round(self.base_limit * v, 2) for k, v in self.scales.items()}


__all__: List[str] = ["BrakeAdaptConfig", "BrakeAdapter"]
