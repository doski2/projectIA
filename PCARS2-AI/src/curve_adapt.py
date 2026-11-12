"""Ajuste unificado de las curvas (opt-in, `--curve-adapt`): límite lateral, gas de salida y frenada por curva, vuelta a vuelta.

Diseño: `circuito_virtual/docs/DISENO_AJUSTE_UNIFICADO.md`. Sustituye a `lat_adapt.py`, `exit_adapt.py` y `brake_adapt.py`.

Por curva (C1-C14 de `curvas.json`) hay tres **magnitudes** en valores absolutos (m/s²), cada una con su canal:

- `lat`: límite lateral del perfil de velocidad en la curva;
- `exit`: radio del círculo que topa el gas en la salida;
- `brake`: deceleración de la frenada que prepara la curva.

Al teacher se le sigue pasando un multiplicador por metro (valor / base), así que el teacher no cambia.

**Cada tick va a un solo canal**, según la fase del teacher y la posición:
- en frenada (`entry`), al canal `brake` de la frenada que cubre esa distancia (de la salida de la curva anterior a la salida de ésta; la recta de meta es de C1);
- dentro de la zona de una curva (de su inicio a su salida más `exit_margin_m`) y sin frenar: al canal `exit` si va en fase de salida y ha pasado el vértice, y al canal `lat` si no.

Los síntomas comunes (|CTE|, deriva, ruedas fuera) se acumulan por canal, así que una deriva en la salida baja el gas y no el lateral.

**Reglas por curva y magnitud, al cerrar cada vuelta:**
1. Baja si salió mala en 2 de sus 3 últimas vueltas evaluadas, o en la última si es grave (rueda en la hierba o deriva > `drift_severe_deg`). Paso `down`, y 2 vueltas congelada.
2. Al bajar, guarda `ultimo_malo` = el valor que tenía al salir mala.
3. Sube si salió limpia con margen en las 2 últimas evaluadas: `min(up, mitad de la distancia a ultimo_malo)`. Si esa distancia es menor que `limit_gap` → «limite». Si choca con la cota máxima → «tope».
4. En una curva sube como mucho una magnitud por vuelta, por turno (`lat` → `exit` → `brake`); las otras candidatas quedan en «turno».
5. `ultimo_malo` se olvida tras `reprobe_laps` vueltas seguidas limpias en el límite, o al cargar un mapa con condiciones o reglaje distintos.

El patinazo de la salida es **calibrado** (razón traseras / delanteras ÷ razón de rodar libre − 1, en %) y no cuenta con una rueda en el piano.
"""

from __future__ import annotations

import json
import math
import os
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Mapping, Optional, Sequence, Tuple

CHANNELS: Tuple[str, ...] = ("lat", "exit", "brake")

# terrenos del juego (`pcars2_surface.py`)
KERB_TERRAIN = frozenset({10, 25, 47, 48, 49})  # pianos, piano de salida, franja ilegal, pintura (48 sin nombre en el enum)
OFF_TERRAIN = frozenset({6, 7, 8, 9, 15, 16, 17, 18, 27, 28, 46})  # hierba, grava, arena, tierra, escapatoria: fuera de verdad
GRASS_TERRAIN = frozenset({6, 7, 27, 28})

DEFAULT_FREE_RATIO = 0.942  # razón traseras / delanteras rodando libre (V122-V123)


@dataclass
class CurveAdaptConfig:
    # criterio común (V89; provisional hasta repetir los logs)
    cte_bad_m: float = 2.3
    drift_bad_deg: float = 5.5
    cte_clean_m: float = 1.8
    drift_clean_deg: float = 4.5
    drift_severe_deg: float = 7.0
    # reglas
    up: float = 0.04
    down: float = 0.06
    freeze_laps: int = 2
    bad_needed: int = 2  # bajar con 2 malas …
    bad_window: int = 3  # … de las 3 últimas vueltas evaluadas
    clean_needed: int = 2  # subir con las 2 últimas evaluadas limpias
    limit_gap: float = 0.01  # a menos de este 1 % del último nivel malo, «limite»
    reprobe_laps: int = 6
    # cotas absolutas (m/s²)
    minima: Dict[str, float] = field(default_factory=lambda: {"lat": 8.0, "exit": 12.6, "brake": 6.6})
    maxima: Dict[str, float] = field(default_factory=lambda: {"lat": 14.6, "exit": 23.4, "brake": 13.2})
    # vueltas y zonas
    first_lap: int = 2
    exit_margin_m: float = 15.0
    min_coverage: float = 0.9
    learn: bool = True
    # canal lat
    lat_min_ticks: int = 5
    # canal exit
    spin_clean_pct: float = 5.0
    spin_bad_pct: float = 6.5
    gas_min: float = 0.3
    min_front_rps: float = 5.0
    exit_min_ticks: int = 20
    min_bound_frac: float = 0.2
    # canal brake
    over_bad_ms: float = 1.0
    early_ms: float = -0.3
    pedal_sat: float = 0.9
    limiter_clean: float = 0.8
    brake_min_ticks: int = 15
    last_ticks: int = 5
    # razón de rodar libre medida en línea
    free_window: int = 300
    free_min_samples: int = 50
    free_gas_max: float = 0.2
    free_steer_max: float = 0.02
    free_min_speed_ms: float = 60.0 / 3.6
    free_gear_ticks: int = 10
    # condiciones (igual que el ajuste de antes)
    tyre_dead_c: float = 5.0
    tyre_span_c: float = 15.0
    track_dead_c: float = 4.0
    track_span_c: float = 11.0
    climb_min_factor: float = 0.5
    forget_mismatch: float = 0.3  # con un desajuste mayor, la memoria de los niveles malos no vale


@dataclass
class Zone:
    id: int
    s0: float
    s1: float
    apex: float


@dataclass
class Tick:
    """Lo que el ajuste necesita de un tick. `phase` es la del teacher: "entry", "exit" o "drive"."""

    lap: int
    s: float
    signed_cte: float
    local_vx: float
    local_vz: float
    terrain: Sequence[int] = (0, 0, 0, 0)
    tyre_c: Optional[float] = None
    phase: str = "drive"
    exit_bound: bool = False
    gas: float = 0.0  # gas que sale al juego
    gas_req: float = 0.0  # gas que pide el teacher
    brake: float = 0.0  # pedal de freno que sale al juego
    limiter_scale: float = 1.0
    over_ms: float = 0.0  # velocidad − v*(s) del perfil
    rps: Sequence[float] = (0.0, 0.0, 0.0, 0.0)
    gear: int = 0
    clutch: int = 0
    steering: float = 0.0
    speed_ms: float = 0.0


def drift_deg(local_vx: float, local_vz: float, min_speed_ms: float = 5.0) -> float:
    """Ángulo de deriva en grados (como en `resumen_sesion.py`): 0 por debajo de `min_speed_ms`. El eje 2 de `local_velocity` es negativo al avanzar."""
    forward = -float(local_vz)
    if forward <= min_speed_ms:
        return 0.0
    return abs(math.degrees(math.atan2(float(local_vx), forward)))


class _Acc:
    """Métricas de una curva y un canal en la vuelta en curso."""

    __slots__ = ("n", "cte_max", "drift_max", "off", "grass", "bound", "spin_max", "spin_n", "pedal_max", "scale_min", "over", "over_max")

    def __init__(self) -> None:
        self.n = 0
        self.cte_max = 0.0
        self.drift_max = 0.0
        self.off = 0
        self.grass = 0
        self.bound = 0
        self.spin_max = float("-inf")
        self.spin_n = 0
        self.pedal_max = 0.0
        self.scale_min = 1.0
        self.over: List[float] = []
        self.over_max = float("-inf")


class _State:
    """Estado de una magnitud de una curva."""

    __slots__ = ("value", "last_bad", "frozen", "history", "limit_laps", "decision")

    def __init__(self, value: float) -> None:
        self.value = float(value)
        self.last_bad: Optional[float] = None
        self.frozen = 0
        self.history: Deque[str] = deque(maxlen=3)  # "mala", "limpia" o "media" de las últimas vueltas evaluadas
        self.limit_laps = 0
        self.decision = "igual"


class FreeRatio:
    """Razón traseras / delanteras rodando libre, medida en línea (embrague suelto, poco gas, recto, sin cambio de marcha reciente)."""

    def __init__(self, cfg: CurveAdaptConfig, prior: float = DEFAULT_FREE_RATIO) -> None:
        self.cfg = cfg
        self.prior = float(prior)
        self._samples: Deque[float] = deque(maxlen=cfg.free_window)
        self._gears: Deque[int] = deque(maxlen=cfg.free_gear_ticks)

    def observe(self, t: Tick) -> None:
        c = self.cfg
        self._gears.append(int(t.gear))
        if len(self._gears) < c.free_gear_ticks or len(set(self._gears)) != 1 or t.gear <= 0:
            return
        if t.clutch != 0 or t.gas >= c.free_gas_max or t.gas_req >= c.free_gas_max or t.brake > 0.01:
            return
        if abs(t.steering) >= c.free_steer_max or t.speed_ms <= c.free_min_speed_ms:
            return
        front = (abs(t.rps[0]) + abs(t.rps[1])) / 2.0
        if front <= c.min_front_rps:
            return
        self._samples.append((abs(t.rps[2]) + abs(t.rps[3])) / 2.0 / front)

    @property
    def n(self) -> int:
        return len(self._samples)

    @property
    def value(self) -> float:
        if len(self._samples) < self.cfg.free_min_samples:
            return self.prior
        s = sorted(self._samples)
        m = len(s) // 2
        return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2.0

    def slip_pct(self, t: Tick) -> Optional[float]:
        front = (abs(t.rps[0]) + abs(t.rps[1])) / 2.0
        if front <= self.cfg.min_front_rps:
            return None
        return ((abs(t.rps[2]) + abs(t.rps[3])) / 2.0 / front / self.value - 1.0) * 100.0


class CurveAdapter:
    def __init__(self, zones: Sequence[Zone], bases: Mapping[str, float], track_length: float, config: Optional[CurveAdaptConfig] = None,
                 channels: Optional[Sequence[str]] = None):
        self.cfg = config or CurveAdaptConfig()
        self.channels: Tuple[str, ...] = tuple(c for c in CHANNELS if c in (channels or CHANNELS))
        if not self.channels:
            raise ValueError("--curve-adapt necesita al menos un canal (lat, exit, brake)")
        unknown = set(channels or ()) - set(CHANNELS)
        if unknown:
            raise ValueError(f"canales desconocidos: {sorted(unknown)}")
        for ch in self.channels:
            if float(bases.get(ch, 0.0)) <= 0.0:
                raise ValueError(f"el canal {ch} necesita su valor base (> 0)")
        self.bases: Dict[str, float] = {ch: float(bases[ch]) for ch in self.channels}
        self.zones: List[Zone] = sorted(zones, key=lambda z: z.s0)
        self.track_length = float(track_length)
        self.state: Dict[int, Dict[str, _State]] = {
            z.id: {ch: _State(self._clip(ch, self.bases[ch])) for ch in self.channels} for z in self.zones}
        self._turn: Dict[int, int] = {z.id: 0 for z in self.zones}
        self.free = FreeRatio(self.cfg)
        self._lap: Optional[int] = None
        self._acc: Dict[Tuple[int, str], _Acc] = {}
        self._d_min = float("inf")
        self._d_max = float("-inf")
        self._tyre: List[float] = [0.0, 0.0]
        self.tyre_by_lap: Dict[int, float] = {}
        self._down_by_lap: List[List[str]] = []
        self.prior: Optional[dict] = None
        self._prior_v1: Dict[str, dict] = {}
        self.prior_pending = False
        self.start_conditions: Optional[dict] = None
        self.setup: Optional[dict] = None
        self.mismatch = 0.0
        self._g_track = 0.0

    # ── construcción ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
    @classmethod
    def from_curvas_json(cls, path: Path, bases: Mapping[str, float], track_length: float, config: Optional[CurveAdaptConfig] = None,
                         channels: Optional[Sequence[str]] = None) -> "CurveAdapter":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        zones = [Zone(int(c["id"]), float(c["s_ini"]), float(c["s_fin"]), float(c.get("s_apice", (float(c["s_ini"]) + float(c["s_fin"])) / 2.0)))
                 for c in data["curvas"]]
        return cls(zones, bases, track_length, config, channels)

    def _clip(self, ch: str, v: float) -> float:
        return min(self.cfg.maxima[ch], max(self.cfg.minima[ch], float(v)))

    # ── zonas ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
    def _zone_end(self, i: int) -> float:
        end = self.zones[i].s1 + self.cfg.exit_margin_m
        if i + 1 < len(self.zones):
            end = min(end, self.zones[i + 1].s0)
        return end

    def curve_zone(self, s: float) -> Optional[Zone]:
        """Curva cuya zona (inicio → salida + margen) contiene `s`, o None en recta."""
        for i, z in enumerate(self.zones):
            if z.s0 <= s <= self._zone_end(i):
                return z
        return None

    def brake_zone(self, s: float) -> int:
        """Curva cuya frenada cubre esta distancia: la siguiente salida de curva; pasada la última, C1 (recta de meta)."""
        for z in self.zones:
            if s <= z.s1:
                return z.id
        return self.zones[0].id

    def channel_of(self, t: Tick) -> Optional[Tuple[int, str]]:
        """(curva, canal) al que va este tick, o None si no va a ninguno."""
        if t.phase == "entry":
            return (self.brake_zone(t.s), "brake") if "brake" in self.channels else None
        z = self.curve_zone(t.s)
        if z is None:
            return None
        ch = "exit" if t.phase == "exit" and t.s >= z.apex else "lat"
        return (z.id, ch) if ch in self.channels else None

    # ── vuelta a vuelta ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
    def _reset_lap(self, lap: Optional[int]) -> None:
        self._lap = lap
        self._acc = {(z.id, ch): _Acc() for z in self.zones for ch in self.channels}
        self._d_min, self._d_max = float("inf"), float("-inf")
        self._tyre = [0.0, 0.0]

    def observe(self, t: Tick) -> Optional[dict]:
        """Un tick. Devuelve el resumen del ajuste cuando este tick abre una vuelta nueva y la anterior se pudo evaluar; si no, None."""
        self.free.observe(t)
        update = None
        if t.lap != self._lap:
            if self._lap is not None and self._lap >= self.cfg.first_lap:
                update = self._close_lap()
            self._reset_lap(t.lap)
        if t.lap < self.cfg.first_lap:
            return update
        if t.tyre_c is not None:
            self._tyre[0] += float(t.tyre_c)
            self._tyre[1] += 1.0
        self._d_min = min(self._d_min, t.s)
        self._d_max = max(self._d_max, t.s)
        where = self.channel_of(t)
        if where is None:
            return update
        a = self._acc[where]
        ch = where[1]
        terrain = [int(x) for x in list(t.terrain)[:4]]
        on_kerb = any(x in KERB_TERRAIN for x in terrain)
        if ch == "brake":
            if t.brake <= 0.02:
                return update  # en la frenada solo cuentan los ticks con el pedal pisado (como antes)
            a.pedal_max = max(a.pedal_max, t.brake)
            a.scale_min = min(a.scale_min, t.limiter_scale)
            a.over.append(t.over_ms)
            del a.over[:-self.cfg.last_ticks]
            a.over_max = max(a.over_max, t.over_ms)
        a.n += 1
        a.cte_max = max(a.cte_max, abs(t.signed_cte))
        a.drift_max = max(a.drift_max, drift_deg(t.local_vx, t.local_vz))
        a.off += 1 if any(x in OFF_TERRAIN for x in terrain) else 0
        a.grass += 1 if any(x in GRASS_TERRAIN for x in terrain) else 0
        if ch == "exit":
            a.bound += 1 if t.exit_bound else 0
            if t.gas > self.cfg.gas_min and t.clutch == 0 and not on_kerb:
                slip = self.free.slip_pct(t)
                if slip is not None:
                    a.spin_max = max(a.spin_max, slip)
                    a.spin_n += 1
        return update

    # ── criterio ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
    def _min_ticks(self, ch: str) -> int:
        return {"lat": self.cfg.lat_min_ticks, "exit": self.cfg.exit_min_ticks, "brake": self.cfg.brake_min_ticks}[ch]

    @staticmethod
    def _release_over(a: _Acc) -> float:
        return sum(a.over) / len(a.over) if a.over else 0.0

    def judge(self, ch: str, a: _Acc) -> Tuple[str, str]:
        """(veredicto, motivo): veredicto «sin datos», «grave», «mala», «limpia» o «media»."""
        c = self.cfg
        if a.n < self._min_ticks(ch):
            return "sin datos", f"{a.n} ticks"
        if a.grass > 0:
            return "grave", "rueda en la hierba"
        if a.drift_max > c.drift_severe_deg:
            return "grave", f"deriva {a.drift_max:.1f}° > {c.drift_severe_deg:g}"
        bad: List[str] = []
        if a.cte_max > c.cte_bad_m:
            bad.append(f"|CTE| {a.cte_max:.2f} > {c.cte_bad_m:g}")
        if a.drift_max > c.drift_bad_deg:
            bad.append(f"deriva {a.drift_max:.1f}° > {c.drift_bad_deg:g}")
        if a.off > 0:
            bad.append(f"{a.off} ticks fuera")
        if ch == "exit" and a.spin_n and a.spin_max > c.spin_bad_pct:
            bad.append(f"patinazo {a.spin_max:.1f} % > {c.spin_bad_pct:g}")
        if ch == "brake" and self._release_over(a) > c.over_bad_ms:
            bad.append(f"suelta a {self._release_over(a):+.2f} m/s > {c.over_bad_ms:g}")
        if bad:
            return "mala", "; ".join(bad)
        clean = a.cte_max <= c.cte_clean_m and a.drift_max <= c.drift_clean_deg and a.off == 0
        why = "" if clean else f"|CTE| {a.cte_max:.2f}, deriva {a.drift_max:.1f}°"
        if clean and ch == "exit":
            if a.spin_n and a.spin_max > c.spin_clean_pct:
                clean, why = False, f"patinazo {a.spin_max:.1f} %"
            elif a.bound < c.min_bound_frac * a.n:
                clean, why = False, f"el tope recorta solo {a.bound / a.n:.0%}"
        if clean and ch == "brake":
            if self._release_over(a) >= c.early_ms:
                clean, why = False, f"suelta a {self._release_over(a):+.2f} m/s"
            elif a.pedal_max >= c.pedal_sat or a.scale_min < c.limiter_clean:
                clean, why = False, f"frenada al límite (pedal {a.pedal_max:.2f}, limitador {a.scale_min:.2f})"
        return ("limpia", "") if clean else ("media", why)

    # ── cierre de vuelta ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
    def _close_lap(self) -> Optional[dict]:
        cfg = self.cfg
        if self._d_max - self._d_min < cfg.min_coverage * self.track_length:
            return None  # vuelta incompleta (reinicio, corte): no se fía
        closed = self._lap
        assert closed is not None
        tyre = self._tyre[0] / self._tyre[1] if self._tyre[1] else None
        if tyre is not None:
            self.tyre_by_lap[closed] = tyre
        g_lap = self._lap_mismatch(closed, tyre)
        up = cfg.up * (1.0 - (1.0 - cfg.climb_min_factor) * g_lap)
        out: Dict[str, Dict[str, Any]] = {}
        downs: List[str] = []
        for z in self.zones:
            cands: List[str] = []
            row: Dict[str, Any] = {}
            for ch in self.channels:
                st = self.state[z.id][ch]
                a = self._acc[(z.id, ch)]
                verdict, why = self.judge(ch, a)
                if verdict != "sin datos":
                    st.history.append("mala" if verdict in ("mala", "grave") else verdict)
                decision = self._decide(st, verdict, ch)
                if decision == "candidata":
                    cands.append(ch)
                if decision == "baja":
                    downs.append(f"C{z.id}.{ch}")
                st.decision = decision
                row[ch] = {"valor": round(st.value, 3), "decision": decision, "veredicto": verdict, "motivo": why, "metricas": self._metrics(ch, a)}
            if cands:  # una subida por curva y vuelta, por turno
                order = [self.channels[(self._turn[z.id] + k) % len(self.channels)] for k in range(len(self.channels))]
                pick = next(ch for ch in order if ch in cands)
                self._turn[z.id] = (self.channels.index(pick) + 1) % len(self.channels)
                for ch in cands:
                    st = self.state[z.id][ch]
                    st.decision = self._climb(st, ch, up) if ch == pick else "turno"
                    row[ch]["decision"] = st.decision
                    row[ch]["valor"] = round(st.value, 3)
            out[str(z.id)] = row
        self._down_by_lap.append(downs)
        return {"lap": closed, "curvas": out, "bajadas": downs, "razon_libre": round(self.free.value, 4), "razon_libre_n": self.free.n,
                "tyre_c": None if tyre is None else round(tyre, 1), "cond_factor": None if self.prior is None and not self._prior_v1 else round(g_lap, 2)}

    def _decide(self, st: _State, verdict: str, ch: str) -> str:
        """Bajada, congelada o candidata a subir (la subida la reparte el turno)."""
        cfg = self.cfg
        if verdict == "sin datos":
            return "sin datos"
        if not cfg.learn:
            return "fijo"
        hist = list(st.history)
        bad_count = sum(1 for h in hist[-cfg.bad_window:] if h == "mala")
        if verdict == "grave" or (verdict == "mala" and bad_count >= cfg.bad_needed):
            st.last_bad = st.value  # el nivel al que salió mala
            st.value = max(cfg.minima[ch], st.value * (1.0 - cfg.down))
            st.frozen = cfg.freeze_laps
            st.history.clear()
            st.limit_laps = 0
            return "baja"
        if st.frozen > 0:
            st.frozen -= 1
            return "congelada"
        if len(hist) >= cfg.clean_needed and all(h == "limpia" for h in hist[-cfg.clean_needed:]):
            return "candidata"
        st.limit_laps = 0  # las vueltas en el límite cuentan solo si son seguidas y limpias
        return "aviso" if verdict == "mala" else "igual"  # «aviso»: mala, pero una sola de las 3 últimas; no baja todavía

    def _climb(self, st: _State, ch: str, up: float) -> str:
        cfg = self.cfg
        top = cfg.maxima[ch]
        if st.value >= top - 1e-9:
            return "tope"
        step = st.value * up
        if st.last_bad is not None:
            gap = st.last_bad - st.value
            if gap < cfg.limit_gap * st.value:
                st.limit_laps += 1
                if st.limit_laps >= cfg.reprobe_laps:
                    st.last_bad, st.limit_laps = None, 0  # mucho tiempo limpia en el límite: se vuelve a probar
                return "limite"
            step = min(step, gap / 2.0)
        st.value = min(top, st.value + step)
        return "sube"

    def _metrics(self, ch: str, a: _Acc) -> Dict[str, Any]:
        m: Dict[str, Any] = {"n": a.n, "cte_max": round(a.cte_max, 2), "drift_max": round(a.drift_max, 1), "off": a.off}
        if ch == "exit":
            m.update({"bound_frac": round(a.bound / a.n, 2) if a.n else 0.0, "spin_max_pct": round(a.spin_max, 2) if a.spin_n else None})
        if ch == "brake":
            m.update({"release_over_ms": round(self._release_over(a), 2) if a.over else None, "over_max_ms": round(a.over_max, 2) if a.over else None,
                      "pedal_max": round(a.pedal_max, 2), "limiter_min": round(a.scale_min, 2)})
        return m

    # ── lo que se pasa al teacher ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
    def values(self, ch: str) -> Dict[int, float]:
        return {z.id: round(self.state[z.id][ch].value, 3) for z in self.zones}

    def scales_per_m(self, ch: str, n: Optional[int] = None) -> List[float]:
        """Multiplicador por metro de vuelta para el teacher (valor / base): `lat` y `exit` en la zona de cada curva (1,0 fuera); `brake` en toda la vuelta, el de la frenada que viene."""
        n = int(n or math.ceil(self.track_length))
        base = self.bases[ch]
        if ch == "brake":
            return [self.state[self.brake_zone(float(d))][ch].value / base for d in range(n)]
        out = [1.0] * n
        for i, z in enumerate(self.zones):
            lo, hi = max(0, int(math.floor(z.s0))), min(n - 1, int(math.ceil(self._zone_end(i))))
            for d in range(lo, hi + 1):
                out[d] = self.state[z.id][ch].value / base
        return out

    def clean_tail(self) -> bool:
        """Al menos 3 vueltas cerradas y ninguna bajada en las dos últimas: el mapa es digno de guardarse."""
        return len(self._down_by_lap) >= 3 and not self._down_by_lap[-1] and not self._down_by_lap[-2]

    # ── condiciones y mapas ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _frac(delta: float, dead: float, span: float) -> float:
        return min(1.0, max(0.0, (abs(delta) - dead) / span))

    def load_prior(self, data: dict, channel: Optional[str] = None) -> None:
        """Deja un mapa a la espera de las condiciones de hoy (`start`). Formato 2: el mapa entero. Formato 1 (los de `--lat/exit/brake-adapt`): uno por canal, con `channel`."""
        if int(data.get("version", 1)) >= 2:
            if not isinstance(data.get("curvas"), dict):
                raise ValueError("el mapa de formato 2 no trae «curvas»")
            self.prior = data
        else:
            if channel not in CHANNELS:
                raise ValueError("un mapa de formato 1 necesita su canal (lat, exit o brake)")
            if not isinstance(data.get("scales"), dict) or not data.get("base_limit"):
                raise ValueError("el mapa de formato 1 no trae «scales» y «base_limit»")
            self._prior_v1[channel] = data
        self.prior_pending = True

    def _prior_values(self) -> Tuple[Dict[int, Dict[str, Tuple[float, Optional[float]]]], dict, Optional[dict], Optional[float], Optional[dict]]:
        """(valores {curva: {canal: (valor, último malo)}}, condiciones, tyre_by_lap, razón libre, reglaje) de lo cargado."""
        vals: Dict[int, Dict[str, Tuple[float, Optional[float]]]] = {}
        if self.prior is not None:
            for k, row in self.prior["curvas"].items():
                for ch, cell in row.items():
                    if ch in self.channels and isinstance(cell, dict) and cell.get("valor") is not None:
                        vals.setdefault(int(k), {})[ch] = (float(cell["valor"]), None if cell.get("ultimo_malo") is None else float(cell["ultimo_malo"]))
            return vals, dict(self.prior.get("conditions") or {}), self.prior.get("tyre_by_lap"), self.prior.get("razon_libre"), self.prior.get("reglaje")
        cond: dict = {}
        tyre_by_lap = None
        for ch, data in self._prior_v1.items():
            if ch not in self.channels:
                continue
            base = float(data["base_limit"])
            for k, s in data["scales"].items():
                vals.setdefault(int(k), {})[ch] = (base * float(s), None)
            cond = cond or dict(data.get("conditions") or {})
            tyre_by_lap = tyre_by_lap or data.get("tyre_by_lap")
        return vals, cond, tyre_by_lap, None, None

    def start(self, now: dict, setup: Optional[dict] = None) -> Optional[dict]:
        """Primer instante con las condiciones conocidas. Guarda condiciones y reglaje y, si hay un mapa pendiente, lo aplica. Devuelve el resumen o None."""
        self.start_conditions = dict(now)
        self.setup = dict(setup) if setup else None
        if not self.prior_pending:
            return None
        self.prior_pending = False
        vals, ref, _, free_ratio, saved_setup = self._prior_values()
        if bool(ref.get("rain")) != bool(now.get("rain")):
            self.prior, self._prior_v1 = None, {}
            return {"applied": False, "reason": "lluvia distinta a la del mapa guardado"}
        if ref.get("compound") and now.get("compound") and ref["compound"] != now["compound"]:
            self.prior, self._prior_v1 = None, {}
            return {"applied": False, "reason": f"compuesto distinto ({now['compound']} frente a {ref['compound']})"}
        cfg = self.cfg
        g_track = self._frac(now["track_c"] - ref["track_c"], cfg.track_dead_c, cfg.track_span_c) if ref.get("track_c") is not None and now.get("track_c") is not None else 0.0
        g_tyre = (self._frac(now["tyre_start_c"] - ref["tyre_start_c"], cfg.tyre_dead_c, cfg.tyre_span_c)
                  if ref.get("tyre_start_c") is not None and now.get("tyre_start_c") is not None else 0.0)
        self._g_track = g_track
        self.mismatch = max(g_track, g_tyre)
        setup_differs = bool(saved_setup) and bool(self.setup) and saved_setup != self.setup
        keep_memory = self.mismatch <= cfg.forget_mismatch and not setup_differs
        for z in self.zones:
            for ch, (v, last_bad) in vals.get(z.id, {}).items():
                base = self.bases[ch]
                v = base + (v - base) * (1.0 - self.mismatch) if v > base else v  # solo puede frenar, nunca acelerar
                st = self.state[z.id][ch]
                st.value = self._clip(ch, v)
                st.last_bad = last_bad if keep_memory else None
        if free_ratio:
            self.free.prior = float(free_ratio)
        return {"applied": True, "mismatch": round(self.mismatch, 2), "mismatch_track": round(g_track, 2), "mismatch_tyre": round(g_tyre, 2),
                "memoria": keep_memory, "reglaje_distinto": setup_differs, "valores": {ch: self.values(ch) for ch in self.channels}}

    def _lap_mismatch(self, lap: int, tyre: Optional[float]) -> float:
        if self.prior is None and not self._prior_v1:
            return 0.0
        _, cond, tyre_by_lap, _, _ = self._prior_values()
        g = self._g_track
        ref = (tyre_by_lap or {}).get(str(lap))
        if ref is None:
            ref = cond.get("tyre_ref_c")
        if tyre is not None and ref is not None:
            g = max(g, self._frac(tyre - float(ref), self.cfg.tyre_dead_c, self.cfg.tyre_span_c))
        return g

    def snapshot(self, meta: Optional[dict] = None) -> dict:
        """Mapa de formato 2 para guardar."""
        laps = sorted(self.tyre_by_lap)[-3:]
        cond = dict(self.start_conditions or {})
        if laps:
            cond["tyre_ref_c"] = round(sum(self.tyre_by_lap[k] for k in laps) / len(laps), 1)
        return {
            "version": 2,
            "curvas": {str(z.id): {ch: {"valor": round(self.state[z.id][ch].value, 3),
                                        "ultimo_malo": None if self.state[z.id][ch].last_bad is None else round(self.state[z.id][ch].last_bad or 0.0, 3),
                                        "estado": self.state[z.id][ch].decision} for ch in self.channels} for z in self.zones},
            "bases": dict(self.bases),
            "maximos": {ch: self.cfg.maxima[ch] for ch in self.channels},
            "razon_libre": round(self.free.value, 4),
            "reglaje": self.setup,
            "conditions": cond,
            "tyre_by_lap": {str(k): round(v, 1) for k, v in sorted(self.tyre_by_lap.items())},
            "laps_closed": len(self._down_by_lap),
            "clean_tail": self.clean_tail(),
            "meta": meta or {},
        }


def save_map(path: Path, data: dict) -> None:
    """Escribe el mapa de una vez (archivo temporal y reemplazo), para que un Ctrl+C no lo deje a medias."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def load_map(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not (isinstance(data.get("curvas"), dict) or isinstance(data.get("scales"), dict)):
        raise ValueError(f"{path} no es un mapa de ajuste por curva (faltan «curvas» o «scales»)")
    return data


__all__ = ["CHANNELS", "CurveAdaptConfig", "CurveAdapter", "FreeRatio", "Tick", "Zone", "drift_deg", "load_map", "save_map"]
