"""Límite lateral por curva que se ajusta solo, vuelta a vuelta (opt-in, `--lat-adapt`).

Hasta ahora el teacher usa un único `lat_accel_limit` para toda la vuelta. Aquí cada curva (C1-C14, `curvas.json`) tiene un multiplicador sobre ese límite:
empieza en 1,0 (comportamiento idéntico al de siempre) y al cerrar cada vuelta se mide cada curva con lo que ya registramos (|CTE| máximo, deriva máxima y ruedas
fuera de la superficie de carrera):

- limpia con margen (|CTE| ≤ 1,2 m, deriva ≤ 3°, 0 ruedas fuera) y sin vecinas en mal estado: el multiplicador sube un 4 %;
- fuera de criterio (|CTE| > 1,8 m, deriva > 4° o alguna rueda fuera): baja un 8 % y se congela 2 vueltas (no sube aunque salga limpia);
- en medio: se queda como está.

Topes: multiplicador entre 0,7 y `max_scale` (1,15), y el límite resultante nunca pasa de `cap_limit` (10 m/s² por defecto: con 10 en toda la vuelta se ganaba 1,9 s pero no
se cumplía V19). La vuelta de salida (índice < 2) no cuenta. El ajuste va en la vuelta siguiente, no dentro de la misma vuelta.

Guardar y cargar el mapa (`--lat-adapt-save` / `--lat-adapt-load`): al cerrar cada vuelta con las dos últimas limpias (ninguna curva «baja») se guarda un JSON con los
multiplicadores y las condiciones (lluvia, temperatura de pista, compuesto, temperatura de las gomas al empezar y por vuelta). Al cargarlo, el mapa solo se aplica si es compatible
(seco con seco, mismo compuesto) y **solo puede frenar, nunca acelerar** respecto al ajuste normal: si las condiciones de hoy se parecen menos a las guardadas, el margen
sobre 1,0 de cada curva se recorta (hasta quedarse en el límite base si son muy distintas, sea más frío o más caliente) y, vuelta a vuelta, la subida baja hasta la mitad
mientras las gomas no sigan la misma curva de temperatura que cuando se guardó. `--lat-adapt-fixed` carga el mapa y no aprende (para comparar una sola variable).
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence


@dataclass
class LatAdaptConfig:
    up: float = 0.04  # subida del multiplicador de una curva limpia con margen
    down: float = 0.08  # bajada de una curva fuera de criterio (el doble que la subida: tiende a la prudencia)
    cte_clean_m: float = 1.2
    drift_clean_deg: float = 3.0
    cte_bad_m: float = 1.8  # V19
    drift_bad_deg: float = 4.0  # V19
    min_scale: float = 0.7
    max_scale: float = 1.15
    freeze_laps: int = 2
    first_lap: int = 2  # la vuelta 1 lleva la salida parada y no cuenta
    exit_margin_m: float = 15.0  # la zona de una curva llega hasta su salida más este margen
    min_coverage: float = 0.9  # fracción de la vuelta que hay que haber visto para fiarse de ella
    learn: bool = True  # False: mapa fijo (se mide y se registra, pero no cambia ningún multiplicador)
    tyre_dead_c: float = 5.0  # diferencia de temperatura de las gomas respecto a lo guardado que no cuenta
    tyre_span_c: float = 15.0  # a dead + span de diferencia, el desajuste es total (1,0)
    track_dead_c: float = 4.0
    track_span_c: float = 11.0
    climb_min_factor: float = 0.5  # con desajuste total la subida de una curva limpia es la mitad


@dataclass
class Zone:
    id: int
    s0: float
    s1: float


def drift_deg(local_vx: float, local_vz: float, min_speed_ms: float = 5.0) -> float:
    """Ángulo de deriva en grados (como en `resumen_sesion.py`): 0 por debajo de `min_speed_ms`. El eje 2 de `local_velocity` es negativo al avanzar."""
    forward = -float(local_vz)
    if forward <= min_speed_ms:
        return 0.0
    return abs(math.degrees(math.atan2(float(local_vx), forward)))


class _Acc:
    __slots__ = ("cte_max", "drift_max", "off", "n")

    def __init__(self) -> None:
        self.cte_max = 0.0
        self.drift_max = 0.0
        self.off = 0
        self.n = 0


class LatAdapter:
    def __init__(self, zones: Sequence[Zone], base_limit: float, track_length: float, config: Optional[LatAdaptConfig] = None, cap_limit: float = 10.0):
        if base_limit <= 0.0:
            raise ValueError("--lat-adapt necesita --lat-accel-limit")
        self.zones: List[Zone] = sorted(zones, key=lambda z: z.s0)
        self.base_limit = float(base_limit)
        self.track_length = float(track_length)
        self.cfg = config or LatAdaptConfig()
        # el límite resultante no pasa de `cap_limit`; si el límite base ya lo supera, las curvas no suben (tope 1,0) pero pueden bajar
        self.cap_limit = float(cap_limit)
        self.max_scale = max(1.0, min(self.cfg.max_scale, cap_limit / self.base_limit))
        self.scales: Dict[int, float] = {z.id: 1.0 for z in self.zones}
        self.frozen: Dict[int, int] = {z.id: 0 for z in self.zones}
        self._lap: Optional[int] = None
        self._acc: Dict[int, _Acc] = {}
        self._d_min = float("inf")
        self._d_max = float("-inf")
        self._tyre: List[float] = [0.0, 0.0]  # suma y cuenta de la temperatura media de las gomas en la vuelta en curso
        self.tyre_by_lap: Dict[int, float] = {}
        self._bad_by_lap: List[List[int]] = []
        self.prior: Optional[dict] = None  # mapa cargado (None = sin mapa o descartado por incompatible)
        self.prior_pending = False
        self.start_conditions: Optional[dict] = None
        self.mismatch = 0.0  # desajuste de condiciones al empezar (0 = iguales a lo guardado, 1 = muy distintas)
        self._g_track = 0.0

    @classmethod
    def from_curvas_json(cls, path: Path, base_limit: float, track_length: float, config: Optional[LatAdaptConfig] = None, cap_limit: float = 10.0) -> "LatAdapter":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        zones = [Zone(int(c["id"]), float(c["s_ini"]), float(c["s_fin"])) for c in data["curvas"]]
        return cls(zones, base_limit, track_length, config, cap_limit)

    def _zone_end(self, i: int) -> float:
        """Fin de la zona de la curva `i`: su salida más el margen, sin pasar del inicio de la siguiente."""
        end = self.zones[i].s1 + self.cfg.exit_margin_m
        if i + 1 < len(self.zones):
            end = min(end, self.zones[i + 1].s0)
        return end

    def _reset_lap(self, lap: Optional[int]) -> None:
        self._lap = lap
        self._acc = {z.id: _Acc() for z in self.zones}
        self._d_min, self._d_max = float("inf"), float("-inf")
        self._tyre = [0.0, 0.0]

    @staticmethod
    def _frac(delta: float, dead: float, span: float) -> float:
        return min(1.0, max(0.0, (abs(delta) - dead) / span))

    def load_prior(self, data: dict) -> None:
        """Deja un mapa guardado a la espera de las condiciones de hoy (`start`)."""
        if not isinstance(data.get("scales"), dict):
            raise ValueError("el mapa guardado no trae «scales»")
        self.prior, self.prior_pending = data, True

    def start(self, now: dict) -> Optional[dict]:
        """Primer instante con las condiciones conocidas (lluvia, pista, gomas, compuesto). Guarda esas condiciones y, si hay un mapa pendiente, lo aplica. Devuelve el resumen de lo aplicado o None."""
        self.start_conditions = dict(now)
        if not self.prior_pending:
            return None
        self.prior_pending = False
        prior = self.prior
        assert prior is not None  # `prior_pending` solo se activa en `load_prior`
        ref = prior.get("conditions") or {}
        if bool(ref.get("rain")) != bool(now.get("rain")):
            self.prior = None
            return {"applied": False, "reason": "lluvia distinta a la del mapa guardado"}
        if ref.get("compound") and now.get("compound") and ref["compound"] != now["compound"]:
            self.prior = None
            return {"applied": False, "reason": f"compuesto distinto ({now['compound']} frente a {ref['compound']})"}
        cfg = self.cfg
        g_track = 0.0
        if ref.get("track_c") is not None and now.get("track_c") is not None:
            g_track = self._frac(now["track_c"] - ref["track_c"], cfg.track_dead_c, cfg.track_span_c)
        g_tyre = 0.0
        if ref.get("tyre_start_c") is not None and now.get("tyre_start_c") is not None:
            g_tyre = self._frac(now["tyre_start_c"] - ref["tyre_start_c"], cfg.tyre_dead_c, cfg.tyre_span_c)
        self._g_track = g_track
        self.mismatch = max(g_track, g_tyre)
        base_saved = float(prior.get("base_limit") or self.base_limit)
        for z in self.zones:
            saved = prior["scales"].get(str(z.id))
            if saved is None:
                continue
            s = base_saved * float(saved) / self.base_limit  # el mapa guarda multiplicadores sobre su límite base
            s = 1.0 + (s - 1.0) * (1.0 - self.mismatch) if s > 1.0 else s
            self.scales[z.id] = min(self.max_scale, max(cfg.min_scale, s))
        return {"applied": True, "mismatch": round(self.mismatch, 2), "mismatch_track": round(g_track, 2), "mismatch_tyre": round(g_tyre, 2),
                "scales": {str(k): round(v, 4) for k, v in self.scales.items()}}

    def _lap_mismatch(self, lap: int, tyre: Optional[float]) -> float:
        """Desajuste de esta vuelta: el de la pista al empezar y el de las gomas frente a la misma vuelta del mapa guardado (o su temperatura de régimen)."""
        if self.prior is None:
            return 0.0
        g = self._g_track
        ref = (self.prior.get("tyre_by_lap") or {}).get(str(lap))
        if ref is None:
            ref = (self.prior.get("conditions") or {}).get("tyre_ref_c")
        if tyre is not None and ref is not None:
            g = max(g, self._frac(tyre - float(ref), self.cfg.tyre_dead_c, self.cfg.tyre_span_c))
        return g

    def clean_tail(self) -> bool:
        """Al menos 3 vueltas cerradas y ninguna curva «baja» en las dos últimas: el mapa es digno de guardarse."""
        return len(self._bad_by_lap) >= 3 and not self._bad_by_lap[-1] and not self._bad_by_lap[-2]

    def snapshot(self, meta: Optional[dict] = None) -> dict:
        """Mapa para guardar: multiplicadores y las condiciones en las que se aprendieron."""
        laps = sorted(self.tyre_by_lap)[-3:]
        cond = dict(self.start_conditions or {})
        if laps:
            cond["tyre_ref_c"] = round(sum(self.tyre_by_lap[k] for k in laps) / len(laps), 1)
        return {"version": 1, "base_limit": self.base_limit, "cap_limit": self.cap_limit, "max_scale": self.max_scale,
                "scales": {str(k): round(v, 4) for k, v in self.scales.items()}, "conditions": cond,
                "tyre_by_lap": {str(k): round(v, 1) for k, v in sorted(self.tyre_by_lap.items())},
                "laps_closed": len(self._bad_by_lap), "clean_tail": self.clean_tail(), "meta": meta or {}}

    def observe(self, lap: int, lap_distance: float, signed_cte: float, local_vx: float, local_vz: float, off_surface: bool, tyre_c: Optional[float] = None) -> Optional[dict]:
        """Un tick. Devuelve el resumen del ajuste cuando este tick abre una vuelta nueva y la anterior se pudo evaluar; si no, None."""
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
        for i, z in enumerate(self.zones):
            if z.s0 <= lap_distance <= self._zone_end(i):
                a = self._acc[z.id]
                a.n += 1
                a.cte_max = max(a.cte_max, abs(signed_cte))
                a.drift_max = max(a.drift_max, drift_deg(local_vx, local_vz))
                a.off += 1 if off_surface else 0
                break
        return update

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
        bad = {z.id for z in self.zones if self._acc[z.id].n and self._is_bad(self._acc[z.id])}
        self._bad_by_lap.append(sorted(bad))
        decisions: Dict[int, str] = {}
        for i, z in enumerate(self.zones):
            a = self._acc[z.id]
            if not a.n:
                decisions[z.id] = "sin datos"
                continue
            if not cfg.learn:
                decisions[z.id] = "fijo"
                continue
            neigh_bad = (i > 0 and self.zones[i - 1].id in bad) or (i + 1 < len(self.zones) and self.zones[i + 1].id in bad)
            if z.id in bad:
                self.scales[z.id] = max(cfg.min_scale, self.scales[z.id] * (1.0 - cfg.down))
                self.frozen[z.id] = cfg.freeze_laps
                decisions[z.id] = "baja"
            elif self.frozen[z.id] > 0:
                self.frozen[z.id] -= 1
                decisions[z.id] = "congelada"
            elif a.cte_max <= cfg.cte_clean_m and a.drift_max <= cfg.drift_clean_deg and a.off == 0 and not neigh_bad:
                self.scales[z.id] = min(self.max_scale, self.scales[z.id] * (1.0 + up))
                decisions[z.id] = "sube"
            else:
                decisions[z.id] = "igual"
        return {
            "lap": closed,
            "scales": {str(k): round(v, 4) for k, v in self.scales.items()},
            "decisions": {str(k): v for k, v in decisions.items()},
            "bad": sorted(bad), "tyre_c": None if tyre is None else round(tyre, 1), "cond_factor": None if self.prior is None else round(g_lap, 2),
            "metrics": {str(z.id): {"cte_max": round(self._acc[z.id].cte_max, 2), "drift_max": round(self._acc[z.id].drift_max, 1), "off": self._acc[z.id].off} for z in self.zones},
        }

    def _is_bad(self, a: _Acc) -> bool:
        return a.cte_max > self.cfg.cte_bad_m or a.drift_max > self.cfg.drift_bad_deg or a.off > 0

    def scales_per_m(self, n: Optional[int] = None) -> List[float]:
        """Multiplicador por metro de vuelta (1,0 fuera de las curvas)."""
        n = int(n or math.ceil(self.track_length))
        out = [1.0] * n
        for i, z in enumerate(self.zones):
            lo, hi = max(0, int(math.floor(z.s0))), min(n - 1, int(math.ceil(self._zone_end(i))))
            for d in range(lo, hi + 1):
                out[d] = self.scales[z.id]
        return out

    def limits(self) -> Dict[int, float]:
        """Límite lateral resultante de cada curva en m/s²."""
        return {k: round(self.base_limit * v, 2) for k, v in self.scales.items()}


def save_map(path: Path, data: dict) -> None:
    """Escribe el mapa de una vez (archivo temporal y reemplazo), para que un Ctrl+C no lo deje a medias."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def load_map(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("scales"), dict):
        raise ValueError(f"{path} no es un mapa de --lat-adapt (falta «scales»)")
    return data
