"""Sincroniza el vídeo de una vuelta con su log por el arranque desde parado (D1 y D3 de docs/DECISIONES.md).

El coche está parado al empezar a grabar. El log dice cuándo se mueve (velocidad > umbral) y el vídeo, cuándo
cambia la imagen de la franja de carretera. La diferencia es el desfase: ``t_log = t_video + desfase``.
Con él se pasa de la distancia de vuelta del log (``lap_distance``) al instante del vídeo y se saca el
fotograma de cualquier punto de la pista. El error se mide con el cruce de meta (``comprobar_meta``).

Uso:
    python video_vuelta/src/sincronia.py <video> <log.jsonl> [--manifiesto <manifiesto.json>]
    python video_vuelta/src/sincronia.py <video> <log.jsonl> --fotograma 259 --salida apice_c1.jpg

No toca el juego ni la telemetría: solo lee los dos archivos.
"""

from __future__ import annotations

import argparse
import json
import io
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

try:  # OpenCV solo hace falta para leer vídeo; las funciones sobre arrays no lo necesitan
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

UMBRAL_LOG_KMH = 1.0  # velocidad a partir de la cual el coche «se mueve» en el log
UMBRAL_VIDEO = 2.0  # energía de movimiento (diferencia media de grises entre fotogramas) que cuenta como movimiento
FOTOGRAMAS_SEGUIDOS = 10  # el movimiento del vídeo debe mantenerse este número de fotogramas
FRANJA = (0.40, 0.66)  # filas del fotograma (fracción de la altura) donde se mide el movimiento: la carretera


@dataclass
class LogVuelta:
    """Lo que hace falta de un log de sesión: instante, velocidad, vuelta y distancia de vuelta de cada tick."""

    t_s: np.ndarray
    velocidad_kmh: np.ndarray
    vuelta: np.ndarray
    distancia_m: np.ndarray


def leer_log(ruta: str | Path) -> LogVuelta:
    t, v, vu, d = [], [], [], []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            r = json.loads(linea)
            if r.get("type") == "tick":
                t.append(r["t_s"])
                v.append(r["speed_kmh"])
                vu.append(r["lap"])
                d.append(r["lap_distance"])
    if not t:
        raise ValueError(f"el log {ruta} no tiene ticks")
    return LogVuelta(np.array(t, float), np.array(v, float), np.array(vu, int), np.array(d, float))


def energia_movimiento(ruta_video: str | Path, franja: tuple[float, float] = FRANJA):
    """Devuelve (t_video_s, energia) por fotograma: diferencia media de grises con el anterior en la franja de carretera."""
    if cv2 is None:  # pragma: no cover
        raise RuntimeError("falta opencv-python-headless")
    cap = cv2.VideoCapture(str(ruta_video), cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise ValueError(f"no se puede abrir {ruta_video}")
    ts, en, previo = [], [], None
    while True:
        ok, fot = cap.read()
        if not ok:
            break
        alto = fot.shape[0]
        g = cv2.cvtColor(fot[int(franja[0] * alto):int(franja[1] * alto):2, ::2], cv2.COLOR_BGR2GRAY).astype(np.float32)
        ts.append(cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0)
        en.append(0.0 if previo is None else float(np.mean(np.abs(g - previo))))
        previo = g
    cap.release()
    return np.array(ts), np.array(en)


def arranque_log(log: LogVuelta, umbral_kmh: float = UMBRAL_LOG_KMH) -> float:
    """Primer instante del log con velocidad por encima del umbral."""
    i = np.where(log.velocidad_kmh > umbral_kmh)[0]
    if len(i) == 0:
        raise ValueError("el coche no se mueve en el log")
    return float(log.t_s[i[0]])


def arranque_video(ts: np.ndarray, energia: np.ndarray, umbral: float = UMBRAL_VIDEO, seguidos: int = FOTOGRAMAS_SEGUIDOS) -> float:
    """Primer instante en que la energía de movimiento supera el umbral durante ``seguidos`` fotogramas seguidos."""
    if len(energia) < seguidos:
        raise ValueError("vídeo demasiado corto")
    sobre = (energia > umbral).astype(int)
    ventana = np.convolve(sobre, np.ones(seguidos, int), "valid")
    k = np.where(ventana == seguidos)[0]
    if len(k) == 0:
        raise ValueError("no se ve arrancar el coche en el vídeo")
    return float(ts[k[0]])


def instante_de_distancia(log: LogVuelta, s_m: float, vuelta: int = 1) -> float:
    """Instante del log (s) en que se alcanza la distancia de vuelta ``s_m`` en la vuelta indicada."""
    i = np.where((log.vuelta == vuelta) & (log.distancia_m >= s_m))[0]
    if len(i) == 0:
        raise ValueError(f"la vuelta {vuelta} no llega a {s_m} m")
    return float(log.t_s[i[0]])


def cruce_de_meta(log: LogVuelta) -> Optional[float]:
    """Instante del log en que cambia la vuelta (cruce de la meta), o None si no la cruza."""
    i = np.where(np.diff(log.vuelta) > 0)[0]
    return float(log.t_s[i[0] + 1]) if len(i) else None


def sincronizar(ts: np.ndarray, energia: np.ndarray, log: LogVuelta) -> dict:
    """Desfase por el arranque desde parado: ``t_log = t_video + desfase_s``."""
    t_video0 = arranque_video(ts, energia)
    t_log0 = arranque_log(log)
    meta = cruce_de_meta(log)
    return {
        "metodo": "arranque_desde_parado",
        "t_video_s": round(t_video0, 3),
        "t_log_s": round(t_log0, 3),
        "desfase_s": round(t_log0 - t_video0, 3),
        "cruce_de_meta_t_log_s": None if meta is None else round(meta, 3),
        "cruce_de_meta_t_video_s": None if meta is None else round(meta - (t_log0 - t_video0), 3),
        "duracion_video_s": round(float(ts[-1]), 3),
    }


def t_video_de_distancia(sinc: dict, log: LogVuelta, s_m: float, vuelta: int = 1) -> float:
    """Instante del vídeo en que el coche está en la distancia de vuelta ``s_m``."""
    return instante_de_distancia(log, s_m, vuelta) - sinc["desfase_s"]


def guardar_fotograma(ruta_video: str | Path, t_video_s: float, salida: str | Path) -> None:
    if cv2 is None:  # pragma: no cover
        raise RuntimeError("falta opencv-python-headless")
    cap = cv2.VideoCapture(str(ruta_video), cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_POS_MSEC, t_video_s * 1000.0)
    ok, fot = cap.read()
    cap.release()
    if not ok:
        raise ValueError(f"no hay fotograma en t = {t_video_s:.2f} s")
    cv2.imwrite(str(salida), fot)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("log")
    ap.add_argument("--manifiesto", help="manifiesto.json donde escribir el bloque «sincronia»")
    ap.add_argument("--fotograma", type=float, metavar="S_M", help="guarda el fotograma de esa distancia de vuelta (m)")
    ap.add_argument("--salida", default="fotograma.jpg")
    a = ap.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    log = leer_log(a.log)
    ts, en = energia_movimiento(a.video)
    sinc = sincronizar(ts, en, log)
    print(json.dumps(sinc, indent=2, ensure_ascii=False))
    if a.manifiesto:
        p = Path(a.manifiesto)
        man = json.loads(p.read_text(encoding="utf-8"))
        man["sincronia"] = sinc
        p.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("manifiesto actualizado:", p)
    if a.fotograma is not None:
        t = t_video_de_distancia(sinc, log, a.fotograma)
        guardar_fotograma(a.video, t, a.salida)
        print(f"fotograma de s = {a.fotograma:.0f} m (t_video = {t:.2f} s) -> {a.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
