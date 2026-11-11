"""Bloque de caja (V117): modelo longitudinal del coche ajustado con los logs y simulación de la vuelta con otras relaciones.

1. **Modelo** (gas a fondo y rodando sin pedales, en recta y sin cambio de marcha en curso, pendiente corregida con la altura del coche):
   `a = (c · T(rpm) · G − d0 − d2 · v²) / (1 + k · G²)`, con `T` el `engine_torque` del UDP, `G` = relación de la marcha × final y
   `k` la inercia de motor y transmisión. Mínimos cuadrados con el mismo peso para cada marcha y tipo (si no, la 3.ª lo ahoga todo).
2. **Vuelta:** límites de curva = velocidad media medida donde la lateral pasa de 7 m/s² en la sesión `--sesion`, tope `--banda`,
   frenada hacia atrás con la tabla de A1, y hacia delante con estado de marcha: sube a `--upshift-rpm`, `NEUTRAL_S` en punto muerto
   por cambio, y al frenar la marcha más baja que no pasa del punto de cambio (las bajadas las hace el juego).

Uso: `python caja_cambios.py --sesion <log de la receta vigente>` (la primera vez lee todos los logs de `--logs` y guarda la caché).
Lo que vale es la diferencia entre cajas, no el tiempo absoluto: con la caja de V116 la simulación da 1:47.426 (medido 1:47.287) y
la diferencia 6600 → 7400 rpm −0,26 s (medida −0,31).
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
from bisect import bisect_right
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[2]
LOGS = str(REPO / "PCARS2-AI" / "logs" / "learning" / "202611*.jsonl")
CACHE = REPO / "experimental" / "data" / "caja_cambios_filas.npy"
RATIOS = (2.846, 1.875, 1.421, 1.125)  # garaje (V112)
FINAL = 3.444
G = 9.81
W = 6  # ticks a cada lado para derivar la velocidad
R_WHEEL = 0.2778  # radio efectivo medido (rpm frente a velocidad en 3.ª)
NEUTRAL_S = 0.17  # punto muerto por subida (V113-V116)
TRAC = 5.7  # m/s²: aceleración máxima sostenida a la salida de las curvas lentas (tracción y control de tracción)
CORNER_LAT = 7.0
# frenada a fondo (km/h, m/s²): tabla de A1 hasta 105 km/h y lo medido en V116 por encima
BRAKE = ((45, 11.87), (65, 12.29), (85, 12.28), (105, 13.05), (125, 14.0), (160, 14.5))
# par por encima de 7400 rpm (V115, logs de octubre con la 2.ª en el corte)
TORQUE_TOP = ((7450, 99.2), (7550, 97.5), (7650, 94.2), (7750, 93.0))


def read_rows(pattern: str, cache: Path) -> np.ndarray:
    """(tipo 1 = gas a fondo / 0 = sin pedales, marcha, v m/s, rpm, par, a en llano) de cada tick válido de los logs."""
    if cache.exists():
        return np.load(cache)
    rows = []
    for f in sorted(glob.glob(pattern)):
        if os.path.getsize(f) > 200e6:
            continue
        with open(f, encoding="utf-8") as fh:
            ticks = [json.loads(line) for line in fh if '"type": "tick"' in line]
        for i in range(W, len(ticks) - W):
            seg = ticks[i - W:i + W + 1]
            a, b, c = seg[0], seg[-1], ticks[i]
            g = c["gear"]
            if a["lap"] != b["lap"] or g not in (2, 3, 4) or any(x["gear"] != g for x in seg):
                continue
            if any(x["vehicle"]["game_brake"] > 0 or abs(x["steering"]) > 0.03 for x in seg):
                continue
            gas = [x["vehicle"]["game_throttle"] for x in seg]
            kind = 1 if min(gas) >= 0.99 else (0 if max(gas) == 0.0 else -1)
            dt = b["t_s"] - a["t_s"]
            pa, pb = a["vehicle"]["position"], b["vehicle"]["position"]
            dh = math.dist((pa[0], pa[2]), (pb[0], pb[2]))
            if kind < 0 or dt <= 0 or dh < 1:
                continue
            sin = (pb[1] - pa[1]) / math.hypot(dh, pb[1] - pa[1])
            a_flat = (b["speed_kmh"] - a["speed_kmh"]) / 3.6 / dt + G * sin
            rows.append((kind, g, c["speed_kmh"] / 3.6, c["rpm"], float(np.median([x["vehicle"]["engine_torque"] for x in seg])), a_flat))
    arr = np.array(rows)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache, arr)
    return arr


def fit(arr: np.ndarray) -> Dict[str, float]:
    kind, gear, v, _rpm, tq, acc = arr.T
    gt = np.array([RATIOS[int(x) - 1] * FINAL for x in gear])
    keep = ~((gear == 2) & (v * 3.6 < 80) & (kind == 1)) & (v * 3.6 > 40)  # la 2.ª lenta la limita la tracción
    w = np.ones_like(v)
    for g in (2, 3, 4):
        for k in (0, 1):
            m = keep & (gear == g) & (kind == k)
            if m.any():
                w[m] = 1.0 / math.sqrt(m.sum())
    x = np.column_stack([tq * gt, -np.ones_like(v), -v ** 2, -(gt ** 2) * acc])[keep]
    coef, *_ = np.linalg.lstsq(x * w[keep, None], acc[keep] * w[keep], rcond=None)
    return dict(zip(("c", "d0", "d2", "k"), (float(c) for c in coef)))


def torque_curve(arr: np.ndarray) -> Tuple[List[float], List[float]]:
    kind, _gear, _v, rpm, tq, _acc = arr.T
    m = (kind == 1) & (tq > 20)
    pts = {}
    for r0 in range(3000, 7800, 100):
        s = m & (rpm >= r0) & (rpm < r0 + 100)
        if s.sum() >= 10:
            pts[r0 + 50.0] = float(np.median(tq[s]))
    for r, t in TORQUE_TOP:
        pts.setdefault(float(r), t)
    xs = sorted(pts)
    return xs, [pts[x] for x in xs]


class Car:
    def __init__(self, model: Dict[str, float], curve: Tuple[List[float], List[float]], mass_scale: float = 1.0):
        self.m = dict(model)
        # masa 1/mass_scale veces la de los logs (p. ej. menos gasolina): el empuje y el aire cambian de efecto; la rodadura (d0) no
        self.m["c"] *= mass_scale
        self.m["d2"] *= mass_scale
        self.rx, self.ty = curve

    def torque(self, r: float) -> float:
        xs, ys = self.rx, self.ty
        if r <= xs[0]:
            return ys[0]
        if r >= xs[-1]:
            return ys[-1]
        i = bisect_right(xs, r)
        return ys[i - 1] + (ys[i] - ys[i - 1]) * (r - xs[i - 1]) / (xs[i] - xs[i - 1])

    def drag(self, v: float) -> float:
        return self.m["d0"] + self.m["d2"] * v * v

    def accel(self, v: float, gt: float) -> Tuple[float, float]:
        r = v * gt / R_WHEEL * 60 / (2 * math.pi)
        a = (self.m["c"] * self.torque(r) * gt - self.drag(v)) / (1 + self.m["k"] * gt * gt)
        return min(a, TRAC), r


class Lap:
    """Límites de curva y pendiente por metro, medidos en las vueltas 2 en adelante de una sesión."""

    def __init__(self, log: Path, band_kmh: float):
        with open(log, encoding="utf-8") as fh:
            ticks = [json.loads(line) for line in fh if '"type": "tick"' in line]
        laps = [t for t in ticks if t["lap"] >= 2]
        n = int(max(t["lap_distance"] for t in laps)) + 1
        vs, cnt, ys, lat = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
        for t in laps:
            i = int(t["lap_distance"]) % n
            vs[i] += t["speed_kmh"] / 3.6
            cnt[i] += 1
            ys[i] += t["vehicle"]["position"][1]
            lat[i] = max(lat[i], abs(t["vehicle"]["lat_accel"]))
        have = np.flatnonzero(cnt > 0)
        grid = np.arange(n)
        self.n = n
        self.v_meas = np.interp(grid, have, vs[have] / cnt[have], period=n)
        y = np.interp(grid, have, ys[have] / cnt[have], period=n)
        self.grade = (np.roll(y, -15) - np.roll(y, 15)) / 30.0
        corner = np.interp(grid, have, lat[have], period=n) > CORNER_LAT
        cap = band_kmh / 3.6
        self.lim = np.minimum(np.where(corner, self.v_meas, cap), cap)
        self.vb = self._backward()

    def _backward(self) -> np.ndarray:
        xs, ys = [p[0] for p in BRAKE], [p[1] for p in BRAKE]
        vb = self.lim.copy()
        for step in range(2 * self.n):
            i = (self.n - 1 - step) % self.n
            j = (i + 1) % self.n
            d = max(float(np.interp(vb[j] * 3.6, xs, ys)) + G * self.grade[i], 0.5)
            vb[i] = min(vb[i], math.sqrt(vb[j] ** 2 + 2 * d))
        return vb

    def simulate(self, car: Car, ratios: Sequence[float] = RATIOS, final: float = FINAL, upshift_rpm: float = 7400.0) -> Tuple[float, int]:
        """Tiempo de vuelta (s) y subidas por vuelta; se recorre dos veces para que el principio y el final encajen."""
        gts = [r * final for r in ratios]
        vb, grade = self.vb, self.grade
        v, g, neutral = float(vb[0]), 0, 0.0
        t_total, shifts = 0.0, 0
        for _ in range(2):
            t_total, shifts = 0.0, 0
            for i in range(self.n):
                j = (i + 1) % self.n
                if v >= vb[i] - 1e-6:  # frenando o en el límite: la marcha la pone el juego
                    v = float(vb[i])
                    g = next(k for k, gt in enumerate(gts) if v * gt / R_WHEEL * 60 / (2 * math.pi) <= upshift_rpm or k == len(gts) - 1)
                    neutral = 0.0
                if neutral > 0:
                    a = -car.drag(v) - G * grade[i]
                else:
                    a, r = car.accel(v, gts[g])
                    a -= G * grade[i]
                    if r >= upshift_rpm and g < len(gts) - 1:
                        g, shifts, neutral = g + 1, shifts + 1, NEUTRAL_S
                v2 = min(math.sqrt(max(v * v + 2 * a, 1.0)), float(vb[j]))
                dt = 2.0 / (v + v2)
                neutral = max(0.0, neutral - dt)
                t_total += dt
                v = v2
        return t_total, shifts


def fmt(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:06.3f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sesion", type=Path, required=True, help="Log de la receta vigente (límites de curva y pendiente)")
    ap.add_argument("--logs", default=LOGS, help="Logs para ajustar el modelo (glob)")
    ap.add_argument("--cache", type=Path, default=CACHE, help="Caché de las filas del ajuste (se borra para releer los logs)")
    ap.add_argument("--banda", type=float, nargs="+", default=[155.0], help="Topes de velocidad a simular (km/h)")
    ap.add_argument("--upshift-rpm", type=float, default=7400.0)
    a = ap.parse_args()
    arr = read_rows(a.logs, a.cache)
    model = fit(arr)
    car = Car(model, torque_curve(arr))
    print(f"modelo: c {model['c']:.5f}  d0 {model['d0']:.3f} m/s²  d2 {model['d2']:.6f} 1/m  k {model['k']:.5f}  "
          f"(resistencia a 150 km/h {car.drag(150 / 3.6):.2f} m/s²; {len(arr)} filas)")
    for band in a.banda:
        lap = Lap(a.sesion, band)
        t0, s0 = lap.simulate(car, upshift_rpm=a.upshift_rpm)
        print(f"\nbanda {band:g}: caja del garaje {fmt(t0)} ({s0} subidas por vuelta)")
        print("  final (todas las marchas):  " + "  ".join(f"{f:.2f} {lap.simulate(car, final=f, upshift_rpm=a.upshift_rpm)[0] - t0:+.3f}"
                                                         for f in (3.2, 3.3, 3.6, 3.75, 3.9, 4.2)))
        for gi in (1, 2, 3):
            parts = []
            for fac in (0.9, 0.95, 1.05, 1.1):
                r = list(RATIOS)
                r[gi] *= fac
                parts.append(f"{r[gi]:.3f} {lap.simulate(car, r, upshift_rpm=a.upshift_rpm)[0] - t0:+.3f}")
            print(f"  {gi + 1}.ª:  " + "  ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
