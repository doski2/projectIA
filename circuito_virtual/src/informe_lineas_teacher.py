"""Informe HTML de las líneas que sigue el teacher y de lo que pasó con cada una en el juego (V15-V62).

Qué enseña: (1) las líneas (suavizada, `a1mu9`, `a1mu9b`, `a1mu9c15`, `a1mu9c12`) con el tiempo previsto del solver para el coche del teacher, su longitud y su variación de curvatura;
(2) dónde serpentea cada una respecto a la suavizada (máximo móvil de |Δκ| en ventanas de 100 m, con la curvatura **del teacher**) y las zonas donde fallaron las sesiones;
(3) una tabla con **todas las sesiones A2.0 de vuelta completa a 100 km/h o más** que hay en `PCARS2-AI/logs/learning` (se lee de los logs, así que una sesión nueva aparece sola al regenerar):
línea, banda, experimento, tiempo de la vuelta lanzada, |CTE| máx., |CTE| máx. en las zonas problemáticas y ticks con ruedas fuera de la superficie de carrera.
El criterio completo de V19 (rectas, tasa, deriva) lo da `experimental/common/resumen_sesion.py`; aquí solo se ven los indicadores que salen del log sin importar `experimental`
(`circuito_virtual` no importa de él, ver `README.md`).

Uso:
    python circuito_virtual/src/informe_lineas_teacher.py [--salida circuito_virtual/pistas/sugo_gp/informes/informe_lineas_teacher.html] [--banda-min 100]
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "PCARS2-AI" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from circuito_virtual.src import linea_optima as lo  # noqa: E402
from circuito_virtual.src.bordes_logs import Observaciones  # noqa: E402
from circuito_virtual.src.informe_mapa import _png  # noqa: E402
from circuito_virtual.src.mapa import Mapa  # noqa: E402

LOGS = REPO / "PCARS2-AI" / "logs" / "learning"
LINEAS: Dict[str, Optional[str]] = {  # nombre → archivo `_n.npy` (None = el eje, la suavizada)
    "suavizada": None, "a1mu9": "sugo_optima_a1mu9_n.npy", "a1mu9b": "sugo_optima_a1mu9b_n.npy",
    "a1mu9c15": "sugo_optima_a1mu9c15_n.npy", "a1mu9c12": "sugo_optima_a1mu9c12_n.npy",
}
COLORES = {"suavizada": "#888888", "a1mu9": "#2a9d5c", "a1mu9b": "#d9822b", "a1mu9c15": "#7a4fd1", "a1mu9c12": "#2b6fd9"}
ZONAS: Dict[str, Tuple[float, float]] = {"S 400-600 m": (400.0, 600.0), "880-980 m": (880.0, 980.0), "S 2380-2560 m": (2380.0, 2560.0), "2680-2870 m": (2680.0, 2870.0)}
TOPE_SOLVER_KMH = 125.0  # las líneas se hicieron con este tope (V62)
CRITERIO_CTE_M = 1.8


def resumen_sesion(log: Path, zonas: Dict[str, Tuple[float, float]] = ZONAS) -> Optional[Dict]:
    """Indicadores de un log A2.0 de vuelta completa, o None si no lo es. Las vueltas con índice ≥ 2 son las lanzadas."""
    from pcars2_surface import RACING_TERRAIN_IDS  # noqa: PLC0415

    with open(log, encoding="utf-8") as fh:
        cab = json.loads(fh.readline())
        if cab.get("type") != "session":
            return None
        ticks = []
        for linea in fh:
            if '"type": "tick"' not in linea:
                continue
            t = json.loads(linea)
            veh = t.get("vehicle") or {}
            terr = veh.get("terrain")
            ticks.append((int(t["lap"]), float(t["lap_distance"]), float(t["t_s"]), float(t["signed_cte"]), float(t["speed_kmh"]),
                          bool(terr) and any(x not in RACING_TERRAIN_IDS for x in terr)))
    if not ticks:
        return None
    por_vuelta: Dict[int, List[Tuple]] = {}
    for tk in ticks:
        por_vuelta.setdefault(tk[0], []).append(tk)
    completas = {v: s for v, s in por_vuelta.items() if v >= 2 and s[-1][1] - s[0][1] > 0.9 * 3500.0}
    if not completas:
        return None
    tiempos = {v: s[-1][2] - s[0][2] for v, s in completas.items()}
    cte = np.array([abs(tk[3]) for s in completas.values() for tk in s])
    pico_zona = {}
    for nombre, (a, b) in zonas.items():
        vals = [abs(tk[3]) for s in completas.values() for tk in s if a <= tk[1] <= b]
        pico_zona[nombre] = max(vals) if vals else float("nan")
    return {"log": log.name[:16], "linea": Path(str(cab.get("reference") or "")).stem, "banda": float(cab.get("speed_band_kmh") or 0.0),
            "experimento": str(cab.get("experiment") or ""), "git": str(cab.get("git") or ""), "vueltas": len(completas), "vuelta_s": min(tiempos.values()),
            "cte_max": float(cte.max()), "zonas": pico_zona, "fuera": int(sum(1 for tk in ticks if tk[5])), "v_max": max(tk[4] for tk in ticks)}


def sesiones(banda_min: float = 100.0, logs: Path = LOGS) -> List[Dict]:
    """Sesiones A2.0 (experimento `a2_*`) a `banda_min` km/h o más, de la más antigua a la más reciente."""
    out = []
    for log in sorted(logs.glob("*_sugo_gp_l1_linea.jsonl")):
        with open(log, encoding="utf-8") as fh:
            try:
                cab = json.loads(fh.readline())
            except ValueError:
                continue
        if not str(cab.get("experiment") or "").startswith("a2_") or float(cab.get("speed_band_kmh") or 0.0) < banda_min:
            continue
        r = resumen_sesion(log)
        if r:
            out.append(r)
    return out


def cargar_lineas(mapa: Mapa, dir_pista: Path) -> Dict[str, np.ndarray]:
    out = {}
    for nombre, arch in LINEAS.items():
        if arch is None:
            out[nombre] = np.zeros(mapa.n_puntos)
        elif (dir_pista / arch).is_file():
            out[nombre] = np.load(dir_pista / arch)
    return out


def figura_planta(mapa: Mapa, lo_c: np.ndarray, hi_c: np.ndarray, lineas: Dict[str, np.ndarray]) -> str:
    fig, ax = plt.subplots(figsize=(9, 7.8))
    for lado in (lo_c, hi_c):
        x, z = lo.geometria(mapa, lado)
        ax.plot(x, z, color="#c33", lw=0.5, alpha=0.6)
    ax.plot([], [], color="#c33", lw=0.8, label="límite del centro del coche (pasillo estricto, margen 0,6 m)")
    for nombre, n in lineas.items():
        x, z = lo.geometria(mapa, n)
        ax.plot(x, z, color=COLORES[nombre], lw=0.9, label=nombre)
    for nombre, (a, b) in ZONAS.items():
        idx = (mapa.s >= a) & (mapa.s <= b)
        ax.plot(mapa.x[idx], mapa.z[idx], color="#e0b000", lw=4.0, alpha=0.35, solid_capstyle="round")
    ax.plot([], [], color="#e0b000", lw=4.0, alpha=0.35, label="zonas problemáticas (V58-V61)")
    ax.set_aspect("equal")
    ax.legend(loc="best", fontsize=8)
    ax.set_title("Planta: pasillo, líneas y zonas problemáticas")
    return _png(fig)


def figura_n(mapa: Mapa, lo_c: np.ndarray, hi_c: np.ndarray, lineas: Dict[str, np.ndarray]) -> str:
    fig, ax = plt.subplots(figsize=(12, 4.4))
    ax.fill_between(mapa.s, lo_c, hi_c, color="#e8f3e8", label="pasillo del centro")
    for nombre, n in lineas.items():
        ax.plot(mapa.s, n, color=COLORES[nombre], lw=0.9, label=nombre)
    for a, b in ZONAS.values():
        ax.axvspan(a, b, color="#e0b000", alpha=0.18)
    ax.set_xlabel("s: distancia de vuelta (m)")
    ax.set_ylabel("n del centro del coche (m, + = derecha)")
    ax.legend(loc="upper right", fontsize=8, ncol=3)
    ax.set_title("Desplazamiento lateral (las bandas amarillas son las zonas problemáticas)")
    return _png(fig)


def figura_curvatura(mapa: Mapa, lineas: Dict[str, np.ndarray]) -> str:
    fig, ax = plt.subplots(figsize=(12, 4.4))
    for nombre, n in lineas.items():
        dk, _ = lo.perfil_curvatura(mapa, n)
        ax.plot(mapa.s, dk * 1e6, color=COLORES[nombre], lw=0.9, label=nombre)
    for a, b in ZONAS.values():
        ax.axvspan(a, b, color="#e0b000", alpha=0.18)
    ax.set_xlabel("s: distancia de vuelta (m)")
    ax.set_ylabel("máx. móvil (100 m) de |Δκ| por metro (·10⁻⁶)")
    ax.legend(loc="upper right", fontsize=8, ncol=3)
    ax.set_title("Variación de curvatura que ve el teacher: dónde serpentea cada línea")
    return _png(fig)


def figura_velocidad(mapa: Mapa, coche, lineas: Dict[str, np.ndarray]) -> str:
    fig, ax = plt.subplots(figsize=(12, 4.2))
    for nombre, n in lineas.items():
        if nombre in ("a1mu9", "a1mu9c15"):
            continue
        v, _, _ = lo.perfil_en_s(mapa, n, coche)
        ax.plot(mapa.s, v * 3.6, color=COLORES[nombre], lw=0.9, label=nombre)
    ax.set_xlabel("s: distancia de vuelta (m)")
    ax.set_ylabel("velocidad prevista (km/h)")
    ax.legend(loc="lower right", fontsize=8)
    ax.set_title(f"Velocidad prevista por el solver (coche del teacher, μ 9, tope {TOPE_SOLVER_KMH:g} km/h)")
    return _png(fig)


def tabla_lineas(mapa: Mapa, coche, lineas: Dict[str, np.ndarray]) -> str:
    base = lo.tiempo_vuelta(mapa, np.zeros(mapa.n_puntos), coche)
    filas = []
    for nombre, n in lineas.items():
        t = lo.tiempo_vuelta(mapa, n, coche)
        track = lo.track_de_n(mapa, n)[0]
        dk, cambios = lo.perfil_curvatura(mapa, n)
        zonas = "".join(f"<td>{dk[(mapa.s >= a) & (mapa.s <= b)].max() * 1e6:.0f} · {int(cambios[(mapa.s >= a) & (mapa.s <= b)].max())}</td>" for a, b in ZONAS.values())
        filas.append(f"<tr><td>{nombre}</td><td>{t:.2f}</td><td>{t - base:+.2f} ({100 * (t / base - 1):+.2f} %)</td><td>{track.length_m:.1f}</td>{zonas}</tr>")
    cab = "".join(f"<th>{html.escape(z)}</th>" for z in ZONAS)
    return (f"<table><tr><th>línea</th><th>previsto (s)</th><th>frente a la suavizada</th><th>longitud (m)</th>{cab}</tr>{''.join(filas)}</table>"
            "<p class=\"n\">Las columnas de zona: máx. de |Δκ| por metro (·10⁻⁶) · cambios de signo de κ en una ventana de 100 m, con la curvatura del teacher.</p>")


def tabla_sesiones(ses: Sequence[Dict]) -> str:
    if not ses:
        return "<p>No hay logs A2.0 a esa banda.</p>"
    filas = []
    for r in ses:
        fallo = lambda v: ' class="mal"' if v > CRITERIO_CTE_M else ""  # noqa: E731
        zonas = "".join(f"<td{fallo(v)}>{v:.2f}</td>" for v in r["zonas"].values())
        mal_fuera = ' class="mal"' if r["fuera"] else ""
        filas.append(f"<tr><td>{r['log']}</td><td>{html.escape(r['linea'])}</td><td>{r['banda']:g}</td><td>{r['vuelta_s']:.1f}</td><td{fallo(r['cte_max'])}>{r['cte_max']:.2f}</td>{zonas}"
                     f"<td{mal_fuera}>{r['fuera']}</td><td>{html.escape(r['git'])}</td><td class=\"exp\">{html.escape(r['experimento'])}</td></tr>")
    cab = "".join(f"<th>{html.escape(z)}</th>" for z in ZONAS)
    return (f"<table><tr><th>log</th><th>línea</th><th>banda</th><th>mejor vuelta (s)</th><th>|CTE| máx.</th>{cab}<th>ticks con ruedas fuera</th><th>commit</th><th>experimento</th></tr>"
            f"{''.join(filas)}</table><p class=\"n\">En rojo: |CTE| por encima de {CRITERIO_CTE_M:g} m o algún tick con ruedas fuera. |CTE| máx. en m, en las vueltas completas lanzadas (índice ≥ 2).</p>")


def generar(dir_pista: Path, salida: Path, banda_min: float = 100.0) -> Path:
    mapa = Mapa.cargar(dir_pista / "mapa.json")
    obs = Observaciones.de_dict(json.loads((dir_pista / "observaciones_logs.json").read_text(encoding="utf-8")))
    lo_c, hi_c = lo.pasillo_centro(mapa, obs, 0.6, incluir_eje=False)
    coche = lo.coche_a1(9.0, tope_kmh=TOPE_SOLVER_KMH)
    lineas = cargar_lineas(mapa, dir_pista)
    ses = sesiones(banda_min)
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Líneas del teacher en {html.escape(mapa.nombre)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1250px;margin:24px auto;padding:0 16px;color:#222}}table{{border-collapse:collapse;font-size:.88em}}
td,th{{border:1px solid #ccc;padding:3px 8px;text-align:left}}img{{max-width:100%}}h2{{margin-top:28px}}.n{{color:#666;font-size:.9em}}.mal{{background:#f9d6d6}}.exp{{font-size:.8em;color:#555}}</style></head><body>
<h1>Líneas del teacher en {html.escape(mapa.nombre)}</h1>
<p class="n">Generado por <code>circuito_virtual/src/informe_lineas_teacher.py</code>. Los tiempos previstos son del solver (<code>perfil_velocidad.solve</code>, coche del teacher: tablas de A1, μ 9, tope {TOPE_SOLVER_KMH:g} km/h):
dicen cuánto gana cada línea con el mismo coche. Qué pasó en el juego con cada una, en <code>circuito_virtual/docs/DECISIONES.md</code> (V15-V62).</p>
<h2>Líneas</h2>{tabla_lineas(mapa, coche, lineas)}
<h2>Sesiones A2.0 de vuelta completa (banda ≥ {banda_min:g} km/h)</h2>{tabla_sesiones(ses)}
<h2>Planta</h2><img src="{figura_planta(mapa, lo_c, hi_c, lineas)}" alt="planta">
<h2>Desplazamiento lateral</h2><img src="{figura_n(mapa, lo_c, hi_c, lineas)}" alt="n">
<h2>Variación de curvatura</h2><img src="{figura_curvatura(mapa, lineas)}" alt="curvatura">
<h2>Velocidad prevista</h2><img src="{figura_velocidad(mapa, coche, lineas)}" alt="velocidad">
</body></html>"""
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(doc, encoding="utf-8")
    return salida


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--dir", type=Path, default=lo.PISTA)
    ap.add_argument("--salida", type=Path, default=None)
    ap.add_argument("--banda-min", type=float, default=100.0)
    args = ap.parse_args(argv)
    print(generar(args.dir, args.salida or args.dir / "informes" / "informe_lineas_teacher.html", args.banda_min))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
