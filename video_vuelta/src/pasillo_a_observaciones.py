"""Del mapa de bordes corregido (`mapa_corregido.py`) al archivo de observaciones que lee `linea_optima.py` (D12 de docs/DECISIONES.md).

Uso:
    python video_vuelta/src/pasillo_a_observaciones.py <mapa_bordes_corregido.json> --salida circuito_virtual/pistas/<pista>/observaciones_pasillo_d11.json
        [--base circuito_virtual/pistas/<pista>/observaciones_logs.json] [--prudente 0.3]

El límite de carrera de cada metro (la `n` de la rueda sobre el borde, la misma convención de `bordes_logs.py`) se guarda como un borde medido: `dentro` = `fuera` =
límite, con un solo tick, de modo que `Observaciones.bordes()` lo da por medido y `linea_optima.pasillo_centro` lo usa tal cual. Donde el mapa corregido no tiene dato se
queda lo que ya había en `--base` (si se da). Con `--prudente M` los metros con incertidumbre ≥ 0,4 m (corrección propagada o solo vídeo) se acercan M m a la pista.

Escribe un archivo nuevo; no toca `observaciones_logs.json`. Para generar la línea con él:
    python circuito_virtual/src/linea_optima.py ... --observaciones observaciones_pasillo_d11.json --nombre <nombre>
"""
from __future__ import annotations

import argparse
import json
import io
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "PCARS2-AI" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from circuito_virtual.src.bordes_logs import Observaciones  # noqa: E402
from circuito_virtual.src.linea_optima import bordes_rueda  # noqa: E402

SIGMA_PRUDENTE_M = 0.4


def _lista(a) -> np.ndarray:
    return np.array([np.nan if v is None else v for v in a], dtype=float)


def desde_mapa_corregido(datos: dict, base: Observaciones, prudente_m: float = 0.0, nombre: str = "corregido") -> Observaciones:
    """Observaciones con el límite del mapa corregido como borde medido (`datos` = JSON de `mapa_corregido.py`)."""
    izq, dcha = _lista(datos["borde_izq"]), _lista(datos["borde_dcha"])
    if len(izq) != base.n_puntos or len(dcha) != base.n_puntos:
        raise ValueError(f"el mapa corregido tiene {len(izq)} puntos y las observaciones base {base.n_puntos}")
    if prudente_m:
        sig_i, sig_d = _lista(datos["sigma_izq"]), _lista(datos["sigma_dcha"])
        izq = np.where(sig_i >= SIGMA_PRUDENTE_M, izq + prudente_m, izq)
        dcha = np.where(sig_d >= SIGMA_PRUDENTE_M, dcha - prudente_m, dcha)
    r_izq, r_dcha = bordes_rueda(base)
    izq = np.where(np.isfinite(izq), izq, r_izq)
    dcha = np.where(np.isfinite(dcha), dcha, r_dcha)
    return Observaciones(base.n_puntos, base.longitud_m, izq, izq.copy(), dcha, dcha.copy(), np.ones(base.n_puntos, dtype=int), [nombre], base.semivia_m)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("corregido", type=Path)
    ap.add_argument("--base", type=Path, default=REPO / "circuito_virtual" / "pistas" / "sugo_gp" / "observaciones_logs.json",
                    help="observaciones de las que se toman la semivía y los metros sin dato")
    ap.add_argument("--prudente", type=float, default=0.0, help="m que se acercan a la pista los metros con incertidumbre ≥ 0,4 m")
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    base = Observaciones.de_dict(json.loads(a.base.read_text(encoding="utf-8")))
    datos = json.loads(a.corregido.read_text(encoding="utf-8"))
    obs = desde_mapa_corregido(datos, base, a.prudente, nombre=f"corregido:{a.corregido.parent.name}" + (f" prudente {a.prudente:g}" if a.prudente else ""))
    a.salida.write_text(json.dumps(obs.a_dict(), separators=(",", ":")), encoding="utf-8")
    print(f"guardado: {a.salida}; ancho mediano de la rueda {np.nanmedian(obs.dcha_dentro - obs.izq_dentro):.2f} m, mínimo {np.nanmin(obs.dcha_dentro - obs.izq_dentro):.2f} m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
