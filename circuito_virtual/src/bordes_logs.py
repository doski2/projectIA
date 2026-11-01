"""D1a (`circuito_virtual/docs/PLAN.md`): qué dicen los logs que ya hay sobre los bordes de la pista.

Cada tick de un log de esquema 2 trae la posición del coche y el terreno de las cuatro ruedas. Con la posición se calcula la `n` del coche respecto al
eje del mapa y, con una semivía supuesta (`SEMIVIA_M`), la `n` de cada rueda (izquierda = FL y RL, derecha = FR y RR). Por cada metro de vuelta y lado se guardan dos cotas:

- **asfalto hasta** (`dentro`): la rueda más alejada del eje que seguía en superficie de carrera (asfalto, bordillo...). El borde está al menos ahí.
- **fuera desde** (`fuera`): la rueda más cercana al eje que ya estaba fuera (césped, grava, franja ilegal...). El borde está antes de ahí.

El borde cae entre las dos cotas; donde las dos existen, la incertidumbre es su separación. Donde solo hay `dentro`, se sabe hasta dónde llega el asfalto
como mínimo, pero no dónde acaba. La semivía y el efecto del rumbo del coche sobre la posición de las ruedas son aproximaciones (D1b las calibra).

Uso:
    python circuito_virtual/src/bordes_logs.py escanear [--logs-dir PCARS2-AI/logs/learning] [--mapa circuito_virtual/pistas/sugo_gp/mapa.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "PCARS2-AI" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from circuito_virtual.src.mapa import Mapa  # noqa: E402
from pcars2_surface import RACING_TERRAIN_IDS  # noqa: E402

SEMIVIA_M = 0.85  # media distancia entre ruedas izquierda y derecha (sin medir; D1b)
MIN_SPEED_MS = 2.0
LEFT_WHEELS = (0, 2)  # FL, RL
RIGHT_WHEELS = (1, 3)  # FR, RR
MAX_BRACKET_M = 0.6  # un borde se da por medido si las dos cotas están a menos de esto
TOLERANCIA_SOLAPE_M = 0.15  # las cotas pueden cruzarse esto por el rumbo del coche y la semivía supuesta
OUT = REPO / "circuito_virtual" / "pistas" / "sugo_gp" / "observaciones_logs.json"


@dataclass
class Observaciones:
    """Cotas por metro de vuelta y lado (n de la rueda respecto al eje; NaN = sin dato)."""

    n_puntos: int
    longitud_m: float
    izq_dentro: np.ndarray  # n más negativa con la rueda izquierda aún en superficie de carrera
    izq_fuera: np.ndarray  # n más próxima al eje con una rueda izquierda ya fuera (n de esa rueda; < borde)
    dcha_dentro: np.ndarray  # n más positiva con la rueda derecha aún en superficie de carrera
    dcha_fuera: np.ndarray
    ticks: np.ndarray  # ticks por metro, para saber cuánto se ha pasado
    logs: List[str]
    semivia_m: float = SEMIVIA_M

    @staticmethod
    def vacia(mapa: Mapa, semivia_m: float = SEMIVIA_M) -> "Observaciones":
        n = mapa.n_puntos
        return Observaciones(n, mapa.longitud_m, np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan),
                             np.zeros(n, dtype=int), [], semivia_m)

    def _bin(self, s: np.ndarray) -> np.ndarray:
        return np.clip((np.mod(s, self.longitud_m) / self.longitud_m * self.n_puntos).astype(int), 0, self.n_puntos - 1)

    def agregar(self, mapa: Mapa, s_juego, x, z, terreno, velocidad_ms) -> int:
        """Añade ticks (arrays): distancia de vuelta del juego, posición (x, z), terreno (N, 4) y velocidad. Devuelve cuántos usó."""
        s_juego, x, z = (np.asarray(a, dtype=float) for a in (s_juego, x, z))
        terreno = np.asarray(terreno, dtype=int).reshape(-1, 4)
        ok = np.asarray(velocidad_ms, dtype=float) > MIN_SPEED_MS
        if not ok.any():
            return 0
        s, n = mapa.xz_a_sn(x[ok], z[ok], s_hint=s_juego[ok])
        self._acumular(s, n, terreno[ok])
        return int(ok.sum())

    def agregar_cte(self, mapa: Mapa, s_juego, cte, terreno, velocidad_ms, n_referencia: np.ndarray) -> int:
        """Como `agregar`, para logs sin posición: la `n` del coche es el CTE firmado más la `n` que tiene en el mapa la línea de referencia de esa sesión."""
        s_juego, cte = np.asarray(s_juego, dtype=float), np.asarray(cte, dtype=float)
        terreno = np.asarray(terreno, dtype=int).reshape(-1, 4)
        ok = np.asarray(velocidad_ms, dtype=float) > MIN_SPEED_MS
        if not ok.any():
            return 0
        s = np.mod(s_juego[ok], self.longitud_m)
        self._acumular(s, cte[ok] + mapa.interpola(n_referencia, s), terreno[ok])
        return int(ok.sum())

    def _acumular(self, s: np.ndarray, n: np.ndarray, terr: np.ndarray) -> None:
        racing = np.isin(terr, list(RACING_TERRAIN_IDS))
        b = self._bin(s)
        np.add.at(self.ticks, b, 1)
        for lado, ruedas, signo, dentro, fuera in (
            ("izq", LEFT_WHEELS, -1.0, self.izq_dentro, self.izq_fuera),
            ("dcha", RIGHT_WHEELS, +1.0, self.dcha_dentro, self.dcha_fuera),
        ):
            n_rueda = n + signo * self.semivia_m
            r = racing[:, list(ruedas)].all(axis=1)  # las dos ruedas de ese lado en superficie de carrera
            f = ~r  # alguna de las dos fuera
            # "dentro": la rueda más lejana del eje que seguía en carrera -> mínimo en la izquierda, máximo en la derecha
            if r.any():
                (np.fmin if signo < 0 else np.fmax).at(dentro, b[r], n_rueda[r])
            # "fuera": la rueda más cercana al eje que ya estaba fuera -> máximo en la izquierda, mínimo en la derecha
            if f.any():
                (np.fmax if signo < 0 else np.fmin).at(fuera, b[f], n_rueda[f])

    def agregar_log(self, mapa: Mapa, ruta: Path, n_referencia: Optional[np.ndarray] = None) -> int:
        """Lee un log. Con posición por tick usa la proyección al mapa; sin ella, y si se da `n_referencia`, usa el CTE firmado."""
        s_l: List[float] = []
        x_l: List[float] = []
        z_l: List[float] = []
        t_l: List[List[int]] = []
        v_l: List[float] = []
        c_l: List[float] = []
        sin_pos = {"s": [], "cte": [], "t": [], "v": []}
        with open(ruta, encoding="utf-8") as fh:
            for linea in fh:
                if '"type": "tick"' not in linea:
                    continue
                d = json.loads(linea)
                veh = d.get("vehicle") or {}
                pos, terr = veh.get("position"), veh.get("terrain")
                if not terr or len(terr) < 4:
                    continue
                if pos:
                    s_l.append(d["lap_distance"])
                    x_l.append(pos[0])
                    z_l.append(pos[2])
                    t_l.append(terr[:4])
                    v_l.append(d.get("speed_kmh", 0.0) / 3.6)
                elif n_referencia is not None and d.get("signed_cte") is not None:
                    sin_pos["s"].append(d["lap_distance"])
                    sin_pos["cte"].append(d["signed_cte"])
                    sin_pos["t"].append(terr[:4])
                    sin_pos["v"].append(d.get("speed_kmh", 0.0) / 3.6)
        usados = self.agregar(mapa, s_l, x_l, z_l, t_l, v_l) if s_l else 0
        if sin_pos["s"]:
            usados += self.agregar_cte(mapa, sin_pos["s"], sin_pos["cte"], sin_pos["t"], sin_pos["v"], n_referencia)
        if usados:
            self.logs.append(Path(ruta).name)
        return usados

    # ---- resultados ------------------------------------------------------------------------------------------------------
    def bordes(self) -> Dict[str, np.ndarray]:
        """Borde medido por lado (NaN si no hay las dos cotas o están a más de `MAX_BRACKET_M`) y su incertidumbre."""
        out: Dict[str, np.ndarray] = {}
        for lado, dentro, fuera, signo in (("izq", self.izq_dentro, self.izq_fuera, -1.0), ("dcha", self.dcha_dentro, self.dcha_fuera, +1.0)):
            # a la izquierda el borde cae entre «fuera» (menor n) y «dentro»; a la derecha, entre «dentro» y «fuera» (mayor n)
            hueco = (dentro - fuera) if signo < 0 else (fuera - dentro)
            ok = np.isfinite(dentro) & np.isfinite(fuera) & (hueco >= -TOLERANCIA_SOLAPE_M) & (hueco <= MAX_BRACKET_M)
            out[lado] = np.where(ok, (dentro + fuera) / 2.0, np.nan)  # si se solapan (rumbo, semivía) se da el punto medio igualmente
            out[f"{lado}_incertidumbre"] = np.where(ok, np.abs(hueco) / 2.0 + TOLERANCIA_SOLAPE_M / 2.0, np.nan)
        return out

    def cobertura(self) -> Dict[str, float]:
        b = self.bordes()
        return {
            "metros_con_datos": float(np.mean(self.ticks > 0)),
            "borde_izq_medido": float(np.mean(np.isfinite(b["izq"]))),
            "borde_dcha_medido": float(np.mean(np.isfinite(b["dcha"]))),
            "asfalto_hasta_izq": float(np.mean(np.isfinite(self.izq_dentro))),
            "asfalto_hasta_dcha": float(np.mean(np.isfinite(self.dcha_dentro))),
            "fuera_izq": float(np.mean(np.isfinite(self.izq_fuera))),
            "fuera_dcha": float(np.mean(np.isfinite(self.dcha_fuera))),
        }

    def a_mapa(self, mapa: Mapa) -> Mapa:
        """Copia del mapa con los bordes que ya están medidos (los demás siguen en NaN)."""
        b = self.bordes()
        nuevo = Mapa(mapa.nombre, mapa.longitud_m, mapa.s.copy(), mapa.x.copy(), mapa.y.copy(), mapa.z.copy(),
                     np.where(np.isfinite(b["izq"]), b["izq"], mapa.borde_izq), np.where(np.isfinite(b["dcha"]), b["dcha"], mapa.borde_dcha),
                     mapa.sup_izq.copy(), mapa.sup_dcha.copy(), dict(mapa.meta))
        nuevo.meta["bordes"] = f"logs ({len(self.logs)}), semivía {self.semivia_m:g} m (D1a)"
        nuevo.meta["semivia_m"] = self.semivia_m
        return nuevo

    def a_dict(self) -> Dict:
        def lista(a):
            return [None if (isinstance(v, float) and not np.isfinite(v)) else round(float(v), 3) for v in a.tolist()]

        return {"n_puntos": self.n_puntos, "longitud_m": self.longitud_m, "semivia_m": self.semivia_m, "logs": self.logs,
                "izq_dentro": lista(self.izq_dentro), "izq_fuera": lista(self.izq_fuera), "dcha_dentro": lista(self.dcha_dentro),
                "dcha_fuera": lista(self.dcha_fuera), "ticks": self.ticks.tolist()}

    @staticmethod
    def de_dict(d: Dict) -> "Observaciones":
        nan = lambda a: np.array([np.nan if v is None else v for v in a], dtype=float)  # noqa: E731
        return Observaciones(d["n_puntos"], d["longitud_m"], nan(d["izq_dentro"]), nan(d["izq_fuera"]), nan(d["dcha_dentro"]), nan(d["dcha_fuera"]),
                             np.array(d["ticks"], dtype=int), list(d["logs"]), d.get("semivia_m", SEMIVIA_M))


def n_de_la_referencia(mapa: Mapa, ruta_referencia: Path) -> np.ndarray:
    """`n` que tiene en el mapa cada punto del eje de la línea de referencia de producción (el CTE de los logs se mide contra ella, no contra el eje suavizado)."""
    datos = json.loads(Path(ruta_referencia).read_text(encoding="utf-8"))
    pts = datos["points"]
    d = np.array([p["d"] for p in pts], dtype=float)
    pos = np.array([p["pos"] for p in pts], dtype=float)
    _, n = mapa.xz_a_sn(pos[:, 0], pos[:, 2], s_hint=d)
    return np.interp(mapa.s, d, n, period=mapa.longitud_m)


REFERENCIA_ACTUAL_S = 213.875  # `reference_lap_s` de la cabecera de los logs hechos con la referencia vigente (desde 2026-10-10)


def logs_con_terreno(carpeta: Path, vuelta_referencia_s: float = REFERENCIA_ACTUAL_S) -> Iterable[Path]:
    """Logs que traen el terreno de las ruedas y se hicieron con la referencia vigente (cabecera con esa vuelta o sin ella, de después del cambio)."""
    for ruta in sorted(Path(carpeta).glob("*.jsonl")):
        try:
            with open(ruta, encoding="utf-8") as fh:
                cab = json.loads(fh.readline())
                ref_s = cab.get("reference_lap_s")
                if ref_s is not None and abs(float(ref_s) - vuelta_referencia_s) > 0.01:
                    continue  # otra línea de referencia: el CTE no vale contra esta
                for linea in fh:
                    if '"type": "tick"' in linea:
                        veh = json.loads(linea).get("vehicle") or {}
                        if veh.get("terrain"):
                            yield ruta
                        break
        except (OSError, ValueError):
            continue


def logs_esquema_2(carpeta: Path) -> Iterable[Path]:
    """Logs con posición y terreno por rueda (esquema 2), por orden de nombre."""
    for ruta in sorted(Path(carpeta).glob("*.jsonl")):
        try:
            with open(ruta, encoding="utf-8") as fh:
                if json.loads(fh.readline()).get("log_schema", 1) >= 2:
                    yield ruta
        except (OSError, ValueError):
            continue


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("escanear", help="recorre los logs y guarda las cotas por metro")
    e.add_argument("--logs-dir", type=Path, default=REPO / "PCARS2-AI" / "logs" / "learning")
    e.add_argument("--mapa", type=Path, default=REPO / "circuito_virtual" / "pistas" / "sugo_gp" / "mapa.json")
    e.add_argument("--salida", type=Path, default=OUT)
    e.add_argument("--semivia", type=float, default=SEMIVIA_M)
    e.add_argument("--referencia", type=Path, default=REPO / "PCARS2-AI" / "src" / "refs" / "sugo_ai.json",
                   help="línea de referencia contra la que se midió el CTE de los logs sin posición")
    e.add_argument("--carpetas", nargs="*", default=["learning", "teaching", "imitation"],
                   help="subcarpetas de PCARS2-AI/logs; --logs-dir apunta a la de learning y las demás se buscan a su lado")
    args = ap.parse_args(argv)
    mapa = Mapa.cargar(args.mapa)
    obs = Observaciones.vacia(mapa, args.semivia)
    n_ref = n_de_la_referencia(mapa, args.referencia)
    for carpeta in args.carpetas:
        for ruta in logs_con_terreno(args.logs_dir.parent / carpeta):
            usados = obs.agregar_log(mapa, ruta, n_ref)
            print(f"{carpeta}/{ruta.name}: {usados} ticks", flush=True)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(obs.a_dict(), separators=(",", ":")), encoding="utf-8")
    print(json.dumps(obs.cobertura(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
