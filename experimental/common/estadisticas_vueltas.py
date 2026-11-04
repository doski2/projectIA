"""Mínimo, media y máximo de cada magnitud, vuelta a vuelta, de un log de sesión.

Sirve para ver de un vistazo si las condiciones empeoran con las vueltas (gomas y frenos que se enfrían, agarre que cae) y si el coche las sigue: velocidad, |CTE|, deriva,
aceleración lateral y longitudinal, gas, freno, volante, temperatura y presión de las gomas, temperatura de los frenos, y la lluvia y la temperatura de la pista que
llegaron al empezar cada vuelta. Solo cuentan las vueltas completas (≥ 90 % de la distancia máxima vista); la de salida parada se marca.

Uso:
    python experimental/common/estadisticas_vueltas.py PCARS2-AI/logs/learning/<ts>_sugo_gp_l1_linea.jsonl [otro.jsonl ...] [--magnitud cte --magnitud gomas]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "PCARS2-AI" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from session_log import tick_accels  # noqa: E402

Stat = Tuple[float, float, float]  # mínimo, media, máximo
# nombre → (descripción con unidad, decimales)
MAGNITUDES: Dict[str, Tuple[str, int]] = {
    "velocidad": ("velocidad (km/h)", 0), "cte": ("|CTE| (m)", 2), "deriva": ("deriva (°)", 1), "lateral": ("|lateral| (m/s²)", 1),
    "longitudinal": ("longitudinal (m/s², + acelera)", 1), "gas": ("gas", 2), "freno": ("freno", 2), "volante": ("|volante|", 2),
    "gomas": ("gomas, media de las 4 (°C)", 0), "frenos": ("frenos, media de los 4 (°C)", 0), "presion": ("presión de las gomas, media (bar)", 2),
}


def _deriva(vehicle: dict) -> float:
    lv = vehicle.get("local_velocity")
    if not lv or -lv[2] <= 5.0:
        return 0.0
    return abs(math.degrees(math.atan2(lv[0], -lv[2])))


def _media(valores: Optional[Sequence[float]]) -> Optional[float]:
    return sum(valores) / len(valores) if valores else None


def valores_tick(t: dict) -> Dict[str, Optional[float]]:
    v = t.get("vehicle") or {}
    acc = tick_accels(v)
    presion = _media(v.get("air_pressure") or [])
    return {
        "velocidad": float(t["speed_kmh"]), "cte": abs(float(t["signed_cte"])), "deriva": _deriva(v),
        "lateral": abs(acc[0]) if acc else None, "longitudinal": acc[1] if acc else None,
        "gas": float(t["throttle"]), "freno": float(t["brake"]), "volante": abs(float(t["steering"])),
        "gomas": _media(v.get("tyre_temp") or []), "frenos": _media(v.get("brake_temp") or []),
        "presion": presion / 100.0 if presion is not None else None,  # `air_pressure` va en centésimas de bar
    }


def cargar(ruta: Path) -> Tuple[List[dict], List[dict]]:
    ticks, condiciones = [], []
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            if '"type": "tick"' in linea:
                ticks.append(json.loads(linea))
            elif '"type": "conditions"' in linea:
                condiciones.append(json.loads(linea))
    return ticks, condiciones


def estadisticas(ticks: Sequence[dict], condiciones: Sequence[dict] = (), cobertura: float = 0.9) -> Dict[int, Dict[str, object]]:
    """{vuelta: {magnitud: (mín, media, máx), "tiempo_s": s, "fuera": ticks con rueda fuera, "lluvia": x, "pista_c": x, "ambiente_c": x}} de las vueltas completas."""
    if not ticks:
        return {}
    largo = max(float(t["lap_distance"]) for t in ticks)
    por_vuelta: Dict[int, List[dict]] = {}
    for t in ticks:
        por_vuelta.setdefault(int(t["lap"]), []).append(t)
    out: Dict[int, Dict[str, object]] = {}
    for lap, tk in sorted(por_vuelta.items()):
        d = [float(t["lap_distance"]) for t in tk]
        if len(tk) < 100 or max(d) - min(d) < cobertura * largo:
            continue
        columnas: Dict[str, List[float]] = {k: [] for k in MAGNITUDES}
        for t in tk:
            for k, val in valores_tick(t).items():
                if val is not None:
                    columnas[k].append(val)
        fila: Dict[str, object] = {k: (min(c), sum(c) / len(c), max(c)) for k, c in columnas.items() if c}
        fila["tiempo_s"] = float(tk[-1]["t_s"]) - float(tk[0]["t_s"])
        fila["fuera"] = sum(1 for t in tk if any(x for x in (t.get("vehicle") or {}).get("terrain", [])))
        previas = [c for c in condiciones if float(c.get("t_s", 0.0)) <= float(tk[0]["t_s"])]
        cond = previas[-1] if previas else (condiciones[0] if condiciones else {})
        fila["lluvia"], fila["pista_c"], fila["ambiente_c"] = cond.get("rain"), cond.get("track_c"), cond.get("ambient_c")
        out[lap] = fila
    return out


def tabla(stats: Dict[int, Dict[str, object]], magnitudes: Sequence[str] = tuple(MAGNITUDES)) -> str:
    if not stats:
        return "(sin vueltas completas)"
    vueltas = sorted(stats)
    primera = vueltas[0]
    ancho = 20
    lineas = ["vuelta" + " " * 32 + "".join(f"{('V%d' % v) + ('*' if v == primera else ''):>{ancho}}" for v in vueltas)]
    lineas.append("tiempo (s)" + " " * 28 + "".join(f"{stats[v]['tiempo_s']:>{ancho}.1f}" for v in vueltas))
    lineas.append("ticks con rueda fuera" + " " * 17 + "".join(f"{stats[v]['fuera']:>{ancho}d}" for v in vueltas))
    lineas.append("lluvia / pista °C / ambiente °C" + " " * 7 + "".join(f"{'%s / %s / %s' % (stats[v]['lluvia'], stats[v]['pista_c'], stats[v]['ambiente_c']):>{ancho}}" for v in vueltas))
    lineas.append("")
    lineas.append(f"{'mín / media / máx':<38}")
    for nombre in magnitudes:
        desc, dec = MAGNITUDES[nombre]
        celdas = []
        for v in vueltas:
            s: Optional[Stat] = stats[v].get(nombre)  # type: ignore[assignment]
            celdas.append(f"{s[0]:.{dec}f}/{s[1]:.{dec}f}/{s[2]:.{dec}f}" if s else "-")
        lineas.append(f"{desc:<38}" + "".join(f"{c:>{ancho}}" for c in celdas))
    lineas.append("(* = la primera vuelta completa lleva la salida parada)")
    return "\n".join(lineas)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("logs", nargs="+", type=Path)
    ap.add_argument("--magnitud", action="append", choices=sorted(MAGNITUDES), help="solo estas magnitudes (se puede repetir); por defecto todas")
    args = ap.parse_args(argv)
    for ruta in args.logs:
        ticks, condiciones = cargar(ruta)
        print(f"\n== {ruta.name}")
        print(tabla(estadisticas(ticks, condiciones), args.magnitud or tuple(MAGNITUDES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
