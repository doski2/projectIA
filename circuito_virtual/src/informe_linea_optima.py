"""Informe HTML de D2: la línea óptima frente a la suavizada, para cada nivel de ritmo.

Qué enseña: tiempo previsto de cada línea, planta con el pasillo, `n(s)` de cada ritmo (para ver si la forma depende del modelo), velocidad prevista y dónde la línea
toca el borde del pasillo (donde manda la restricción y no el solver). Marca los tramos donde la velocidad prevista supera lo que el propio coche ha medido
(`V_MEDIDA_COCHE_KMH`): ahí el solver extrapola con las envolventes de la IA.

Uso:
    python circuito_virtual/src/informe_linea_optima.py [--dir circuito_virtual/pistas/sugo_gp] [--salida .../informes/informe_linea_optima.html]
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from circuito_virtual.src import ajuste_ia  # noqa: E402
from circuito_virtual.src import linea_optima as lo  # noqa: E402
from circuito_virtual.src.bordes_logs import Observaciones  # noqa: E402
from circuito_virtual.src.informe_mapa import _png, tramos  # noqa: E402
from circuito_virtual.src.mapa import Mapa  # noqa: E402

KAPPA_FINA_M = 1  # curvatura casi sin suavizar: si la ganancia aguanta, viene de la geometría y no del suavizado del modelo
V_MEDIDA_COCHE_KMH = 125.0  # lo más rápido que se ha medido con el propio coche (A1)
TOCA_BORDE_M = 0.05
COLORES = {0: "#2b6fd9", 1: "#d9822b", 2: "#2a9d5c"}


def _linea_xz(mapa: Mapa, n: np.ndarray):
    return lo.geometria(mapa, n)


def figura_planta(mapa: Mapa, lo_c: np.ndarray, hi_c: np.ndarray, lineas: Dict[float, np.ndarray]) -> str:
    fig, ax = plt.subplots(figsize=(9, 7.8))
    ax.plot(mapa.x, mapa.z, color="#999", lw=0.8, label="eje (línea suavizada)")
    for lado, color in ((lo_c, "#c33"), (hi_c, "#c33")):
        x, z = lo.geometria(mapa, lado)
        ax.plot(x, z, color=color, lw=0.5, alpha=0.7)
    ax.plot([], [], color="#c33", lw=0.8, label="límite del centro del coche (pasillo)")
    for i, (f, n) in enumerate(lineas.items()):
        x, z = _linea_xz(mapa, n)
        ax.plot(x, z, color=COLORES[i % 3], lw=1.0, label=f"óptima f = {f:g}")
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("z (m)")
    ax.legend(loc="best", fontsize=8)
    ax.set_title("Planta: pasillo y líneas óptimas")
    return _png(fig)


def figura_n(mapa: Mapa, lo_c: np.ndarray, hi_c: np.ndarray, lineas: Dict[float, np.ndarray]) -> str:
    fig, ax = plt.subplots(figsize=(12, 4.4))
    ax.fill_between(mapa.s, lo_c, hi_c, color="#e8f3e8", label="pasillo del centro")
    for i, (f, n) in enumerate(lineas.items()):
        ax.plot(mapa.s, n, color=COLORES[i % 3], lw=1.0, label=f"óptima f = {f:g}")
    ax.axhline(0.0, color="#555", lw=0.8)
    ax.set_xlabel("s: distancia de vuelta (m)")
    ax.set_ylabel("n del centro del coche (m, + = derecha)")
    ax.legend(loc="upper right", fontsize=8, ncol=4)
    ax.set_title("Desplazamiento lateral frente a la distancia")
    return _png(fig)


def figura_v(mapa: Mapa, f: float, v_base: np.ndarray, v_opt: np.ndarray) -> str:
    fig, ax = plt.subplots(figsize=(12, 4.2))
    ax.plot(mapa.s, v_base * 3.6, color="#888", lw=1.0, label="suavizada")
    ax.plot(mapa.s, v_opt * 3.6, color="#2b6fd9", lw=1.0, label="óptima")
    ax.axhline(V_MEDIDA_COCHE_KMH, color="#c33", lw=0.8, ls="--", label=f"{V_MEDIDA_COCHE_KMH:g} km/h: lo más rápido medido con el coche")
    ax.set_xlabel("s: distancia de vuelta (m)")
    ax.set_ylabel("velocidad prevista (km/h)")
    ax.legend(loc="lower right", fontsize=8)
    ax.set_title(f"Velocidad prevista, ritmo f = {f:g}")
    return _png(fig)


def analizar(mapa: Mapa, lo_c: np.ndarray, hi_c: np.ndarray, coche, f: float, n: np.ndarray) -> Dict:
    c = ajuste_ia.escalar(coche, f)
    cero = np.zeros(mapa.n_puntos)
    v0, prof0, tr0 = lo.perfil_en_s(mapa, cero, c)
    v1, prof1, tr1 = lo.perfil_en_s(mapa, n, c)
    toca = (n <= lo_c + TOCA_BORDE_M) | (n >= hi_c - TOCA_BORDE_M)
    libre = (hi_c - lo_c) > 2 * TOCA_BORDE_M  # donde el pasillo es solo el eje no hay nada que tocar
    k0, k1 = lo.curvatura_continua(tr0), lo.curvatura_continua(tr1)
    fina0, fina1 = lo.tiempo_vuelta(mapa, cero, c, KAPPA_FINA_M), lo.tiempo_vuelta(mapa, n, c, KAPPA_FINA_M)
    return {"t_base_fina": fina0, "t_opt_fina": fina1, "f": f, "t_base": prof0.time_s, "t_opt": prof1.time_s, "v_base": v0, "v_opt": v1, "longitud_base": tr0.length_m, "longitud_opt": tr1.length_m,
            "kappa_base": k0, "kappa_opt": k1, "toca_borde": float(np.mean(toca[libre])) if libre.any() else 0.0,
            "sobre_medido_base": float(np.mean(v0 * 3.6 > V_MEDIDA_COCHE_KMH)), "sobre_medido_opt": float(np.mean(v1 * 3.6 > V_MEDIDA_COCHE_KMH)),
            "n_min": float(n.min()), "n_max": float(n.max()), "n_rms": float(np.sqrt(np.mean(n ** 2)))}


def generar(mapa: Mapa, obs: Observaciones, coche, lineas: Dict[float, np.ndarray], margen_m: float, salida: Path) -> Path:
    lo_c, hi_c = lo.pasillo_centro(mapa, obs, margen_m)
    filas: List[Dict] = [analizar(mapa, lo_c, hi_c, coche, f, n) for f, n in lineas.items()]
    tabla = "".join(
        f"<tr><td>{r['f']:g}</td><td>{r['t_base']:.2f}</td><td>{r['t_opt']:.2f}</td><td>{r['t_opt'] - r['t_base']:+.2f} ({100 * (r['t_opt'] / r['t_base'] - 1):+.1f} %)</td>"
        f"<td>{r['longitud_base']:.1f} → {r['longitud_opt']:.1f}</td><td>{r['kappa_base']['kappa_max']:.4f} → {r['kappa_opt']['kappa_max']:.4f}</td>"
        f"<td>{r['kappa_base']['salto_max']:.5f} → {r['kappa_opt']['salto_max']:.5f}</td><td>{100 * (r['t_opt_fina'] / r['t_base_fina'] - 1):+.1f} %</td><td>{100 * r['toca_borde']:.0f} %</td>"
        f"<td>{100 * r['sobre_medido_base']:.0f} → {100 * r['sobre_medido_opt']:.0f} %</td><td>{r['n_min']:+.2f} / {r['n_max']:+.2f}</td></tr>"
        for r in filas)
    ns = list(lineas.values())
    dif = [f"f = {list(lineas)[i]:g} frente a {list(lineas)[j]:g}: {np.sqrt(np.mean((ns[i] - ns[j]) ** 2)):.2f} m rms, {np.abs(ns[i] - ns[j]).max():.2f} m máx."
           for i in range(len(ns)) for j in range(i + 1, len(ns))]
    estrecho = tramos((hi_c - lo_c) < 0.2, mapa.longitud_m, 20.0)
    fig_v = "".join(f"<h2>Velocidad prevista, f = {r['f']:g}</h2><img src=\"{figura_v(mapa, r['f'], r['v_base'], r['v_opt'])}\" alt=\"velocidad\">" for r in filas)
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Línea óptima de {html.escape(mapa.nombre)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1150px;margin:24px auto;padding:0 16px;color:#222}}table{{border-collapse:collapse;font-size:.92em}}
td,th{{border:1px solid #ccc;padding:4px 10px;text-align:left}}img{{max-width:100%}}h2{{margin-top:28px}}.n{{color:#666;font-size:.9em}}</style></head><body>
<h1>Línea óptima de {html.escape(mapa.nombre)} (D2)</h1>
<p class="n">Tiempo previsto por el solver (<code>perfil_velocidad.solve</code>) con las envolventes de la IA × ritmo f; margen al borde {margen_m:g} m, semivía supuesta {obs.semivia_m:g} m.
Los tiempos son de modelo: dicen cuánto gana la línea con el mismo coche, no cuánto tardará el coche real.</p>
<table><tr><th>ritmo f</th><th>suavizada (s)</th><th>óptima (s)</th><th>diferencia (s)</th><th>longitud (m)</th><th>|κ| máx. (1/m)</th><th>salto de |κ| máx.</th>
<th>con |κ| casi sin suavizar</th><th>toca el borde</th><th>sobre {V_MEDIDA_COCHE_KMH:g} km/h</th><th>n mín. / máx. (m)</th></tr>{tabla}</table>
<p>Lo que cambia la forma de la línea con el ritmo: {'; '.join(dif)}</p>
<p>Tramos de al menos 20 m donde el pasillo del centro mide menos de 20 cm (la línea no puede salirse del eje): {', '.join(f'{a:.0f}-{b:.0f} m' for a, b in estrecho) or 'ninguno'}.</p>
<h2>Planta</h2><img src="{figura_planta(mapa, lo_c, hi_c, lineas)}" alt="planta">
<h2>Desplazamiento lateral</h2><img src="{figura_n(mapa, lo_c, hi_c, lineas)}" alt="n">
{fig_v}
</body></html>"""
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(doc, encoding="utf-8")
    return salida


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--dir", type=Path, default=lo.PISTA)
    ap.add_argument("--ritmos", type=float, nargs="+", default=list(lo.RITMOS))
    ap.add_argument("--margen", type=float, default=lo.MARGEN_M)
    ap.add_argument("--salida", type=Path, default=None)
    args = ap.parse_args(argv)
    mapa = Mapa.cargar(args.dir / "mapa.json")
    obs = Observaciones.de_dict(json.loads((args.dir / "observaciones_logs.json").read_text(encoding="utf-8")))
    lineas = {f: np.load(args.dir / f"sugo_optima_f{round(f * 1000)}_n.npy") for f in args.ritmos}
    salida = args.salida or args.dir / "informes" / "informe_linea_optima.html"
    print(generar(mapa, obs, lo.coche_ia(), lineas, args.margen, salida))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
