"""Conjunto de entrenamiento «pasillo» a partir de un vídeo, su log y el mapa de bordes (D7 de docs/DECISIONES.md).

Uso:
    python video_vuelta/src/crear_dataset.py <manifiesto.json> [--bordes mapa_bordes_video.json] [--cada 30] [--salida data/x.npz]

Por cada N fotogramas con el coche en marcha guarda el fotograma reducido y la máscara del pasillo proyectada con `etiquetas.py`
(1 = pasillo, 0 = fuera, 255 = carrocería, que no se entrena), más la distancia de vuelta y la vuelta para poder separar entrenamiento y validación
por tramos de pista. Se salta los fotogramas donde faltan límites (la máscara sería falsa).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "PCARS2-AI" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from circuito_virtual.src.mapa import Mapa  # noqa: E402
from video_vuelta.src import bordes_video as bv  # noqa: E402
from video_vuelta.src.camara import Camara, camara_de_manifiesto  # noqa: E402
from video_vuelta.src.etiquetas import mascara_pasillo  # noqa: E402

TAM = (256, 144)  # (ancho, alto) de lo que se guarda y entrena
MIN_PUNTOS_VALIDOS = 0.8  # fracción de los puntos del pasillo por delante que deben tener límite


def _tiene_limites(mapa: Mapa, izq: np.ndarray, dcha: np.ndarray, s_coche: float, hasta_m: float = 40.0) -> bool:
    s = s_coche + np.arange(0.0, hasta_m, 1.0)
    return bool(np.mean(np.isfinite(mapa.interpola(izq, s)) & np.isfinite(mapa.interpola(dcha, s))) >= MIN_PUNTOS_VALIDOS)


def crear(manifiesto: Path, bordes: Path, cada: int, mapa: Mapa, cam: Camara | None = None) -> dict:
    man = json.loads(Path(manifiesto).read_text(encoding="utf-8"))
    cam = cam or camara_de_manifiesto(man)
    mb = Mapa.cargar(bordes)
    pose = bv.leer_pose(REPO / man["log"])
    desfase = float(man["sincronia"]["desfase_s"])
    cap = cv2.VideoCapture(man["video"], cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise ValueError(f"no se abre {man['video']}")
    imgs, masks, s_l, vuelta_l = [], [], [], []
    k = 0
    while cap.grab():
        k += 1
        if k % cada:
            continue
        ok, fot = cap.retrieve()
        if not ok:
            break
        t_log = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0 + desfase
        if t_log < pose.t[0] or t_log > pose.t[-1]:
            continue
        p = pose.en(t_log)
        if p[4] < bv.VELOCIDAD_MIN_KMH or not _tiene_limites(mapa, mb.borde_izq, mb.borde_dcha, p[3]):
            continue
        m = mascara_pasillo(cam, mb, p[:4], mb.borde_izq, mb.borde_dcha, fot.shape[:2])
        imgs.append(cv2.resize(fot, TAM, interpolation=cv2.INTER_AREA)[..., ::-1])  # RGB
        masks.append(cv2.resize(m, TAM, interpolation=cv2.INTER_NEAREST))
        s_l.append(p[3])
        vuelta_l.append(p[5])
    cap.release()
    return {"imagenes": np.array(imgs, np.uint8), "mascaras": np.array(masks, np.uint8), "s": np.array(s_l, np.float32), "vuelta": np.array(vuelta_l, np.int16)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("manifiesto", type=Path)
    ap.add_argument("--bordes", type=Path, help="mapa con los límites (por defecto mapa_bordes_video.json junto al manifiesto)")
    ap.add_argument("--cada", type=int, default=30)
    ap.add_argument("--mapa", type=Path, default=bv.MAPA)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args(argv)
    bordes = a.bordes or a.manifiesto.with_name("mapa_bordes_video.json")
    d = crear(a.manifiesto, bordes, a.cada, Mapa.cargar(a.mapa))
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(a.salida, **d)
    print(f"{len(d['imagenes'])} fotogramas -> {a.salida} ({a.salida.stat().st_size / 1e6:.0f} MB); pasillo medio {100 * np.mean(d['mascaras'][d['mascaras'] != 255]):.0f} % de los píxeles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
