"""D0 (`circuito_virtual/docs/PLAN.md`): mapa virtual de la pista en coordenadas (s, n).

- `s`: distancia de vuelta en metros (la que da el juego, `lap_distance`), de 0 a la longitud de la pista; la pista es cerrada.
- `n`: desplazamiento lateral respecto al eje en metros, **positivo a la derecha**; es la misma convención que el CTE firmado de producción
  (`obs_universal.signed_lateral_error`: derecha = (tz, −tx)).
- El **eje** es la línea de referencia (suavizada, H61), no el centro geométrico del asfalto: los bordes `borde_izq(s)` (n < 0) y `borde_dcha(s)` (n > 0)
  se miden respecto a él (D1) y quedan como NaN hasta entonces.

El eje es una poligonal con un punto por metro. La posición se interpola linealmente y la tangente se interpola entre vértices, de modo que
`sn_a_xz` y `xz_a_sn` son una la inversa de la otra con error de milímetros mientras `|n · κ| < 0,5` (con R = 46 m, |n| < 23 m).

Uso:
    python circuito_virtual/src/mapa.py construir [--referencia PCARS2-AI/src/refs/sugo_ai.json] [--salida circuito_virtual/pistas/sugo_gp/mapa.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[2]
DEFAULT_REF = REPO / "PCARS2-AI" / "src" / "refs" / "sugo_ai.json"
DEFAULT_OUT = REPO / "circuito_virtual" / "pistas" / "sugo_gp" / "mapa.json"
VERSION = 1
SUPERFICIE_DESCONOCIDA = -1
FIXED_POINT_ITERATIONS = 8


def _wrap_angle(a: np.ndarray) -> np.ndarray:
    return (a + np.pi) % (2 * np.pi) - np.pi


@dataclass
class Mapa:
    nombre: str
    longitud_m: float
    s: np.ndarray  # distancia de vuelta de cada punto del eje, creciente, empieza en 0
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    borde_izq: np.ndarray = field(default_factory=lambda: np.empty(0))  # n del borde izquierdo (< 0); NaN = desconocido
    borde_dcha: np.ndarray = field(default_factory=lambda: np.empty(0))  # n del borde derecho (> 0); NaN = desconocido
    sup_izq: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=int))  # eTerrain de la rueda que tocó el borde
    sup_dcha: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=int))
    meta: Dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        n = len(self.s)
        if n < 8 or not (len(self.x) == len(self.y) == len(self.z) == n):
            raise ValueError("el eje necesita al menos 8 puntos y las mismas longitudes en s, x, y y z")
        if np.any(np.diff(self.s) <= 0) or self.s[0] != 0 or self.longitud_m <= self.s[-1]:
            raise ValueError("s debe ser creciente desde 0 y menor que la longitud de la pista")
        for name, default in (("borde_izq", np.nan), ("borde_dcha", np.nan)):
            arr = getattr(self, name)
            setattr(self, name, np.full(n, default) if len(arr) == 0 else np.asarray(arr, dtype=float))
        for name in ("sup_izq", "sup_dcha"):
            arr = getattr(self, name)
            setattr(self, name, np.full(n, SUPERFICIE_DESCONOCIDA, dtype=int) if len(arr) == 0 else np.asarray(arr, dtype=int))
        self._derivar()

    # ---- geometría derivada del eje -------------------------------------------------------------------------------
    def _derivar(self) -> None:
        px, pz = self.x, self.z
        tx = np.roll(px, -1) - np.roll(px, 1)
        tz = np.roll(pz, -1) - np.roll(pz, 1)
        norm = np.maximum(np.hypot(tx, tz), 1e-9)
        self.tx, self.tz = tx / norm, tz / norm
        self._s_ext = np.append(self.s, self.longitud_m)
        psi = np.arctan2(self.tz, self.tx)
        s_next = np.append(self.s[1:], self.s[0] + self.longitud_m)
        s_prev = np.insert(self.s[:-1], 0, self.s[-1] - self.longitud_m)
        ds = s_next - s_prev
        self.kappa = _wrap_angle(np.roll(psi, -1) - np.roll(psi, 1)) / ds  # + = giro a la izquierda (como ReferenceLine.curvature)
        self.pendiente = (np.roll(self.y, -1) - np.roll(self.y, 1)) / ds  # + = cuesta arriba

    @property
    def n_puntos(self) -> int:
        return len(self.s)

    def eje(self, s) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Posición (x, z) y tangente unitaria (tx, tz) del eje en `s` (cualquier valor, se envuelve a la vuelta)."""
        s = np.mod(np.asarray(s, dtype=float), self.longitud_m)
        i = np.clip(np.searchsorted(self._s_ext, s, side="right") - 1, 0, self.n_puntos - 1)
        j = (i + 1) % self.n_puntos
        span = self._s_ext[i + 1] - self._s_ext[i]
        t = (s - self._s_ext[i]) / span
        px = self.x[i] + t * (self.x[j] - self.x[i])
        pz = self.z[i] + t * (self.z[j] - self.z[i])
        tx = (1 - t) * self.tx[i] + t * self.tx[j]
        tz = (1 - t) * self.tz[i] + t * self.tz[j]
        norm = np.maximum(np.hypot(tx, tz), 1e-9)
        return px, pz, tx / norm, tz / norm

    def sn_a_xz(self, s, n) -> Tuple[np.ndarray, np.ndarray]:
        """Del sistema (s, n) al mundo: eje(s) + n · derecha, con derecha = (tz, −tx)."""
        px, pz, tx, tz = self.eje(s)
        n = np.asarray(n, dtype=float)
        return px + n * tz, pz - n * tx

    def xz_a_sn(self, x, z, s_hint=None) -> Tuple[np.ndarray, np.ndarray]:
        """Del mundo a (s, n): pie de la perpendicular al eje. `s_hint` (opcional) restringe la búsqueda inicial a ±100 m."""
        x = np.atleast_1d(np.asarray(x, dtype=float))
        z = np.atleast_1d(np.asarray(z, dtype=float))
        if s_hint is None:
            s0 = np.empty(len(x))
            for a in range(0, len(x), 512):  # por bloques para no montar una matriz enorme
                dx = x[a:a + 512, None] - self.x[None, :]
                dz = z[a:a + 512, None] - self.z[None, :]
                s0[a:a + 512] = self.s[np.argmin(dx * dx + dz * dz, axis=1)]
        else:
            hint = np.broadcast_to(np.asarray(s_hint, dtype=float), x.shape)
            idx0 = np.clip(np.searchsorted(self.s, np.mod(hint, self.longitud_m)), 0, self.n_puntos - 1)
            ventana = int(100.0 / max(self.longitud_m / self.n_puntos, 1e-6))
            s0 = np.empty(len(x))
            for a in range(0, len(x), 4096):  # ±100 m alrededor de la pista, por bloques
                idx = (idx0[a:a + 4096, None] + np.arange(-ventana, ventana + 1)[None, :]) % self.n_puntos
                d2 = (x[a:a + 4096, None] - self.x[idx]) ** 2 + (z[a:a + 4096, None] - self.z[idx]) ** 2
                s0[a:a + 4096] = self.s[idx[np.arange(len(idx)), np.argmin(d2, axis=1)]]
        s = s0
        for _ in range(FIXED_POINT_ITERATIONS):
            px, pz, tx, tz = self.eje(s)
            s = np.mod(s + (x - px) * tx + (z - pz) * tz, self.longitud_m)
        px, pz, tx, tz = self.eje(s)
        return s, (x - px) * tz - (z - pz) * tx

    # ---- bordes y pasillo -----------------------------------------------------------------------------------------
    def interpola(self, valores: np.ndarray, s) -> np.ndarray:
        """Valor de un campo por punto (curvatura, bordes...) en `s`, interpolado linealmente."""
        s = np.mod(np.asarray(s, dtype=float), self.longitud_m)
        return np.interp(s, self._s_ext, np.append(valores, valores[0]))

    @property
    def bordes_conocidos(self) -> float:
        """Parte de la vuelta con ambos bordes medidos, de 0 a 1."""
        return float(np.mean(np.isfinite(self.borde_izq) & np.isfinite(self.borde_dcha)))

    def pasillo(self, s, margen_m: float = 0.0) -> Tuple[np.ndarray, np.ndarray]:
        """(n mínimo, n máximo) permitidos para el centro del coche en `s`: el borde menos el margen. NaN donde no se midió."""
        return self.interpola(self.borde_izq, s) + margen_m, self.interpola(self.borde_dcha, s) - margen_m

    # ---- persistencia ---------------------------------------------------------------------------------------------
    def a_dict(self) -> Dict:
        def lista(a, nd=3):
            return [None if (isinstance(v, float) and not np.isfinite(v)) else (round(float(v), nd) if nd else int(v)) for v in a.tolist()]

        return {"version": VERSION, "nombre": self.nombre, "longitud_m": round(self.longitud_m, 3), "meta": self.meta,
                "s": lista(self.s), "x": lista(self.x), "y": lista(self.y), "z": lista(self.z),
                "borde_izq": lista(self.borde_izq), "borde_dcha": lista(self.borde_dcha),
                "sup_izq": lista(self.sup_izq, 0), "sup_dcha": lista(self.sup_dcha, 0)}

    @staticmethod
    def de_dict(d: Dict) -> "Mapa":
        if d.get("version") != VERSION:
            raise ValueError(f"versión de mapa no soportada: {d.get('version')!r}")
        nan = lambda a: np.array([np.nan if v is None else v for v in a], dtype=float)  # noqa: E731
        return Mapa(d["nombre"], float(d["longitud_m"]), nan(d["s"]), nan(d["x"]), nan(d["y"]), nan(d["z"]),
                    nan(d["borde_izq"]), nan(d["borde_dcha"]), np.array(d["sup_izq"], dtype=int), np.array(d["sup_dcha"], dtype=int),
                    d.get("meta", {}))

    def guardar(self, ruta: Path) -> None:
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        Path(ruta).write_text(json.dumps(self.a_dict(), separators=(",", ":")), encoding="utf-8")

    @staticmethod
    def cargar(ruta: Path) -> "Mapa":
        return Mapa.de_dict(json.loads(Path(ruta).read_text(encoding="utf-8")))

    @staticmethod
    def desde_referencia(datos: Dict, meta: Optional[Dict] = None) -> "Mapa":
        """Eje a partir del JSON de `ReferenceLine` (`points[i]["d"]` y `["pos"]`)."""
        pts = datos["points"]
        s = np.array([p["d"] for p in pts], dtype=float)
        order = np.argsort(s)
        s = s[order] - s[order][0]
        pos = np.array([p["pos"] for p in pts], dtype=float)[order]
        return Mapa(str(datos.get("track_name", "")).split("\x00")[0].strip(), float(datos["track_length"]), s, pos[:, 0], pos[:, 1], pos[:, 2],
                    meta=meta or {})


def construir(referencia: Path = DEFAULT_REF, sigma_m: Optional[float] = None) -> Mapa:
    """Mapa de la pista a partir de la referencia, con el eje suavizado en rectas (H61)."""
    sys.path.insert(0, str(REPO))
    from circuito_virtual.src import linea_suave  # noqa: PLC0415

    datos = json.loads(Path(referencia).read_text(encoding="utf-8"))
    suave, _ = linea_suave.smooth_reference(datos, sigma_m or linea_suave.SIGMA_M)
    return Mapa.desde_referencia(suave, {"origen": Path(referencia).name, "eje": "referencia suavizada en rectas (linea_suave.py, H61)",
                                         "sigma_m": sigma_m or linea_suave.SIGMA_M, "bordes": "sin medir (D1)"})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("construir", help="construye el mapa (eje) desde la referencia")
    b.add_argument("--referencia", type=Path, default=DEFAULT_REF)
    b.add_argument("--salida", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    mapa = construir(args.referencia)
    mapa.guardar(args.salida)
    rng = np.random.default_rng(1)
    s = rng.uniform(0, mapa.longitud_m, 2000)
    n = rng.uniform(-6, 6, 2000)
    s2, n2 = mapa.xz_a_sn(*mapa.sn_a_xz(s, n))
    ds = np.abs((s2 - s + mapa.longitud_m / 2) % mapa.longitud_m - mapa.longitud_m / 2)
    print(f"{mapa.nombre}: {mapa.n_puntos} puntos, {mapa.longitud_m:.1f} m -> {args.salida}")
    print(f"ida y vuelta (s, n) -> (x, z) -> (s, n) con |n| <= 6 m: error de s máx. {ds.max() * 100:.2f} cm, de n máx. {np.abs(n2 - n).max() * 100:.2f} cm")
    print(f"bordes conocidos: {100 * mapa.bordes_conocidos:.0f} % de la vuelta (D1 los mide)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
