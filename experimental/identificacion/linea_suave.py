"""A2.0-c (`PLAN_A_LIMITES_COCHE.md`, H61): línea de referencia suavizada en las rectas, para alta velocidad.

`src/refs/sugo_ai.json` es la trayectoria que grabó la IA y lleva micro-quiebros (12 de |κ| > 0,003 en rectas, de 0,25-0,8 m de desplazamiento).
A 60 km/h pasan desapercibidos; a 125 km/h el teacher los sigue con fidelidad y pide 8-12 m/s² laterales en medio de una recta (H60-H61).

Esta herramienta escribe una copia con las posiciones suavizadas (gaussiana σ = 15 m, con cierre de vuelta) **solo donde la propia línea suavizada es recta**
(|κ| < 0,003, con un margen de seguridad hacia las curvas) y un empalme gradual en los bordes. Las curvas reales no se tocan. El resto de campos de cada
punto (velocidad, marcha, orientación...) queda como estaba. No toca el archivo de entrada.

Uso:
    python experimental/identificacion/linea_suave.py [--entrada src/refs/sugo_ai.json] [--salida experimental/data/sugo_smooth.json] [--sigma 15]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[2]
DEFAULT_IN = REPO / "PCARS2-AI" / "src" / "refs" / "sugo_ai.json"
DEFAULT_OUT = REPO / "experimental" / "data" / "sugo_smooth.json"
SIGMA_M = 15.0
MAX_KAPPA = 0.003  # por debajo de esto la línea suavizada se considera recta
ERODE_M = 15  # la zona se acorta esto por cada lado, para no acercarse a una curva real
TAPER_SIGMA_M = 10.0  # empalme gradual en los bordes de cada tramo
MAX_DISPLACEMENT_M = 1.0


def _smooth(a: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussiana con cierre de vuelta (el último punto enlaza con el primero)."""
    half = int(4 * sigma)
    k = np.arange(-half, half + 1)
    w = np.exp(-0.5 * (k / sigma) ** 2)
    w /= w.sum()
    return np.convolve(np.concatenate([a[-half:], a, a[:half]]), w, mode="valid")


def curvature(x: np.ndarray, z: np.ndarray) -> np.ndarray:
    dx, dz = np.gradient(x), np.gradient(z)
    ddx, ddz = np.gradient(dx), np.gradient(dz)
    return (dx * ddz - dz * ddx) / np.maximum((dx * dx + dz * dz) ** 1.5, 1e-9)


def smooth_arrays(x: np.ndarray, z: np.ndarray, sigma: float = SIGMA_M, max_kappa: float = MAX_KAPPA,
                  erode_m: int = ERODE_M, taper_sigma: float = TAPER_SIGMA_M) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Devuelve (x nueva, z nueva, peso de la mezcla en [0, 1]; 1 = totalmente suavizado)."""
    xs, zs = _smooth(x, sigma), _smooth(z, sigma)
    straight = (np.abs(curvature(xs, zs)) < max_kappa).astype(float)
    if erode_m > 0:  # el punto cuenta solo si toda su vecindad de ±erode_m es recta
        k = np.ones(2 * erode_m + 1)
        padded = np.concatenate([straight[-erode_m:], straight, straight[:erode_m]])
        core = (np.convolve(padded, k, mode="valid") >= len(k) - 0.5).astype(float)
    else:
        core = straight
    weight = np.clip(_smooth(core, taper_sigma), 0.0, 1.0)
    return weight * xs + (1 - weight) * x, weight * zs + (1 - weight) * z, weight


def smooth_reference(data: Dict, sigma: float = SIGMA_M, max_displacement: float = MAX_DISPLACEMENT_M) -> Tuple[Dict, List[Dict]]:
    """Copia de la referencia con las posiciones (x, z) suavizadas en rectas; también el informe por tramo."""
    pts = data["points"]
    x = np.array([p["pos"][0] for p in pts], dtype=float)
    z = np.array([p["pos"][2] for p in pts], dtype=float)
    d = np.array([p["d"] for p in pts], dtype=float)
    nx, nz, weight = smooth_arrays(x, z, sigma)
    displacement = np.hypot(nx - x, nz - z)
    if displacement.max() > max_displacement:
        raise ValueError(f"el suavizado mueve la línea {displacement.max():.2f} m, más del máximo ({max_displacement:g} m)")
    k_old = curvature(_smooth(x, 3), _smooth(z, 3))
    k_new = curvature(_smooth(nx, 3), _smooth(nz, 3))
    inside = weight > 0.5
    idx = np.flatnonzero(inside)
    runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1) if len(idx) else []
    report = []
    for run in runs:
        report.append({
            "d0": float(d[run[0]]), "d1": float(d[run[-1]]), "kappa_antes": float(np.abs(k_old[run]).max()),
            "kappa_despues": float(np.abs(k_new[run]).max()), "desplazamiento_m": float(displacement[run].max()),
        })
    out = json.loads(json.dumps(data))  # copia profunda
    for p, ax, az in zip(out["points"], nx, nz):
        p["pos"][0] = round(float(ax), 3)
        p["pos"][2] = round(float(az), 3)
    out["suavizada"] = {"sigma_m": sigma, "max_kappa": MAX_KAPPA, "desplazamiento_max_m": round(float(displacement.max()), 3),
                        "origen": "linea_suave.py (H61)"}
    return out, report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--entrada", type=Path, default=DEFAULT_IN)
    ap.add_argument("--salida", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--sigma", type=float, default=SIGMA_M)
    args = ap.parse_args(argv)
    if args.salida.resolve() == args.entrada.resolve():
        ap.error("la salida no puede ser el archivo de entrada")
    data = json.loads(args.entrada.read_text(encoding="utf-8"))
    out, report = smooth_reference(data, args.sigma)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(out), encoding="utf-8")
    print(f"{len(report)} tramos suavizados; desplazamiento máximo {out['suavizada']['desplazamiento_max_m']} m -> {args.salida}")
    for r in report:
        print(f"  {r['d0']:6.0f}-{r['d1']:6.0f} m  desplazamiento {r['desplazamiento_m']:.2f} m  |κ| máx. {r['kappa_antes']:.4f} -> {r['kappa_despues']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
