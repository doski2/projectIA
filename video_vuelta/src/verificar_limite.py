"""Verifica el límite de carrera medido por vídeo con una vuelta que cruza la línea blanca (D6, D10 de docs/DECISIONES.md).

Uso:
    python video_vuelta/src/verificar_limite.py <log.jsonl> [--bordes mapa_bordes_video.json] [--lado izq|dcha|ambos]

Solo hace falta el log (posición y terreno por rueda): se graba con `circuito_virtual/src/sesion_manual.py` conduciendo cruzando la línea blanca de un
lado a otro; no hace falta vídeo. En cada tick el coche tiene su `n` en el mapa; cuando las dos ruedas de un lado pasan de «en carrera» a «fuera» (o
vuelven) la rueda está sobre el borde del juego, y su posición `n ∓ semivía` (0,85 m, la misma supuesta en `bordes_logs.py`, así se cancela) se compara con
el límite del vídeo en ese metro. Si las constantes de `bordes_video.py` (0,06 y 0,18 m) valen, el error mediano sale ≈ 0.

Imprime, por lado y sentido del cruce (saliendo / entrando), cuántos cruces hay, el error mediano y su rango intercuartil, y los cruces que se alejan más de
0,5 m. No escribe nada.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "PCARS2-AI" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from circuito_virtual.src.bordes_logs import LEFT_WHEELS, RIGHT_WHEELS, SEMIVIA_M  # noqa: E402
from circuito_virtual.src.mapa import Mapa  # noqa: E402
from pcars2_surface import RACING_TERRAIN_IDS  # noqa: E402

MIN_KMH = 8.0
REBOTE_S = 0.25  # dos cruces del mismo lado y sentido más juntos que esto cuentan como uno
BORDES = REPO / "video_vuelta" / "capturas" / "sugo_gp" / "formula_r" / "2026-11-08_2" / "mapa_bordes_video.json"
MAPA = REPO / "circuito_virtual" / "pistas" / "sugo_gp" / "mapa.json"


def leer(ruta: Path) -> dict:
    t, s, x, z, v, terr = [], [], [], [], [], []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            if '"type": "tick"' not in linea[:20]:
                continue
            r = json.loads(linea)
            veh = r.get("vehicle") or {}
            if not veh.get("position") or not veh.get("terrain"):
                continue
            t.append(r["t_s"])
            s.append(r["lap_distance"])
            v.append(r["speed_kmh"])
            x.append(veh["position"][0])
            z.append(veh["position"][2])
            terr.append(veh["terrain"][:4])
    if not t:
        raise ValueError(f"{ruta}: sin ticks con posición y terreno")
    return {"t": np.array(t), "s": np.array(s), "x": np.array(x), "z": np.array(z), "v": np.array(v), "terreno": np.array(terr, dtype=int)}


def cruces(d: dict, mapa: Mapa, ruedas: tuple[int, int], signo: float, borde: np.ndarray) -> list[dict]:
    """Cruces de un lado: `signo` −1 izquierda, +1 derecha. Devuelve s, n de la rueda, límite del vídeo y error (m) de cada uno."""
    marcha = d["v"] > MIN_KMH
    s_map, n_car = mapa.xz_a_sn(d["x"], d["z"], s_hint=d["s"])
    dentro = np.isin(d["terreno"][:, list(ruedas)], list(RACING_TERRAIN_IDS)).all(axis=1)
    out, ultimo = [], {"saliendo": -1e9, "entrando": -1e9}
    for i in np.where(marcha[1:] & marcha[:-1] & (dentro[1:] != dentro[:-1]))[0] + 1:
        sentido = "saliendo" if dentro[i - 1] else "entrando"
        if d["t"][i] - ultimo[sentido] < REBOTE_S:
            continue
        ultimo[sentido] = d["t"][i]
        lim = float(mapa.interpola(borde, s_map[i]))
        if not np.isfinite(lim):
            continue
        n_rueda = float(n_car[i] + signo * SEMIVIA_M)
        out.append({"s": float(s_map[i]), "sentido": sentido, "n_rueda": n_rueda, "limite": lim, "error": n_rueda - lim})
    return out


def resumen(lista: list[dict]) -> str:
    if not lista:
        return "sin cruces"
    e = np.array([c["error"] for c in lista])
    return (f"{len(e):3d} cruces  error mediano {np.median(e):+.2f} m  IQR {np.percentile(e, 25):+.2f}..{np.percentile(e, 75):+.2f}  "
            f"|error|<0,3: {100 * np.mean(np.abs(e) < 0.3):.0f} %  <0,5: {100 * np.mean(np.abs(e) < 0.5):.0f} %")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("log", type=Path)
    ap.add_argument("--bordes", type=Path, default=BORDES)
    ap.add_argument("--mapa", type=Path, default=MAPA)
    ap.add_argument("--lado", choices=("izq", "dcha", "ambos"), default="ambos")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    mapa = Mapa.cargar(a.mapa)
    lim = Mapa.cargar(a.bordes)
    d = leer(a.log)
    print(f"{a.log.name}: {len(d['t'])} ticks, {np.sum(d['v'] > MIN_KMH)} en marcha")
    for lado, ruedas, signo, borde in (("izq", LEFT_WHEELS, -1.0, lim.borde_izq), ("dcha", RIGHT_WHEELS, 1.0, lim.borde_dcha)):
        if a.lado not in (lado, "ambos"):
            continue
        todos = cruces(d, mapa, ruedas, signo, borde)
        print(f"== {lado}: {resumen(todos)}")
        for sentido in ("saliendo", "entrando"):
            print(f"   {sentido}: {resumen([c for c in todos if c['sentido'] == sentido])}")
        lejos = [c for c in todos if abs(c["error"]) > 0.5]
        if lejos:
            print("   cruces a más de 0,5 m del límite (s, sentido, error): " + "; ".join(f"{c['s']:.0f} m {c['sentido']} {c['error']:+.2f}" for c in lejos[:15]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
