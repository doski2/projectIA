"""Métricas del seguimiento de la línea curva a curva (V107-V108): la ficha con la que se juzgan las sesiones del volante.

Para cada vuelta y cada curva del catálogo (`curvas.json`, V70) se mide dónde va el coche frente a la línea que sigue:

- en cuatro puntos (**entrada** = inicio de la curva, **vértice**, **vértice + 20 m** y **salida** = fin de la curva): posición lateral del coche y de la línea
  (n del mapa, + derecha), **fracción de pista** de cada uno medida **desde el borde interior** (0 = borde interior, 1 = exterior), el **desvío hacia dentro**
  (coche − línea, + = más por dentro de lo que pide la línea), velocidad, volante (+ = hacia el lado de la curva), gas, freno, |deriva| y |lateral|;
- el **pico de desvío hacia dentro** y el **pico hacia fuera** entre el inicio de la curva y `EXTRA_SALIDA_M` después de su fin, y a cuántos metros del vértice caen;
- la **media de |desvío|** dentro de la curva.

Por vuelta, además: tiempo, media de |desvío| en todas las curvas (V107: 0,654 m con la d11), ticks con rueda fuera y la temperatura media de cada goma
(y de sus zonas izquierda / centro / derecha si el log las trae).

La posición del coche sale de `vehicle.position` proyectada en el mapa de la pista (`mapa.json`), no del `signed_cte` del log: así el desvío es el mismo
para cualquier línea y la fracción de pista usa los bordes del pasillo (`observaciones_pasillo_d11.json` si existe, si no `observaciones_logs.json`).
Los bordes son la n de la rueda en el límite de la superficie de carrera; la fracción es la del centro del coche entre esos dos bordes.

**Comparación:** con `--contra` (logs o un JSON guardado con `--json`) se agrega la referencia (media y desviación típica entre vueltas por curva) y se
imprime la diferencia de la sesión. Si se pide `--vueltas`, la referencia usa por defecto las mismas vueltas (misma vuelta de cada sesión, V108).

Uso:
    python experimental/common/metricas_volante.py <log> [--vueltas 4-6] [--contra D.jsonl --contra E.jsonl --vueltas-contra 3-8] [--json fichas.json]
    python experimental/common/metricas_volante.py <log> --contra referencia_def.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "PCARS2-AI" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from circuito_virtual.src.curvas import Catalogo, Curva  # noqa: E402
from circuito_virtual.src.mapa import Mapa  # noqa: E402
from pcars2_surface import OFF_TRACK_TERRAIN_IDS  # noqa: E402

EXTRA_SALIDA_M = 20.0  # los picos de V107 caen hasta 59 m después del vértice, a veces pegados al fin de la curva
VERTICE_MAS_M = 20.0
COBERTURA = 0.9  # vuelta completa: recorre ≥ 90 % de la pista
PUNTOS = ("entrada", "vertice", "v20", "salida")
NOMBRE_PUNTO = {"entrada": "entrada", "vertice": "vértice", "v20": "vértice+20", "salida": "salida"}
MAGNITUDES_PUNTO = ("frac_coche", "frac_linea", "dentro", "v", "volante", "gas", "freno", "deriva", "lateral")
RUEDAS = ("DI", "DD", "TI", "TD")  # orden del UDP: FL, FR, RL, RR


# ---- carga ---------------------------------------------------------------------------------------------------------

@dataclass
class Sesion:
    nombre: str
    cabecera: Dict
    lap: np.ndarray
    t: np.ndarray
    d: np.ndarray  # lap_distance
    x: np.ndarray
    z: np.ndarray
    v: np.ndarray
    volante: np.ndarray
    gas: np.ndarray
    freno: np.ndarray
    deriva: np.ndarray  # grados, con signo
    lateral: np.ndarray  # m/s², con signo (NaN si el log no la trae)
    fuera: np.ndarray  # 1 si alguna rueda pisa terreno distinto de 0 (incluye piano y franjas)
    fuera_pista: np.ndarray  # 1 si alguna rueda pisa hierba, grava... (`OFF_TRACK_TERRAIN_IDS`), sin piano ni franjas
    gomas: np.ndarray  # (n, 4) °C
    zonas: Dict[str, np.ndarray]  # "izq" / "centro" / "dcha" → (n, 4) °C, NaN donde no hay dato


def _deriva(lv) -> float:
    if not lv or -float(lv[2]) <= 5.0:
        return 0.0
    return math.degrees(math.atan2(float(lv[0]), -float(lv[2])))


def sesion_de_ticks(ticks: Sequence[dict], cabecera: Optional[Dict] = None, nombre: str = "") -> Sesion:
    n = len(ticks)
    col = {k: np.full(n, np.nan) for k in ("lap", "t", "d", "x", "z", "v", "volante", "gas", "freno", "deriva", "lateral", "fuera", "fuera_pista")}
    gomas = np.full((n, 4), np.nan)
    zonas = {k: np.full((n, 4), np.nan) for k in ("izq", "centro", "dcha")}
    for i, t in enumerate(ticks):
        veh = t.get("vehicle") or {}
        pos = veh.get("position") or (np.nan, np.nan, np.nan)
        la = veh.get("local_accel")
        col["lap"][i], col["t"][i], col["d"][i] = t["lap"], t["t_s"], t["lap_distance"]
        col["x"][i], col["z"][i] = pos[0], pos[2]
        col["v"][i], col["volante"][i], col["gas"][i], col["freno"][i] = t["speed_kmh"], t["steering"], t["throttle"], t["brake"]
        col["deriva"][i] = _deriva(veh.get("local_velocity"))
        col["lateral"][i] = float(la[0]) if la and len(la) >= 3 else np.nan
        terreno = (veh.get("terrain") or [])[:4]
        col["fuera"][i] = 1.0 if any(x for x in terreno) else 0.0
        col["fuera_pista"][i] = 1.0 if any(x in OFF_TRACK_TERRAIN_IDS for x in terreno) else 0.0
        tt = veh.get("tyre_temp")
        if tt and len(tt) == 4:
            gomas[i] = tt
        for k, campo in (("izq", "tyre_left_c"), ("centro", "tyre_center_c"), ("dcha", "tyre_right_c")):
            z = veh.get(campo)
            if z and len(z) == 4:
                zonas[k][i] = [x if x else np.nan for x in z]
    return Sesion(nombre, cabecera or {}, col["lap"].astype(int) if n else np.zeros(0, int), col["t"], col["d"], col["x"], col["z"], col["v"], col["volante"],
                  col["gas"], col["freno"], col["deriva"], col["lateral"], col["fuera"], col["fuera_pista"], gomas, zonas)


def cargar_log(ruta: Path) -> Sesion:
    cabecera: Dict = {}
    ticks: List[dict] = []
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            if '"type": "tick"' in linea:
                ticks.append(json.loads(linea))
            elif not cabecera and '"type": "session"' in linea:
                cabecera = json.loads(linea)
    return sesion_de_ticks(ticks, cabecera, Path(ruta).name)


# ---- geometría -----------------------------------------------------------------------------------------------------

@dataclass
class Pista:
    mapa: Mapa
    catalogo: Catalogo
    borde_izq: np.ndarray  # n del borde izquierdo por punto del mapa (< 0)
    borde_dcha: np.ndarray


def cargar_pista(pista_dir: Path, observaciones: Optional[Path] = None) -> Pista:
    mapa = Mapa.cargar(pista_dir / "mapa.json")
    catalogo = Catalogo.cargar(pista_dir / "curvas.json")
    if observaciones is None:
        observaciones = next((p for p in (pista_dir / "observaciones_pasillo_d11.json", pista_dir / "observaciones_logs.json") if p.is_file()), None)
    if observaciones is not None:
        obs = json.loads(Path(observaciones).read_text(encoding="utf-8"))
        nan = lambda a: np.array([np.nan if v is None else v for v in a], dtype=float)  # noqa: E731
        izq, dcha = nan(obs["izq_dentro"]), nan(obs["dcha_dentro"])
    else:
        izq, dcha = mapa.borde_izq, mapa.borde_dcha
    return Pista(mapa, catalogo, izq, dcha)


def n_de_linea(mapa: Mapa, referencia: Dict) -> np.ndarray:
    """n de una línea (JSON de `ReferenceLine`) en cada punto del eje del mapa."""
    pts = referencia["points"]
    pos = np.array([p["pos"] for p in pts], dtype=float)
    d = np.array([p["d"] for p in pts], dtype=float)
    s, n = mapa.xz_a_sn(pos[:, 0], pos[:, 2], s_hint=d)
    orden = np.argsort(s)
    s, n = s[orden], n[orden]
    L = mapa.longitud_m
    return np.interp(mapa.s, np.concatenate([s - L, s, s + L]), np.concatenate([n, n, n]))


def ruta_referencia(cabecera: Dict) -> Optional[Path]:
    ref = cabecera.get("reference")
    if not ref:
        return None
    p = Path(ref)
    if p.is_file():
        return p
    # el log guarda la ruta absoluta de la máquina donde se grabó: probar la misma ruta relativa al repo
    partes = Path(str(ref).replace("\\", "/")).parts
    for i in range(len(partes)):
        cand = REPO.joinpath(*partes[i:])
        if cand.is_file():
            return cand
    return None


# ---- fichas --------------------------------------------------------------------------------------------------------

def _frac(n: float, izq: float, dcha: float, sentido: str) -> float:
    """Fracción de pista desde el borde interior (izquierda en curva a izquierdas)."""
    ancho = dcha - izq
    if not np.isfinite(ancho) or ancho <= 0.5:
        return float("nan")
    return float((n - izq) / ancho) if sentido == "izq" else float((dcha - n) / ancho)


def _r(x: float, nd: int = 3) -> Optional[float]:
    return round(float(x), nd) if x is not None and np.isfinite(x) else None


def vueltas_completas(ses: Sesion, largo: float) -> List[int]:
    out = []
    for lap in sorted(set(ses.lap.tolist())):
        m = ses.lap == lap
        d = ses.d[m]
        if m.sum() >= 100 and np.nanmax(d) - np.nanmin(d) >= COBERTURA * largo:
            out.append(int(lap))
    return out


def fichas(ses: Sesion, pista: Pista, n_linea: np.ndarray, vueltas: Optional[Sequence[int]] = None) -> Dict[int, Dict]:
    """{vuelta: {"tiempo_s", "cte_curvas", "fuera", "gomas": {...}, "curvas": {"C1": ficha, ...}}} de las vueltas completas pedidas."""
    mapa, cat = pista.mapa, pista.catalogo
    completas = vueltas_completas(ses, mapa.longitud_m)
    pedidas = [v for v in completas if vueltas is None or v in vueltas]
    out: Dict[int, Dict] = {}
    ok = np.isfinite(ses.x) & np.isfinite(ses.z)
    s_all = np.full(len(ses.x), np.nan)
    n_all = np.full(len(ses.x), np.nan)
    if ok.any():
        s_all[ok], n_all[ok] = mapa.xz_a_sn(ses.x[ok], ses.z[ok], s_hint=ses.d[ok])
    nl_all = mapa.interpola(n_linea, np.nan_to_num(s_all))
    desv_all = n_all - nl_all
    for lap in pedidas:
        m = (ses.lap == lap) & ok
        idx = np.flatnonzero(m)
        s, desv = s_all[idx], desv_all[idx]
        # los ticks de la vuelta que caen tras la meta (s pequeño al final) o antes (s grande al principio) se descartan para que s sea creciente
        mitad = mapa.longitud_m / 2
        validos = ~(((np.arange(len(s)) < len(s) / 2) & (s > mitad)) | ((np.arange(len(s)) >= len(s) / 2) & (s < mitad)))
        idx, s, desv = idx[validos], s[validos], desv[validos]
        orden = np.argsort(s, kind="stable")
        idx, s, desv = idx[orden], s[orden], desv[orden]
        en_curva = np.zeros(len(s), bool)
        curvas: Dict[str, Dict] = {}
        for c in cat.curvas:
            curvas[f"C{c.id}"] = _ficha_curva(c, ses, pista, n_linea, idx, s, desv, en_curva)
        tk = np.flatnonzero(ses.lap == lap)
        gom = np.nanmean(ses.gomas[tk], axis=0) if np.isfinite(ses.gomas[tk]).any() else np.full(4, np.nan)
        zonas = {}
        for k, arr in ses.zonas.items():
            if np.isfinite(arr[tk]).any():
                with warnings.catch_warnings():  # una rueda sin ningún dato da «Mean of empty slice»
                    warnings.simplefilter("ignore", RuntimeWarning)
                    zonas[k] = [_r(x, 1) for x in np.nanmean(arr[tk], axis=0)]
        out[lap] = {
            "tiempo_s": _r(float(ses.t[tk[-1]] - ses.t[tk[0]])),
            "cte_curvas": _r(float(np.mean(np.abs(desv[en_curva]))) if en_curva.any() else float("nan")),
            "cte_vuelta": _r(float(np.mean(np.abs(desv)))) if len(desv) else None,
            "fuera": int(ses.fuera[tk].sum()),
            "fuera_pista": int(ses.fuera_pista[tk].sum()),
            "gomas": {r: _r(g, 1) for r, g in zip(RUEDAS, gom)},
            "gomas_zonas": zonas,
            "curvas": curvas,
        }
    return out


def _ficha_curva(c: Curva, ses: Sesion, pista: Pista, n_linea: np.ndarray, idx: np.ndarray, s: np.ndarray, desv: np.ndarray, en_curva: np.ndarray) -> Dict:
    mapa = pista.mapa
    signo = -1.0 if c.sentido == "izq" else 1.0  # n + es la derecha: hacia dentro en una curva a derechas es n +
    s_fin = c.s_fin if c.s_fin >= c.s_ini else c.s_fin + mapa.longitud_m
    dentro_curva = (s >= c.s_ini) & (s <= s_fin)
    en_curva |= dentro_curva
    ventana = (s >= c.s_ini) & (s <= s_fin + EXTRA_SALIDA_M)
    ficha: Dict = {}
    if ventana.sum() < 3:
        return {"sin_datos": True}
    dentro = signo * desv
    k_in = int(np.argmax(np.where(ventana, dentro, -np.inf)))
    k_out = int(np.argmin(np.where(ventana, dentro, np.inf)))
    ficha["pico_dentro"] = _r(dentro[k_in])
    ficha["pico_dentro_m"] = _r(s[k_in] - c.s_apice, 0)
    ficha["pico_fuera"] = _r(-dentro[k_out])
    ficha["pico_fuera_m"] = _r(s[k_out] - c.s_apice, 0)
    ficha["cte_media"] = _r(float(np.mean(np.abs(desv[dentro_curva])))) if dentro_curva.any() else None
    ficha["fuera_pista"] = int(ses.fuera_pista[idx[ventana]].sum())
    s_pts = {"entrada": c.s_ini, "vertice": c.s_apice, "v20": c.s_apice + VERTICE_MAS_M, "salida": s_fin}
    sentido_volante = signo  # volante + = a la derecha (mismo convenio que n)
    for nombre, sp in s_pts.items():
        def en(arr: np.ndarray) -> float:
            return float(np.interp(sp, s, arr))
        n_l = float(mapa.interpola(n_linea, sp))
        d_l = en(desv)
        n_c = n_l + d_l
        izq, dcha = float(mapa.interpola(pista.borde_izq, sp)), float(mapa.interpola(pista.borde_dcha, sp))
        lat = ses.lateral[idx]
        ficha[nombre] = {
            "n_coche": _r(n_c), "n_linea": _r(n_l),
            "frac_coche": _r(_frac(n_c, izq, dcha, c.sentido)), "frac_linea": _r(_frac(n_l, izq, dcha, c.sentido)),
            "dentro": _r(signo * d_l),
            "v": _r(en(ses.v[idx]), 1), "volante": _r(sentido_volante * en(ses.volante[idx])), "gas": _r(en(ses.gas[idx]), 2),
            "freno": _r(en(ses.freno[idx]), 2), "deriva": _r(abs(en(ses.deriva[idx])), 2),
            "lateral": _r(abs(en(lat)), 2) if np.isfinite(lat).all() else None,
        }
    return ficha


# ---- agregación y comparación --------------------------------------------------------------------------------------

def _escalares(ficha_curva: Dict) -> Dict[str, float]:
    """Aplana la ficha de una curva: {"pico_dentro": x, "vertice.frac_coche": y, ...}."""
    out: Dict[str, float] = {}
    for k, v in ficha_curva.items():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                if v2 is not None:
                    out[f"{k}.{k2}"] = float(v2)
        elif isinstance(v, (int, float)) and not isinstance(v, bool) and v is not None:
            out[k] = float(v)
    return out


def agregar(por_vuelta: Sequence[Dict[int, Dict]], vueltas: Optional[Sequence[int]] = None) -> Dict:
    """Media y desviación típica entre vueltas: {"vueltas": n, "vuelta": {métrica: (media, dt)}, "curvas": {"C1": {métrica: (media, dt)}}}."""
    vlt: Dict[str, List[float]] = {}
    cur: Dict[str, Dict[str, List[float]]] = {}
    n = 0
    for fv in por_vuelta:
        for lap, f in fv.items():
            if vueltas is not None and lap not in vueltas:
                continue
            n += 1
            for k in ("tiempo_s", "cte_curvas", "cte_vuelta", "fuera", "fuera_pista"):
                if f.get(k) is not None:
                    vlt.setdefault(k, []).append(float(f[k]))
            for r, g in (f.get("gomas") or {}).items():
                if g is not None:
                    vlt.setdefault(f"goma_{r}", []).append(float(g))
            for cid, fc in f["curvas"].items():
                for k, x in _escalares(fc).items():
                    cur.setdefault(cid, {}).setdefault(k, []).append(x)

    def md(xs: List[float]) -> Tuple[float, float]:
        a = np.asarray(xs, float)
        return float(a.mean()), float(a.std(ddof=1)) if len(a) > 1 else 0.0

    return {"vueltas": n, "vuelta": {k: md(x) for k, x in vlt.items()}, "curvas": {c: {k: md(x) for k, x in m.items()} for c, m in cur.items()}}


# ---- texto ---------------------------------------------------------------------------------------------------------

def _f(x, nd=2, signo=False) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "-"
    return f"{x:+.{nd}f}" if signo else f"{x:.{nd}f}"


def tiempo_txt(s: Optional[float]) -> str:
    if s is None:
        return "-"
    m = int(s // 60)
    return f"{m}:{s - 60 * m:06.3f}"


def tabla_vueltas(fv: Dict[int, Dict]) -> str:
    filas = ["vuelta   tiempo     |desv| curvas  |desv| vuelta  fuera (hierba)   gomas DI/DD/TI/TD (°C)"]
    for lap, f in sorted(fv.items()):
        g = f["gomas"]
        filas.append(f"V{lap:<6d} {tiempo_txt(f['tiempo_s']):>9}  {_f(f['cte_curvas'], 3):>13}  {_f(f['cte_vuelta'], 3):>13}  {f['fuera']:>5d} ({f['fuera_pista']:>4d})   "
                     + "/".join(_f(g.get(r), 0) for r in RUEDAS))
    return "\n".join(filas)


def tabla_curvas(agr: Dict, titulo: str) -> str:
    """Una fila por curva con la media de las vueltas agregadas."""
    filas = [titulo,
             "curva  pico dentro (m @ m del vértice)  pico fuera     |desv|   frac. salida coche/línea   dentro: entrada vértice +20 salida   v vértice  volante vértice  hierba"]
    for cid, m in agr["curvas"].items():
        g = lambda k: m.get(k, (None, None))[0]  # noqa: E731
        filas.append(f"{cid:<6} {_f(g('pico_dentro'), 2, True):>6} @ {_f(g('pico_dentro_m'), 0, True):>4}"
                     f"{'':>20}{_f(g('pico_fuera'), 2):>5} @ {_f(g('pico_fuera_m'), 0, True):>4}  {_f(g('cte_media'), 2):>6}"
                     f"   {_f(g('salida.frac_coche'), 2):>8} / {_f(g('salida.frac_linea'), 2):<8}"
                     f"     {_f(g('entrada.dentro'), 2, True):>6} {_f(g('vertice.dentro'), 2, True):>6} {_f(g('v20.dentro'), 2, True):>6} {_f(g('salida.dentro'), 2, True):>6}"
                     f"   {_f(g('vertice.v'), 0):>8}  {_f(g('vertice.volante'), 3):>8}  {_f(g('fuera_pista'), 1):>6}")
    return "\n".join(filas)


# (clave, título, decimales, cambio mínimo para marcar «*»): 0,1 m es lo que se quiere poder medir (V108 pide 0,3 m), 1 km/h, 5 m de posición del pico...
METRICAS_COMPARAR = (("pico_dentro", "pico dentro", 2, 0.1), ("pico_dentro_m", "a m del vértice", 0, 5.0), ("pico_fuera", "pico fuera", 2, 0.1),
                     ("cte_media", "|desv| media", 2, 0.05), ("salida.frac_coche", "frac. salida", 2, 0.02), ("vertice.dentro", "dentro vértice", 2, 0.1),
                     ("salida.dentro", "dentro salida", 2, 0.1), ("vertice.v", "v vértice", 1, 1.0), ("salida.v", "v salida", 1, 1.0),
                     ("vertice.deriva", "deriva vértice", 2, 0.3), ("fuera_pista", "ticks hierba", 1, 2.0))


def marca(delta: float, dt_ref: float, minimo: float) -> bool:
    """Cambio que se sale del ruido entre vueltas de la referencia (> 2 dt) y que además importa (> mínimo de la métrica)."""
    return abs(delta) > 2 * dt_ref and abs(delta) > minimo


def tabla_comparacion(ses: Dict, ref: Dict) -> str:
    """Δ = sesión − referencia por curva; entre paréntesis la desviación típica de la referencia entre vueltas. «*» si |Δ| > 2 dt y por encima del mínimo de la métrica."""
    filas = [f"Sesión ({ses['vueltas']} vueltas) frente a la referencia ({ref['vueltas']} vueltas): Δ (dt de la referencia); "
             "* = |Δ| > 2 dt y mayor que el mínimo de la métrica (0,1 m en desvíos, 0,02 en fracción, 1 km/h, 5 m, 0,3°, 2 ticks)"]
    for k, nombre in (("tiempo_s", "tiempo (s)"), ("cte_curvas", "|desv| en curvas (m)"), ("cte_vuelta", "|desv| vuelta (m)"), ("fuera", "ticks fuera"),
                         ("fuera_pista", "ticks en hierba")):
        a, b = ses["vuelta"].get(k), ref["vuelta"].get(k)
        if a is not None and b is not None:
            filas.append(f"  {nombre:<22} {a[0]:9.3f} frente a {b[0]:9.3f}  Δ {a[0] - b[0]:+.3f} ({b[1]:.3f})")
    gom = [f"{r} {ses['vuelta'][f'goma_{r}'][0]:.0f}/{ref['vuelta'][f'goma_{r}'][0]:.0f}" for r in RUEDAS
           if f"goma_{r}" in ses["vuelta"] and f"goma_{r}" in ref["vuelta"]]
    if gom:
        filas.append("  gomas sesión/ref. (°C)  " + "  ".join(gom))
    filas.append("")
    filas.append("curva  " + "".join(f"{n:>18}" for _, n, _, _ in METRICAS_COMPARAR))
    for cid in ref["curvas"]:
        mc, rc = ses["curvas"].get(cid, {}), ref["curvas"][cid]
        celdas = []
        for k, _, nd, minimo in METRICAS_COMPARAR:
            if k in mc and k in rc:
                d, dt = mc[k][0] - rc[k][0], rc[k][1]
                celdas.append(f"{d:+.{nd}f} ({dt:.{nd}f}){'*' if marca(d, dt, minimo) else ' '}")
            else:
                celdas.append("-")
        filas.append(f"{cid:<6} " + "".join(f"{c:>18}" for c in celdas))
    return "\n".join(filas)


# ---- línea de órdenes ----------------------------------------------------------------------------------------------

def parse_vueltas(txt: Optional[str]) -> Optional[List[int]]:
    """«4-6», «3,5,7» o «3-5,8»."""
    if not txt:
        return None
    out: List[int] = []
    for parte in txt.split(","):
        parte = parte.strip()
        if "-" in parte:
            a, b = parte.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif parte:
            out.append(int(parte))
    return out


def analizar_log(ruta: Path, pista_dir: Optional[Path], observaciones: Optional[Path], linea: Optional[Path], vueltas: Optional[Sequence[int]]) -> Tuple[Dict[int, Dict], Dict]:
    ses = cargar_log(ruta)
    pista_dir = pista_dir or (REPO / "circuito_virtual" / "pistas" / str(ses.cabecera.get("track") or "sugo_gp").lower())
    pista = cargar_pista(pista_dir, observaciones)
    ref_path = linea or ruta_referencia(ses.cabecera)
    if ref_path is None:
        raise SystemExit(f"{ruta.name}: la cabecera no dice qué línea seguía; pásala con --linea")
    n_l = n_de_linea(pista.mapa, json.loads(Path(ref_path).read_text(encoding="utf-8")))
    if vueltas is None:  # por defecto, todas las completas menos la primera (salida parada)
        completas = vueltas_completas(ses, pista.mapa.longitud_m)
        vueltas = completas[1:] if len(completas) > 1 else completas
    fv = fichas(ses, pista, n_l, vueltas)
    meta = {"log": ruta.name, "linea": Path(ref_path).name, "experimento": ses.cabecera.get("experiment"), "git": ses.cabecera.get("git"),
            "pista": pista_dir.name, "vueltas": sorted(fv)}
    return fv, meta


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("log", type=Path)
    ap.add_argument("--vueltas", help="vueltas a medir: «4-6», «3,5,7»; por defecto todas las completas menos la primera")
    ap.add_argument("--contra", action="append", type=Path, default=[], help="log(s) de referencia o un JSON guardado con --json (se puede repetir)")
    ap.add_argument("--vueltas-contra", help="vueltas de la referencia; por defecto las mismas que --vueltas")
    ap.add_argument("--linea", type=Path, help="línea que seguía (por defecto la de la cabecera del log)")
    ap.add_argument("--pista", type=Path, help="carpeta de la pista (por defecto circuito_virtual/pistas/<track>)")
    ap.add_argument("--observaciones", type=Path, help="bordes de la pista (por defecto observaciones_pasillo_d11.json o observaciones_logs.json)")
    ap.add_argument("--json", type=Path, help="guarda las fichas por vuelta de la sesión y su agregado (sirve luego como --contra)")
    ap.add_argument("--guardar-contra", type=Path, help="guarda las fichas de la referencia (--contra) en un JSON, para usarlo luego como --contra")
    ap.add_argument("--por-vuelta", action="store_true", help="imprime también la tabla de curvas de cada vuelta")
    a = ap.parse_args(argv)

    vueltas = parse_vueltas(a.vueltas)
    fv, meta = analizar_log(a.log, a.pista, a.observaciones, a.linea, vueltas)
    agr = agregar([fv])
    print(f"== {a.log.name}  (línea {meta['linea']}, vueltas {meta['vueltas']})")
    print(tabla_vueltas(fv))
    print()
    print(tabla_curvas(agr, f"Media de {agr['vueltas']} vueltas (desvío + = coche más por dentro que la línea; fracción desde el borde interior)"))
    if a.por_vuelta:
        for lap, f in sorted(fv.items()):
            print()
            print(tabla_curvas(agregar([{lap: f}]), f"Vuelta {lap}"))

    if a.contra:
        vueltas_contra = parse_vueltas(a.vueltas_contra) if a.vueltas_contra else vueltas
        partes: List[Dict[int, Dict]] = []
        nombres = []
        guardadas: List[Dict] = []
        for ruta in a.contra:
            if ruta.suffix == ".json":
                d = json.loads(ruta.read_text(encoding="utf-8"))
                for parte in d["sesiones"]:
                    fvr = {int(k): v for k, v in parte["fichas"].items()}
                    fvr = {k: v for k, v in fvr.items() if vueltas_contra is None or k in vueltas_contra}
                    partes.append(fvr)
                    nombres.append(parte["meta"]["log"])
                    guardadas.append({"meta": parte["meta"], "fichas": {str(k): v for k, v in fvr.items()}})
            else:
                fvr, mr = analizar_log(ruta, a.pista, a.observaciones, None, vueltas_contra)
                partes.append(fvr)
                nombres.append(mr["log"])
                guardadas.append({"meta": mr, "fichas": {str(k): v for k, v in fvr.items()}})
        ref = agregar(partes)
        print()
        print("Referencia: " + ", ".join(nombres) + (f" (vueltas {vueltas_contra})" if vueltas_contra else ""))
        print(tabla_comparacion(agr, ref))
        if a.guardar_contra:
            a.guardar_contra.write_text(json.dumps({"sesiones": guardadas, "agregado": ref}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"\nreferencia -> {a.guardar_contra}")

    if a.json:
        a.json.write_text(json.dumps({"sesiones": [{"meta": meta, "fichas": {str(k): v for k, v in fv.items()}}], "agregado": agr}, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")
        print(f"\nfichas -> {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
