"""Informe HTML del mapa de la pista (D1): cobertura de los bordes y gráficos. Distinto del informe de sesión de `experimental/common/informe_c0.py`,
que habla de la salud de una sesión (incidencias, pausas, daño); este habla de **qué sabemos de la pista**: dónde hay bordes medidos, hasta dónde se ha comprobado
que llega el asfalto y dónde faltan datos.

Uso:
    python circuito_virtual/src/informe_mapa.py [--mapa pistas/sugo_gp/mapa.json] [--obs pistas/sugo_gp/observaciones_logs.json] [--salida pistas/sugo_gp/informes/informe_mapa.html]
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from circuito_virtual.src.bordes_logs import Observaciones  # noqa: E402
from circuito_virtual.src.mapa import Mapa  # noqa: E402

PISTA = REPO / "circuito_virtual" / "pistas" / "sugo_gp"


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _normal_derecha(mapa: Mapa) -> Tuple[np.ndarray, np.ndarray]:
    return mapa.tz, -mapa.tx


def figura_planta(mapa: Mapa, obs: Observaciones) -> str:
    """Eje de la pista y, por encima, los puntos donde se midió el borde de cada lado (naranja = izquierdo, azul = derecho)."""
    fig, ax = plt.subplots(figsize=(8.5, 7.5))
    ax.plot(mapa.x, mapa.z, color="#888", lw=1.0, label="eje (referencia suavizada)")
    b = obs.bordes()
    nx, nz = _normal_derecha(mapa)
    for lado, color, nombre in (("izq", "#d9822b", "borde izquierdo medido"), ("dcha", "#2b6fd9", "borde derecho medido")):
        ok = np.isfinite(b[lado])
        if ok.any():
            n = b[lado][ok]
            ax.scatter(mapa.x[ok] + n * nx[ok], mapa.z[ok] + n * nz[ok], s=4, color=color, label=nombre)
    sin_datos = obs.ticks == 0
    if sin_datos.any():
        ax.scatter(mapa.x[sin_datos], mapa.z[sin_datos], s=6, color="#c33", marker="x", label="metros sin ningún dato")
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("z (m)")
    ax.legend(loc="best", fontsize=8)
    ax.set_title(f"{mapa.nombre}: eje y bordes medidos")
    return _png(fig)


def figura_lateral(mapa: Mapa, obs: Observaciones) -> str:
    """Posición lateral de las ruedas frente a la distancia: hasta dónde llegó cada lado en superficie de carrera y dónde se vio ya fuera."""
    fig, ax = plt.subplots(figsize=(11, 4.2))
    s = mapa.s
    ax.fill_between(s, obs.izq_dentro, obs.dcha_dentro, color="#bfe3bf", label="asfalto comprobado (ruedas en superficie de carrera)")
    ax.plot(s, obs.izq_fuera, ".", ms=2.5, color="#d9822b", label="rueda izquierda ya fuera")
    ax.plot(s, obs.dcha_fuera, ".", ms=2.5, color="#2b6fd9", label="rueda derecha ya fuera")
    b = obs.bordes()
    ax.plot(s, b["izq"], "-", lw=1.4, color="#a85a10", label="borde izquierdo medido")
    ax.plot(s, b["dcha"], "-", lw=1.4, color="#154a9e", label="borde derecho medido")
    ax.axhline(0.0, color="#555", lw=0.8)
    ax.set_xlabel("s: distancia de vuelta (m)")
    ax.set_ylabel("n de la rueda respecto al eje (m, + = derecha)")
    ax.legend(loc="upper right", fontsize=7, ncol=2)
    ax.set_title("Lo que se sabe de la anchura de la pista")
    return _png(fig)


def figura_cobertura(mapa: Mapa, obs: Observaciones) -> str:
    """Ticks por metro (escala logarítmica): dónde hay muchos datos y dónde pocos."""
    fig, ax = plt.subplots(figsize=(11, 2.6))
    ax.semilogy(mapa.s, np.maximum(obs.ticks, 0.8), color="#555", lw=0.8)
    ax.set_xlabel("s: distancia de vuelta (m)")
    ax.set_ylabel("ticks por metro")
    ax.set_title("Cobertura de datos")
    return _png(fig)


def tramos(mask: np.ndarray, longitud_m: float, minimo_m: float = 20.0) -> List[Tuple[float, float]]:
    """Tramos consecutivos (en metros) donde `mask` es verdadera, de al menos `minimo_m`."""
    n = len(mask)
    paso = longitud_m / n
    idx = np.flatnonzero(mask)
    if not len(idx):
        return []
    runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
    return [(float(r[0] * paso), float((r[-1] + 1) * paso)) for r in runs if len(r) * paso >= minimo_m]


def generar(mapa: Mapa, obs: Observaciones, salida: Path) -> Path:
    cob = obs.cobertura()
    sin_borde = obs.bordes()
    faltan = tramos(~(np.isfinite(sin_borde["izq"]) & np.isfinite(sin_borde["dcha"])), mapa.longitud_m, 50.0)
    filas = "".join(f"<tr><td>{html.escape(k.replace('_', ' '))}</td><td>{100 * v:.1f} %</td></tr>" for k, v in cob.items())
    lista_logs = "".join(f"<li>{html.escape(n)}</li>" for n in obs.logs[:60]) + ("<li>…</li>" if len(obs.logs) > 60 else "")
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Informe del mapa {html.escape(mapa.nombre)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#222}}table{{border-collapse:collapse}}
td,th{{border:1px solid #ccc;padding:4px 10px;text-align:left}}img{{max-width:100%}}h2{{margin-top:28px}}.n{{color:#666;font-size:.9em}}</style></head><body>
<h1>Mapa de {html.escape(mapa.nombre)}</h1>
<p class="n">{mapa.longitud_m:.0f} m, {mapa.n_puntos} puntos; semivía supuesta {obs.semivia_m:g} m; {len(obs.logs)} logs de esquema 2.</p>
<h2>Cobertura</h2><table><tr><th>Concepto</th><th>Parte de la vuelta</th></tr>{filas}</table>
<p>Tramos de al menos 50 m sin los dos bordes medidos: {', '.join(f'{a:.0f}-{b:.0f} m' for a, b in faltan) or 'ninguno'}.</p>
<h2>Planta</h2><img src="{figura_planta(mapa, obs)}" alt="planta">
<h2>Anchura frente a la distancia</h2><img src="{figura_lateral(mapa, obs)}" alt="anchura">
<h2>Datos por metro</h2><img src="{figura_cobertura(mapa, obs)}" alt="cobertura">
<h2>Logs usados</h2><ul>{lista_logs}</ul></body></html>"""
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(doc, encoding="utf-8")
    return salida


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--mapa", type=Path, default=PISTA / "mapa.json")
    ap.add_argument("--obs", type=Path, default=PISTA / "observaciones_logs.json")
    ap.add_argument("--salida", type=Path, default=PISTA / "informes" / "informe_mapa.html")
    args = ap.parse_args(argv)
    import json

    mapa = Mapa.cargar(args.mapa)
    obs = Observaciones.de_dict(json.loads(args.obs.read_text(encoding="utf-8")))
    print(generar(mapa, obs, args.salida))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
