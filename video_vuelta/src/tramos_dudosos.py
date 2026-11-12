"""Tramos donde el límite del vídeo y las ruedas no coinciden, con su instante del vídeo y los fotogramas para revisarlos con el usuario (D12 de docs/DECISIONES.md).

Uso:
    python video_vuelta/src/tramos_dudosos.py <log.jsonl> --lado izq|dcha --desfase 7.40 [--video <video.mp4> --fotogramas carpeta] [--bordes mapa_bordes_video.json] [--umbral 0.5]

Agrupa los cruces de terreno a más de `--umbral` m del límite en tramos de < 40 m y de cada uno da: instante del vídeo (`t_log = t_vídeo + desfase`), metros de vuelta, curva,
errores, y la secuencia de terrenos de las dos ruedas del lado (0 asfalto, 7 hierba, 10 piano rugoso, 46 asfalto fuera de la línea, 48 piano plano pintado, 49 pintura ilegal...).
Con `--video` y `--fotogramas` guarda un fotograma por tramo (`<carpeta>/NN_<curva>_<metros>m.jpg`) para mirarlos de uno en uno: **las reglas del límite de cada pista las decide el
usuario viendo esos fotogramas** (D11). Solo lee.
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

from circuito_virtual.src.bordes_logs import LEFT_WHEELS, RIGHT_WHEELS  # noqa: E402
from circuito_virtual.src.mapa import Mapa  # noqa: E402
from video_vuelta.src import verificar_limite as vl  # noqa: E402

SEPARACION_M = 40.0


def agrupar(cruces: list[dict], umbral_m: float, separacion_m: float = SEPARACION_M) -> list[list[dict]]:
    """Cruces con |error| > umbral, ordenados por metro y agrupados si el siguiente está a menos de `separacion_m` del último."""
    grupos: list[list[dict]] = []
    for c in sorted(cruces, key=lambda c: c["s"]):
        if abs(c["error"]) <= umbral_m:
            continue
        if grupos and c["s"] - grupos[-1][-1]["s"] < separacion_m:
            grupos[-1].append(c)
        else:
            grupos.append([c])
    return grupos


def secuencia(valores) -> str:
    """Terrenos consecutivos sin repetir: [0, 0, 7, 7, 0] → «0→7→0»."""
    salida: list[int] = []
    for v in valores:
        if not salida or salida[-1] != int(v):
            salida.append(int(v))
    return "→".join(map(str, salida))


def curva_de(s: float, curvas: list[dict]) -> str:
    for c in curvas:
        if c["s_ini"] - 15 <= s <= c["s_fin"] + 15:
            return f"C{c['id']}"
    return "recta"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("log", type=Path)
    ap.add_argument("--lado", choices=("izq", "dcha"), required=True)
    ap.add_argument("--desfase", type=float, required=True, help="t_log = t_vídeo + desfase (sincronia.py o sincronia_giro.py)")
    ap.add_argument("--bordes", type=Path, default=vl.BORDES)
    ap.add_argument("--mapa", type=Path, default=vl.MAPA)
    ap.add_argument("--umbral", type=float, default=0.5)
    ap.add_argument("--video", type=Path)
    ap.add_argument("--fotogramas", type=Path)
    a = ap.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    ruedas, signo = (LEFT_WHEELS, -1.0) if a.lado == "izq" else (RIGHT_WHEELS, 1.0)
    d = vl.leer(a.log)
    mapa = Mapa.cargar(a.mapa)
    lim = Mapa.cargar(a.bordes)
    cruces = vl.cruces(d, mapa, ruedas, signo, lim.borde_izq if a.lado == "izq" else lim.borde_dcha)
    curvas_json = Path(a.mapa).with_name("curvas.json")
    curvas = json.loads(curvas_json.read_text(encoding="utf-8"))["curvas"] if curvas_json.exists() else []
    s_map, _ = mapa.xz_a_sn(d["x"], d["z"], s_hint=d["s"])
    grupos = agrupar(cruces, a.umbral)
    print(f"{len(cruces)} cruces, {sum(len(g) for g in grupos)} a más de {a.umbral:g} m del límite, en {len(grupos)} tramos")
    if a.fotogramas:
        a.fotogramas.mkdir(parents=True, exist_ok=True)
    for k, g in enumerate(grupos, 1):
        s0, s1 = g[0]["s"], g[-1]["s"]
        idx = np.where((s_map >= s0 - 12) & (s_map <= s1 + 12) & (d["v"] > 5))[0]
        j = int(np.argmin(np.abs(s_map - s0)))
        t_video = float(d["t"][j]) - a.desfase
        curva = curva_de(s0, curvas)
        errores = " ".join(f"{c['error']:+.1f}" for c in g)
        print(f"{k:2d}  vídeo {int(t_video // 60)}:{t_video % 60:04.1f}  {s0:5.0f}-{s1:5.0f} m  {curva:6s} err[{errores}]  rueda delantera {secuencia(d['terreno'][idx, ruedas[0]])}  trasera {secuencia(d['terreno'][idx, ruedas[1]])}")
        if a.video and a.fotogramas:
            import cv2  # noqa: PLC0415

            cap = cv2.VideoCapture(str(a.video))
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t_video * cap.get(cv2.CAP_PROP_FPS))))
            ok, fot = cap.read()
            cap.release()
            if ok:
                cv2.imwrite(str(a.fotogramas / f"{k:02d}_{curva}_{s0:.0f}m.jpg"), fot, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return 0


if __name__ == "__main__":
    sys.exit(main())
