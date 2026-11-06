"""Gas de salida por curva que se ajusta solo, vuelta a vuelta (opt-in, `--exit-adapt`).

Con `--exit-circle R` el gas en la salida de curva no pasa de `gas_max · √(1 − (lateral medido / R)²)` (V72): un único radio R para toda la vuelta. Aquí cada curva (C1-C14,
`curvas.json`) tiene un multiplicador sobre ese radio. Un radio mayor deja más gas con el mismo lateral; uno menor, menos. Es el mismo esquema que `lat_adapt.py` (hereda de
`LatAdapter` el mapa por curva, las vueltas congeladas, guardar y cargar con las condiciones de la pista y de las gomas): se mide cada curva al cerrar la vuelta y el cambio va
en la vuelta siguiente. Lo que cambia es qué se mide, y solo en la **fase de salida** de la técnica de pedales:

- patinaje con gas: razón de la velocidad de giro de las ruedas traseras entre las delanteras, con el gas por encima de `gas_min` (con tracción normal queda en ≈ 0,97; pasar de
  ≈ 1,0 es que las traseras giran más de lo que el coche avanza);
- deriva máxima y |CTE| máximo de la salida, y ruedas fuera de la superficie de carrera;
- cuánto manda el tope: fracción de los ticks de salida en que el círculo recortaba el gas. Si casi nunca recorta, subir el radio no cambia nada y el multiplicador no sube.

Reglas (los umbrales salen de la sesión `215729Z`, exit 18 con el mapa congelado: razón mediana 0,96-0,98 en todas las salidas, hasta 1,014-1,022 solo en C4 y C5, que son las que
patinaban, 5,2° y 5,7°):

- limpia con margen (razón ≤ `spin_clean`, deriva ≤ `drift_clean_deg`, |CTE| ≤ `cte_clean_m`, 0 ruedas fuera) y el tope recortaba el gas: el multiplicador sube un 4 %;
- fuera de criterio (razón > `spin_bad`, deriva > `drift_bad_deg`, |CTE| > `cte_bad_m` o alguna rueda fuera): baja un 8 % y se congela 2 vueltas;
- en medio, o sin ticks de salida suficientes: se queda como está.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from lat_adapt import LatAdaptConfig, LatAdapter, Zone, drift_deg


@dataclass
class ExitAdaptConfig(LatAdaptConfig):
    # lo heredado, con los valores de la salida de curva (no de la curva entera)
    drift_clean_deg: float = 3.5
    drift_bad_deg: float = 5.0
    cte_clean_m: float = 1.6
    cte_bad_m: float = 2.0
    min_scale: float = 0.7
    max_scale: float = 1.3
    # lo propio del gas de salida
    spin_clean: float = 0.99  # razón ruedas traseras / delanteras con gas hasta la que la salida cuenta como limpia
    spin_bad: float = 1.005  # por encima, las traseras patinan
    gas_min: float = 0.3  # solo se mide el patinaje con el gas por encima de esto
    min_front_rps: float = 5.0  # por debajo (rad/s) el coche está casi parado y la razón no vale
    min_exit_ticks: int = 20  # una curva con menos ticks de salida en la vuelta no se juzga
    min_bound_frac: float = 0.2  # el tope tiene que haber recortado el gas en al menos esta fracción de la salida para que merezca subir


class _ExitAcc:
    __slots__ = ("cte_max", "drift_max", "off", "n", "bound", "spin_max")

    def __init__(self) -> None:
        self.cte_max = 0.0
        self.drift_max = 0.0
        self.off = 0
        self.n = 0  # ticks de salida de esta curva en la vuelta
        self.bound = 0  # de ellos, los que el tope del círculo recortaba el gas
        self.spin_max = 0.0  # razón traseras / delanteras máxima con gas


class ExitAdapter(LatAdapter):
    """Mismo mapa y mismas condiciones que `LatAdapter`; el «límite base» es el radio de `--exit-circle` y el multiplicador, el de esa curva."""

    def __init__(self, zones: Sequence[Zone], base_limit: float, track_length: float, config: Optional[LatAdaptConfig] = None, cap_limit: Optional[float] = None):
        cfg = config or ExitAdaptConfig()
        if not isinstance(cfg, ExitAdaptConfig):
            raise TypeError("ExitAdapter necesita un ExitAdaptConfig")
        # sin `cap_limit`, el tope del radio es el de `max_scale` (el multiplicador ya lo limita)
        super().__init__(zones, base_limit, track_length, cfg, base_limit * cfg.max_scale if cap_limit is None else cap_limit)
        self.cfg: ExitAdaptConfig = cfg
        self._acc: Dict[int, _ExitAcc] = {}  # type: ignore[assignment]

    @classmethod
    def from_curvas_json(cls, path: Path, base_limit: float, track_length: float, config: Optional[LatAdaptConfig] = None, cap_limit: Optional[float] = None) -> "ExitAdapter":  # type: ignore[override]
        import json

        data = json.loads(Path(path).read_text(encoding="utf-8"))
        zones = [Zone(int(c["id"]), float(c["s_ini"]), float(c["s_fin"])) for c in data["curvas"]]
        return cls(zones, base_limit, track_length, config, cap_limit)

    def _reset_lap(self, lap: Optional[int]) -> None:
        super()._reset_lap(lap)
        self._acc = {z.id: _ExitAcc() for z in self.zones}  # type: ignore[assignment]

    def observe(  # type: ignore[override]
        self, lap: int, lap_distance: float, signed_cte: float, local_vx: float, local_vz: float, off_surface: bool, tyre_c: Optional[float] = None, *,
        exit_phase: bool = False, cap_bound: bool = False, throttle: float = 0.0, rps_front: float = 0.0, rps_rear: float = 0.0,
    ) -> Optional[dict]:
        """Un tick. `exit_phase` y `cap_bound` los da el teacher (`exit_phase`, `exit_bound`); `rps_front` / `rps_rear` son la media de la velocidad de giro de las ruedas de cada eje
        (en valor absoluto). Devuelve el resumen del ajuste cuando este tick abre una vuelta nueva y la anterior se pudo evaluar; si no, None."""
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
        if not exit_phase:
            return update
        for i, z in enumerate(self.zones):
            if z.s0 <= lap_distance <= self._zone_end(i):
                a = self._acc[z.id]
                a.n += 1
                a.bound += 1 if cap_bound else 0
                a.cte_max = max(a.cte_max, abs(signed_cte))
                a.drift_max = max(a.drift_max, drift_deg(local_vx, local_vz))
                a.off += 1 if off_surface else 0
                if throttle > self.cfg.gas_min and rps_front > self.cfg.min_front_rps:
                    a.spin_max = max(a.spin_max, rps_rear / rps_front)
                break
        return update

    def _judged(self, a: _ExitAcc) -> bool:
        return a.n >= self.cfg.min_exit_ticks

    def _is_bad(self, a: _ExitAcc) -> bool:  # type: ignore[override]
        c = self.cfg
        return a.cte_max > c.cte_bad_m or a.drift_max > c.drift_bad_deg or a.off > 0 or a.spin_max > c.spin_bad

    def _is_clean(self, a: _ExitAcc) -> bool:
        c = self.cfg
        return (a.cte_max <= c.cte_clean_m and a.drift_max <= c.drift_clean_deg and a.off == 0 and a.spin_max <= c.spin_clean
                and a.bound >= c.min_bound_frac * a.n)

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
        metrics = {str(z.id): {"exit_ticks": self._acc[z.id].n, "bound_frac": round(self._acc[z.id].bound / self._acc[z.id].n, 2) if self._acc[z.id].n else 0.0,
                               "spin_max": round(self._acc[z.id].spin_max, 3), "cte_max": round(self._acc[z.id].cte_max, 2),
                               "drift_max": round(self._acc[z.id].drift_max, 1), "off": self._acc[z.id].off} for z in self.zones}
        return {
            "lap": closed,
            "scales": {str(k): round(v, 4) for k, v in self.scales.items()},
            "decisions": {str(k): v for k, v in decisions.items()},
            "bad": sorted(bad), "tyre_c": None if tyre is None else round(tyre, 1), "cond_factor": None if self.prior is None else round(g_lap, 2),
            "metrics": metrics,
        }

    def limits(self) -> Dict[int, float]:
        """Radio del círculo de salida resultante de cada curva (mismas unidades que `--exit-circle`)."""
        return {k: round(self.base_limit * v, 2) for k, v in self.scales.items()}


__all__: List[str] = ["ExitAdaptConfig", "ExitAdapter"]
