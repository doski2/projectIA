"""A2 (`PLAN_A_LIMITES_COCHE.md`): perfil de velocidad máxima de una pista a partir de los parámetros medidos en A1.

Modelo clásico de adelante y atrás sobre la línea de referencia, un punto por metro:

1. **Límite lateral:** `v² · κ = a_lat(v)` con `a_lat = μ + k · v²` (D21: μ ≥ 14,6 m/s², k sin medir) → `v_lat = sqrt(μ / (κ − k))`.
2. **Hacia atrás:** `v[i] ≤ sqrt(v[i+1]² + 2 · (a_freno(v) + g · pendiente) · ds)`.
3. **Hacia delante:** `v[i+1]² ≤ v[i]² + 2 · (a_acel(v) − g · pendiente) · ds`.
4. **Tiempo de vuelta:** `Σ ds / v` (v media del tramo).

`a_acel` y `a_freno` salen de las tablas de A1.1 y A1.2, que ya están corregidas de pendiente (a_llano = a_medida + g · pendiente), así que aquí
se vuelve a restar/sumar la pendiente de cada punto de la pista. Las tablas solo cubren hasta `v_known_kmh` (120 km/h en 1ª y 2ª, H50): el
perfil nunca pasa de ahí, y `Profile.share_at_cap` dice qué parte de la vuelta lo toca.
"""

from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "PCARS2-AI" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

G = 9.81
MIN_KAPPA = 1e-4  # tope de velocidad en recta (100 m/s) para no dividir por cero
KAPPA_HALF_M = 7  # mismo suavizado que usa el teacher (`_lateral_speed_limits`)
GRADE_HALF_M = 15
MIN_SPEED_MS = 1.0
SUGO_REF = _SRC / "refs" / "sugo_ai.json"


def _centre(label: str) -> float:
    lo, hi = (float(x) for x in re.findall(r"[\d.]+", label)[:2])
    return (lo + hi) / 2.0


def table_points(rows: Sequence[dict], min_kmh: float = 0.0) -> List[Tuple[float, float]]:
    """Filas de `analisis_a1._table` (`v_kmh` = "30-40", `a_med`) → [(km/h del centro del tramo, m/s²)] desde `min_kmh`."""
    pts = sorted((_centre(r["v_kmh"]), float(r["a_med"])) for r in rows)
    return [p for p in pts if p[0] - 5.0 >= min_kmh]


@dataclass
class CarParams:
    accel: List[Tuple[float, float]]  # (km/h, m/s² en llano a gas a fondo)
    brake: List[Tuple[float, float]]  # (km/h, m/s² en llano a freno a fondo)
    mu: float = 14.6  # D21: cota inferior
    k: float = 0.0
    v_known_kmh: float = 120.0
    brake_delay_s: float = 0.0  # del pedal a la deceleración plena (ABS, presión de frenos): H51 deja ≈ 0,04 s

    def a_acel(self, v_ms: float) -> float:
        return float(np.interp(v_ms * 3.6, [p[0] for p in self.accel], [p[1] for p in self.accel]))

    def a_freno(self, v_ms: float) -> float:
        return float(np.interp(v_ms * 3.6, [p[0] for p in self.brake], [p[1] for p in self.brake]))

    def to_dict(self) -> dict:
        return {"accel": self.accel, "brake": self.brake, "mu": self.mu, "k": self.k, "v_known_kmh": self.v_known_kmh,
                "brake_delay_s": self.brake_delay_s}

    @staticmethod
    def from_dict(d: dict) -> "CarParams":
        return CarParams([tuple(p) for p in d["accel"]], [tuple(p) for p in d["brake"]], d.get("mu", 14.6), d.get("k", 0.0),
                         d.get("v_known_kmh", 120.0), d.get("brake_delay_s", 0.0))


@dataclass
class Track:
    length_m: float
    kappa: np.ndarray  # |κ| suavizada, 1/m, un valor por metro
    grade: np.ndarray  # pendiente (+ = cuesta arriba), un valor por metro
    grade_ref: Optional[np.ndarray] = None  # la de la línea de referencia, si se sustituyó por la medida

    @property
    def n(self) -> int:
        return len(self.kappa)

    def grade_at(self, d: float) -> float:
        return float(self.grade[int(d) % self.n])

    @staticmethod
    def from_reference(path: Path = SUGO_REF) -> "Track":
        from reference_recorder import ReferenceLine  # noqa: PLC0415

        ref = ReferenceLine.load(str(path))
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        n = int(round(ref.track_length))
        kap = np.array([abs(ref.curvature(float(d))) for d in range(n)])
        kernel = np.ones(2 * KAPPA_HALF_M + 1) / (2 * KAPPA_HALF_M + 1)
        kap = np.convolve(np.concatenate([kap[-KAPPA_HALF_M:], kap, kap[:KAPPA_HALF_M]]), kernel, mode="valid")
        ds = np.array([p["d"] for p in data["points"]], dtype=float)
        ys = np.array([p["pos"][1] for p in data["points"]], dtype=float)
        grid = np.arange(n, dtype=float)
        y = np.interp(grid, ds, ys)
        h = GRADE_HALF_M
        grade = (np.roll(y, -h) - np.roll(y, h)) / (2.0 * h)
        return Track(float(ref.track_length), kap, grade)


def grade_from_ticks(ticks: Sequence[dict], n: int, half_m: int = GRADE_HALF_M) -> Optional[np.ndarray]:
    """Pendiente por metro de vuelta de la altura que registra el coche (`vehicle.position[1]`): mediana de las vueltas completas.

    Es la pendiente que ve el coche de verdad (H51); la de `sugo_ai.json` sale de otra vuelta y puede diferir un 1-2 %, que en una aceleración
    de 4 m/s² son ±0,1-0,2 m/s². None si ninguna vuelta cubre el 95 % de la pista.
    """
    by_lap: Dict[int, List[Tuple[float, float]]] = {}
    for t in ticks:
        pos = (t.get("vehicle") or {}).get("position")
        if pos and len(pos) >= 2 and t.get("lap") is not None:
            by_lap.setdefault(int(t["lap"]), []).append((float(t["lap_distance"]), float(pos[1])))
    per_lap = []
    for pts in by_lap.values():
        arr = np.array(pts)
        idx = arr[:, 0].astype(int) % n
        ysum = np.zeros(n)
        cnt = np.zeros(n)
        np.add.at(ysum, idx, arr[:, 1])
        np.add.at(cnt, idx, 1.0)
        if (cnt > 0).mean() < 0.95:
            continue
        have = cnt > 0
        y = np.interp(np.arange(n), np.flatnonzero(have), ysum[have] / cnt[have], period=n)
        per_lap.append((np.roll(y, -half_m) - np.roll(y, half_m)) / (2.0 * half_m))
    return np.median(np.stack(per_lap), axis=0) if per_lap else None


@dataclass
class Profile:
    v_ms: np.ndarray
    time_s: float
    share_at_cap: float  # parte de la vuelta en el tope de velocidad (cobertura de las tablas o `cap_kmh`)
    share_lateral: float  # parte donde manda el límite lateral
    share_braking: float
    share_accel: float


def lateral_limit_ms(track: Track, car: CarParams, vmax_ms: float) -> np.ndarray:
    kappa = np.maximum(track.kappa, MIN_KAPPA)
    with np.errstate(divide="ignore", invalid="ignore"):
        v = np.where(kappa > car.k, np.sqrt(car.mu / np.maximum(kappa - car.k, 1e-12)), np.inf)
    return np.minimum(v, vmax_ms)


def solve(track: Track, car: CarParams, cap_kmh: Optional[float] = None) -> Profile:
    """Perfil de velocidad máxima de una vuelta cerrada (se recorre dos veces para que el principio y el final encajen)."""
    n = track.n
    ds = track.length_m / n
    vmax = min(cap_kmh if cap_kmh else math.inf, car.v_known_kmh) / 3.6
    lim = lateral_limit_ms(track, car, vmax)
    v_b = lim.copy()
    for step in range(2 * n):
        i = (n - 1 - step) % n
        j = (i + 1) % n
        decel = max(car.a_freno(v_b[j]) + G * track.grade[i], 0.5)
        v_b[i] = min(v_b[i], math.sqrt(v_b[j] ** 2 + 2.0 * decel * ds))
    if car.brake_delay_s > 0:  # el freno llega `brake_delay_s` más tarde: hay que frenar antes, a la velocidad de ese punto
        v_b0 = v_b.copy()
        shift = np.round(v_b0 * car.brake_delay_s / ds).astype(int)
        v_b = np.minimum(v_b0, v_b0[(np.arange(n) + shift) % n])
    v = v_b.copy()
    for step in range(2 * n):
        i = step % n
        j = (i + 1) % n
        acc = car.a_acel(v[i]) - G * track.grade[i]
        v[j] = min(v_b[j], math.sqrt(max(v[i] ** 2 + 2.0 * acc * ds, MIN_SPEED_MS ** 2)))
    nxt = np.roll(v, -1)
    time_s = float(np.sum(ds / ((v + nxt) / 2.0)))
    d_v = nxt - v
    at_cap = v >= vmax - 1e-6
    lateral = (v >= lim - 1e-6) & ~at_cap
    braking = (d_v < -1e-6) & ~at_cap
    accel = (d_v > 1e-6) & ~at_cap
    return Profile(v, time_s, float(at_cap.mean()), float(lateral.mean()), float(braking.mean()), float(accel.mean()))


def simulate_accel(track: Track, car: CarParams, d0: float, v0_ms: float, v_end_ms: float, dt: float = 0.005,
                   max_s: float = 60.0) -> Tuple[float, float]:
    """Gas a fondo desde `d0` a `v0` hasta alcanzar `v_end`: (tiempo, distancia recorrida). Para validar las maniobras de A1.1."""
    t = 0.0
    d = d0
    v = max(v0_ms, MIN_SPEED_MS)
    while v < v_end_ms and t < max_s:
        a = car.a_acel(v) - G * track.grade_at(d)
        v = max(v + a * dt, MIN_SPEED_MS)
        d += v * dt
        t += dt
    return t, d - d0


def simulate_brake(track: Track, car: CarParams, d0: float, v_in_ms: float, v_out_ms: float, dt: float = 0.002,
                   max_s: float = 30.0) -> Tuple[float, float]:
    """Freno a fondo desde `d0` a `v_in` hasta `v_out`: (tiempo, distancia). Para validar las frenadas de A1.2."""
    t = car.brake_delay_s
    d = d0 + v_in_ms * car.brake_delay_s
    v = v_in_ms
    while v > v_out_ms and t < max_s:
        a = car.a_freno(v) + G * track.grade_at(d)
        v -= max(a, 0.5) * dt
        d += max(v, 0.0) * dt
        t += dt
    return t, d - d0


def save_params(car: CarParams, path: Path, meta: Optional[Dict] = None) -> None:
    Path(path).write_text(json.dumps({"car": car.to_dict(), "meta": meta or {}}, ensure_ascii=False, indent=2), encoding="utf-8")


def load_params(path: Path) -> CarParams:
    return CarParams.from_dict(json.loads(Path(path).read_text(encoding="utf-8"))["car"])
