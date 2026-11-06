"""Calidad del volante de una sesión del teacher (V19): cuánto corrige, no solo cuánto se desvía.

Una vuelta rápida con el volante siempre corrigiendo es mala aunque el CTE medio sea bajo: es el lazo de dirección rozando la inestabilidad (V18). Por tramo y por
banda de velocidad se calcula:

- **volante rms** y **tasa** (media de |Δvolante|/Δt, en 1/s: lo que se mueve la dirección);
- **inversiones por 100 m**: veces que el volante cambia de sentido con una amplitud mínima (histéresis `UMBRAL_INVERSION`), que es lo que se ve como «zigzag»;
- **|CTE| rms y máximo** y la **deriva máxima** (ángulo atan2(v lateral, v longitudinal), como en `teacher_controller.slip_angle`).

«Recta» es donde la línea de referencia tiene |κ| < `KAPPA_RECTA` en ±`VENTANA_RECTA_M` metros. Ahí el volante debería estar casi quieto; en curva, lo que
pide la curva (la media), no los cambios de sentido. Se ignoran los ticks de seguridad, fuera de pista o por debajo de `V_MIN_KMH`.

Uso:
    python experimental/common/analisis_volante.py PCARS2-AI/logs/learning/<ts>_sugo_gp_l1_linea.jsonl [--desde M] [--hasta M]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "PCARS2-AI" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "PCARS2-AI" / "src"))

KAPPA_RECTA = 0.002
VENTANA_RECTA_M = 15
UMBRAL_INVERSION = 0.03  # amplitud mínima (unidades de volante) para contar una inversión
V_MIN_KMH = 30.0
BANDAS_KMH = (0.0, 70.0, 85.0, 95.0, 105.0, 200.0)


def inversiones(volante: Union[Sequence[float], np.ndarray], umbral: float = UMBRAL_INVERSION) -> int:
    """Cambios de sentido del volante con histéresis: solo cuenta cuando se aleja `umbral` del último extremo."""
    n = 0
    sentido = 0
    extremo: Optional[float] = None
    for x in volante:
        if extremo is None:
            extremo = x
        elif sentido == 0:
            if x - extremo > umbral:
                sentido, extremo = 1, x
            elif extremo - x > umbral:
                sentido, extremo = -1, x
        elif sentido == 1:
            if x > extremo:
                extremo = x
            elif extremo - x > umbral:
                n += 1
                sentido, extremo = -1, x
        else:
            if x < extremo:
                extremo = x
            elif x - extremo > umbral:
                n += 1
                sentido, extremo = 1, x
    return n


def cargar(ruta: Path) -> Dict[str, np.ndarray]:
    filas = []
    cabecera: Dict = {}
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            if '"type": "session"' in linea and not cabecera:
                cabecera = json.loads(linea)
            elif '"type": "tick"' in linea:
                t = json.loads(linea)
                lv = (t.get("vehicle") or {}).get("local_velocity") or [0.0, 0.0, 0.0]
                v_long = -float(lv[2])
                beta = math.degrees(math.atan2(float(lv[0]), v_long)) if v_long > 5.0 else 0.0
                filas.append((t["t_s"], t["lap_distance"], t["speed_kmh"], t["signed_cte"], t["steering"], beta,
                              1.0 if (t.get("safety_override") or t.get("off_track") or t.get("off_surface")) else 0.0))
    a = np.array(filas, dtype=float)
    return {"t": a[:, 0], "d": a[:, 1], "v": a[:, 2], "cte": a[:, 3], "volante": a[:, 4], "beta": a[:, 5], "seguridad": a[:, 6],
            "referencia": cabecera.get("reference", "")}


def mascara_recta(ruta_referencia: str, d: np.ndarray) -> np.ndarray:
    """True donde la línea es recta en ±`VENTANA_RECTA_M` m (curvatura de `ReferenceLine`, como la ve el teacher)."""
    from reference_recorder import ReferenceLine  # noqa: PLC0415

    ref = ReferenceLine.load(ruta_referencia)
    n = int(ref.track_length)
    kappa = np.array([abs(ref.curvature(float(m))) for m in range(n)])
    h = VENTANA_RECTA_M
    cerca = np.max(np.stack([np.roll(kappa, k) for k in range(-h, h + 1)]), axis=0)
    return cerca[np.clip(d.astype(int), 0, n - 1)] < KAPPA_RECTA


def metricas(d: np.ndarray, t: np.ndarray, volante: np.ndarray, cte: np.ndarray, beta: np.ndarray, mascara: np.ndarray) -> Optional[Dict[str, float]]:
    """Métricas del volante en los ticks de `mascara` (varios tramos sueltos: las inversiones y la tasa se miden dentro de cada uno)."""
    if mascara.sum() < 20:
        return None
    idx = np.flatnonzero(mascara)
    tramos = np.split(idx, np.flatnonzero((np.diff(idx) > 3)) + 1)
    inv = 0
    longitud = 0.0
    var = 0.0
    dt_total = 0.0
    for tr in tramos:
        if len(tr) < 5:
            continue
        inv += inversiones(volante[tr])
        longitud += float(np.sum(np.clip(np.diff(d[tr]), 0.0, 50.0)))  # metros recorridos; el salto de fin de vuelta (negativo) no cuenta
        var += float(np.sum(np.abs(np.diff(volante[tr]))))
        dt_total += float(t[tr[-1]] - t[tr[0]])
    if longitud < 20.0 or dt_total <= 0.0:
        return None
    return {"metros": longitud, "volante_rms": float(np.sqrt(np.mean(volante[idx] ** 2))), "tasa": var / dt_total,
            "inversiones_100m": 100.0 * inv / longitud, "cte_rms": float(np.sqrt(np.mean(cte[idx] ** 2))),
            "cte_max": float(np.abs(cte[idx]).max()), "deriva_max": float(np.abs(beta[idx]).max())}


def analizar(ruta: Path, desde: float = 0.0, hasta: float = 1e9) -> Dict:
    s = cargar(ruta)
    ok = (s["seguridad"] == 0) & (s["v"] >= V_MIN_KMH) & (s["d"] >= desde) & (s["d"] <= hasta)
    recta = mascara_recta(str(s["referencia"]), s["d"]) if s["referencia"] else np.zeros(len(s["d"]), dtype=bool)
    out: Dict = {"ruta": str(ruta), "ticks": int(len(s["d"])), "hasta_m": float(s["d"].max()), "bandas": []}
    args = (s["d"], s["t"], s["volante"], s["cte"], s["beta"])
    out["total"] = metricas(*args, ok)
    out["rectas"] = metricas(*args, ok & recta)
    out["curvas"] = metricas(*args, ok & ~recta)
    for lo, hi in zip(BANDAS_KMH[:-1], BANDAS_KMH[1:]):
        banda = ok & (s["v"] >= lo) & (s["v"] < hi)
        out["bandas"].append({"banda_kmh": f"{lo:g}-{hi:g}", "rectas": metricas(*args, banda & recta), "curvas": metricas(*args, banda & ~recta)})
    return out


def _fila(nombre: str, m: Optional[Dict[str, float]]) -> str:
    if not m:
        return f"  {nombre:<22} (sin datos suficientes)"
    return (f"  {nombre:<22} {m['metros']:7.0f} m  volante rms {m['volante_rms']:.3f}  tasa {m['tasa']:.2f}/s  inversiones {m['inversiones_100m']:5.1f}/100 m  "
            f"|CTE| rms {m['cte_rms']:.2f} máx {m['cte_max']:.2f} m  deriva máx {m['deriva_max']:.1f}°")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("log", type=Path)
    ap.add_argument("--desde", type=float, default=0.0)
    ap.add_argument("--hasta", type=float, default=1e9)
    a = ap.parse_args(argv)
    r = analizar(a.log, a.desde, a.hasta)
    print(f"{a.log.name}: {r['ticks']} ticks, hasta {r['hasta_m']:.0f} m")
    for k in ("total", "rectas", "curvas"):
        print(_fila(k, r[k]))
    print("Por banda de velocidad (km/h):")
    for b in r["bandas"]:
        if b["rectas"] or b["curvas"]:
            print(f" {b['banda_kmh']}")
            print(_fila("  rectas", b["rectas"]))
            print(_fila("  curvas", b["curvas"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
