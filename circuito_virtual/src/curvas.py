"""Catálogo numerado de las curvas de una pista (V70): para poder decir «la curva 5» en un informe, un log o una conversación.

Las curvas se detectan en la curvatura del eje del mapa (`mapa.json`, κ > 0 = izquierda), no en la línea que sigue una sesión, así que la numeración es la misma para la suavizada, las óptimas y cualquier
sesión. Se numeran desde la línea de meta (s = 0) en el sentido de la marcha: C1, C2…

Detección: κ suavizada (media móvil de 15 m); picos de |κ| con altura ≥ 0,006 (R ≤ 167 m), prominencia ≥ 0,004 y separación ≥ 20 m; los picos consecutivos del mismo sentido a menos de 90 m con un valle que
no baja del 50 % del menor, o a menos de 45 m, se funden en una sola curva (apex = el pico mayor); los extremos de cada curva son donde |κ| baja de max(0,003, 30 % del pico), sin pasar del valle (mínimo de |κ|) entre ápices vecinos del mismo sentido.

Uso:
    python circuito_virtual/src/curvas.py [--pista circuito_virtual/pistas/sugo_gp] [--salida curvas.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

VENTANA_M = 15
ALTURA_MIN = 0.006  # 1/m
PROMINENCIA_MIN = 0.004
SEPARACION_MIN_M = 20
FUSION_DIST_M = 90
FUSION_VALLE = 0.5
FUSION_SIEMPRE_M = 45  # dos picos del mismo sentido a menos de esta distancia son el doble ápice de una misma curva
UMBRAL_BORDE = 0.003
FRACCION_BORDE = 0.30
MAX_SEMILARGO_M = 150
ESE_MAX_HUECO_M = 100  # dos curvas de sentido contrario a menos de esta distancia (fin a inicio) forman una ese


@dataclass
class Curva:
    id: int
    sentido: str  # "izq" o "dcha"
    s_ini: float
    s_apice: float
    s_fin: float
    radio_min_m: float
    largo_m: float
    tipo: str  # "radio decreciente", "radio creciente" o "radio constante"
    ese_con: Optional[int] = None  # id de la curva de sentido contrario con la que forma una ese


def _suavizar(x: np.ndarray, ventana: int = VENTANA_M) -> np.ndarray:
    h = ventana // 2
    return np.convolve(np.concatenate([x[-h:], x, x[:h]]), np.ones(2 * h + 1) / (2 * h + 1), mode="valid")


def _picos(a: np.ndarray) -> List[int]:
    n = len(a)
    cand = [i for i in range(n) if a[i] >= ALTURA_MIN and a[i] >= a[i - 1] and a[i] > a[(i + 1) % n]]

    def valle(i: int, paso: int) -> float:
        mn, j = a[i], i
        for _ in range(n):
            j = (j + paso) % n
            mn = min(mn, a[j])
            if a[j] > a[i]:
                return mn
        return 0.0

    con_prom = [i for i in cand if a[i] - max(valle(i, 1), valle(i, -1)) >= PROMINENCIA_MIN]
    con_prom.sort(key=lambda i: -a[i])
    keep: List[int] = []
    for i in con_prom:
        if all(min(abs(i - j), n - abs(i - j)) >= SEPARACION_MIN_M for j in keep):
            keep.append(i)
    return sorted(keep)


def detectar(kappa: np.ndarray, longitud_m: float) -> List[Curva]:
    """Curvas de una pista a partir de su curvatura por metro (κ > 0 = izquierda), numeradas desde s = 0."""
    ks = _suavizar(np.asarray(kappa, float))
    a = np.abs(ks)
    n = len(a)
    paso = longitud_m / n
    picos = _picos(a)
    if not picos:
        return []

    def valle_entre(i: int, j: int) -> float:
        if np.sign(ks[i]) != np.sign(ks[j]):
            return 0.0
        idx = [x % n for x in range(i, j + 1)]
        return float(min(a[x] for x in idx))

    grupos: List[List[int]] = [[picos[0]]]
    for p in picos[1:]:
        q = grupos[-1][-1]
        mismo = np.sign(ks[p]) == np.sign(ks[q])
        if mismo and ((p - q) * paso < FUSION_SIEMPRE_M or ((p - q) * paso < FUSION_DIST_M and valle_entre(q, p) >= FUSION_VALLE * min(a[p], a[q]))):
            grupos[-1].append(p)
        else:
            grupos.append([p])
    # el último grupo puede fundirse con el primero al cerrar el circuito
    if len(grupos) > 1:
        p, q = grupos[0][0], grupos[-1][-1]
        if np.sign(ks[p]) == np.sign(ks[q]) and ((p + n) - q) * paso < FUSION_DIST_M and valle_entre(q, p + n) >= FUSION_VALLE * min(a[p], a[q]):
            grupos[0] = grupos[-1] + grupos[0]
            grupos.pop()

    apices = [max(g, key=lambda x: a[x % n]) % n for g in grupos]
    orden = sorted(range(len(grupos)), key=lambda g: apices[g])
    grupos = [grupos[g] for g in orden]
    apices = [apices[g] for g in orden]
    # extremos: hacia fuera desde el primer/último pico del grupo, o la mitad del valle con la vecina
    curvas: List[Curva] = []
    m = len(grupos)

    def valle_idx(i: int, j: int) -> int:
        """Índice (circular) del mínimo de |κ| entre los ápices i y j (j después de i)."""
        if j < i:
            j += n
        return min(range(i, j + 1), key=lambda x: a[x % n]) % n

    limite_ini: Dict[int, int] = {}
    limite_fin: Dict[int, int] = {}
    for g in range(m):
        h = (g + 1) % m
        if m > 1 and np.sign(ks[apices[g]]) == np.sign(ks[apices[h]]):
            v = valle_idx(apices[g], apices[h])
            limite_fin[g] = v
            limite_ini[h] = v
    for g, grupo in enumerate(grupos):
        pico = a[apices[g]]
        corte = max(UMBRAL_BORDE, FRACCION_BORDE * pico)
        ini = grupo[0] % n
        fin = grupo[-1] % n
        i = ini
        for _ in range(int(MAX_SEMILARGO_M / paso)):
            j = (i - 1) % n
            if a[j] < corte or np.sign(ks[j]) != np.sign(ks[ini]) or i == limite_ini.get(g):
                break
            i = j
        j = fin
        for _ in range(int(MAX_SEMILARGO_M / paso)):
            k = (j + 1) % n
            if a[k] < corte or np.sign(ks[k]) != np.sign(ks[fin]) or j == limite_fin.get(g):
                break
            j = k
        s_ini, s_fin = i * paso, j * paso
        if s_fin < s_ini:
            s_fin += longitud_m
        largo = s_fin - s_ini
        tercio = max(1, int(largo / paso / 3))
        idx = [x % n for x in range(int(round(s_ini / paso)), int(round(s_fin / paso)) + 1)]
        ini_t, fin_t = float(np.mean(a[idx[:tercio]])), float(np.mean(a[idx[-tercio:]]))
        tipo = "radio decreciente" if fin_t > 1.25 * ini_t else ("radio creciente" if fin_t < 0.8 * ini_t else "radio constante")
        curvas.append(Curva(id=g + 1, sentido="izq" if ks[apices[g]] > 0 else "dcha", s_ini=round(s_ini, 1), s_apice=round(apices[g] * paso, 1), s_fin=round(s_fin % longitud_m if s_fin >= longitud_m else s_fin, 1),
                            radio_min_m=round(1.0 / float(a[apices[g]]), 1), largo_m=round(largo, 1), tipo=tipo))
    # eses: sentido contrario y poco hueco entre el fin de una y el inicio de la siguiente
    for g in range(m):
        h = (g + 1) % m
        hueco = (curvas[h].s_ini - curvas[g].s_fin) % longitud_m
        if curvas[g].sentido != curvas[h].sentido and hueco < ESE_MAX_HUECO_M and m > 1:
            curvas[g].ese_con = curvas[h].id
            curvas[h].ese_con = curvas[g].id
    return curvas


class Catalogo:
    """Curvas numeradas de una pista y utilidades para etiquetar una distancia de vuelta."""

    def __init__(self, curvas: Sequence[Curva], longitud_m: float, pista: str = ""):
        self.curvas = list(curvas)
        self.longitud_m = float(longitud_m)
        self.pista = pista

    @staticmethod
    def desde_mapa(mapa) -> "Catalogo":
        return Catalogo(detectar(mapa.kappa, mapa.longitud_m), mapa.longitud_m, getattr(mapa, "nombre", ""))

    def a_dict(self) -> Dict:
        return {"pista": self.pista, "longitud_m": self.longitud_m, "origen": "circuito_virtual/src/curvas.py (V70)", "curvas": [asdict(c) for c in self.curvas]}

    def guardar(self, ruta: Path) -> None:
        Path(ruta).write_text(json.dumps(self.a_dict(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    @staticmethod
    def cargar(ruta: Path) -> "Catalogo":
        d = json.loads(Path(ruta).read_text(encoding="utf-8"))
        return Catalogo([Curva(**c) for c in d["curvas"]], d["longitud_m"], d.get("pista", ""))

    def _dentro(self, c: Curva, s: float) -> bool:
        s = s % self.longitud_m
        if c.s_ini <= c.s_fin:
            return c.s_ini <= s <= c.s_fin
        return s >= c.s_ini or s <= c.s_fin

    def curva_en(self, s: float) -> Optional[Curva]:
        """La curva que contiene la distancia `s`, o None en recta."""
        for c in self.curvas:
            if self._dentro(c, s):
                return c
        return None

    def etiqueta(self, s: float) -> str:
        """«C5» dentro de una curva; «recta C4→C5» fuera de ellas."""
        c = self.curva_en(s)
        if c is not None:
            return f"C{c.id}"
        if not self.curvas:
            return "recta"
        s = s % self.longitud_m
        previa = max(self.curvas, key=lambda c: (s - c.s_fin) % self.longitud_m * -1)
        siguiente = min(self.curvas, key=lambda c: (c.s_ini - s) % self.longitud_m)
        return f"recta C{previa.id}→C{siguiente.id}"

    def etiqueta_tramo(self, s0: float, s1: float) -> str:
        """Curvas que toca el tramo [s0, s1]: «C5», «C4-C6» (si son varias) o, si es recta, «recta C4→C5»."""
        ids = []
        paso = max(1.0, (s1 - s0) / 40.0)
        s = s0
        while s <= s1 + 1e-9:
            c = self.curva_en(s)
            if c is not None and c.id not in ids:
                ids.append(c.id)
            s += paso
        if not ids:
            return self.etiqueta(s0)
        return f"C{ids[0]}" if len(ids) == 1 else f"C{ids[0]}-C{ids[-1]}"

    def proxima(self, s: float) -> Optional[Curva]:
        """La curva que contiene `s` o, si va en recta, la siguiente por delante (la que se está frenando)."""
        c = self.curva_en(s)
        if c is not None or not self.curvas:
            return c
        s = s % self.longitud_m
        return min(self.curvas, key=lambda c: (c.s_ini - s) % self.longitud_m)

    def tabla(self) -> str:
        filas = ["  id  sentido  inicio  ápice    fin  radio mín  largo  tipo                 ese con"]
        for c in self.curvas:
            filas.append(f"  C{c.id:<3d}{c.sentido:>6s}  {c.s_ini:6.0f} {c.s_apice:6.0f} {c.s_fin:6.0f}  {c.radio_min_m:7.0f} m {c.largo_m:5.0f}  {c.tipo:20s} {('C' + str(c.ese_con)) if c.ese_con else ''}")
        return "\n".join(filas)


def catalogo_de_pista(pista_dir: Path) -> Optional[Catalogo]:
    """`curvas.json` de la carpeta de la pista si existe."""
    ruta = Path(pista_dir) / "curvas.json"
    return Catalogo.cargar(ruta) if ruta.is_file() else None


def catalogo_de_log(ruta: Path) -> Optional[Catalogo]:
    """Catálogo de la pista de un log de sesión (la carpeta `pistas/<track en minúsculas>` según la cabecera del log), o None si no hay."""
    try:
        with open(ruta, encoding="utf-8") as fh:
            cabecera = json.loads(fh.readline())
    except (OSError, ValueError):
        return None
    pista = str(cabecera.get("track") or "").lower()
    return catalogo_de_pista(REPO / "circuito_virtual" / "pistas" / pista) if pista else None


def main(argv: Optional[list] = None) -> int:
    from circuito_virtual.src.mapa import Mapa  # noqa: PLC0415

    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--pista", type=Path, default=REPO / "circuito_virtual" / "pistas" / "sugo_gp")
    ap.add_argument("--salida", type=Path, default=None, help="por defecto <pista>/curvas.json")
    a = ap.parse_args(argv)
    mapa = Mapa.cargar(a.pista / "mapa.json")
    cat = Catalogo.desde_mapa(mapa)
    cat.pista = a.pista.name
    salida = a.salida or (a.pista / "curvas.json")
    cat.guardar(salida)
    print(cat.tabla())
    print(f"{len(cat.curvas)} curvas -> {salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
