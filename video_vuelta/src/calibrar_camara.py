"""Calibra la cámara (altura, cabeceo y distancia al punto del log) con la línea de meta en los cruces del vídeo (D5 y D9 de docs/DECISIONES.md).

Uso:
    python video_vuelta/src/calibrar_camara.py <manifiesto.json> [--escribir]

Para cada cruce de meta del log (cambio de vuelta) toma los fotogramas de los 3 s anteriores, si la velocidad fue casi constante, mide la fila de la línea de
meta (la fila con más blanco en el centro de la imagen) y los metros que le quedan al coche hasta el cruce (el log). Con eso ajusta altura, cabeceo y
`atras_m` (`camara.ajustar_altura_cabeceo`) con el campo de visión del manifiesto. No sirve la salida desde parado: el coche se «sienta» al acelerar.
Con `--escribir` guarda `camara_modelo` en el manifiesto. Hay que repetirlo cuando cambia el campo de visión, el coche o la cámara.
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

from video_vuelta.src.camara import Camara, ajustar_altura_cabeceo, camara_de_manifiesto  # noqa: E402
from video_vuelta.src.sincronia import leer_log  # noqa: E402

ANTES_S, DESPUES_S = 3.0, 0.8  # ventana de fotogramas alrededor del cruce (la línea sigue a la vista ≈ 3 m, ≈ 0,4 s, después del cruce del log: la cámara va detrás)
VARIACION_MAX_KMH = 2.0  # la velocidad no puede variar más que esto en la ventana
PICO_MIN = 0.5  # fracción de blanco que debe tener la fila de la línea de meta
FILA_MAX = 880  # por debajo empieza el capó


def metros_restantes(log, t_cruce: float, t_log: np.ndarray) -> np.ndarray:
    """Metros que le quedan al coche hasta el instante del cruce, en cada instante de `t_log`."""
    v = log.velocidad_kmh / 3.6
    dist = np.concatenate([[0.0], np.cumsum(0.5 * (v[1:] + v[:-1]) * np.diff(log.t_s))])
    return float(np.interp(t_cruce, log.t_s, dist)) - np.interp(t_log, log.t_s, dist)


def fila_de_meta(bgr: np.ndarray, cam: Camara) -> tuple[float, float] | None:
    """(fila, fracción de blanco) de la línea transversal más marcada en el centro de la imagen, o None."""
    h, w = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    arriba = int(cam.horizonte_v) + 15
    zona = ((hsv[..., 2] > 190) & (hsv[..., 1] < 45))[arriba:FILA_MAX, int(0.2 * w):int(0.8 * w)]
    perfil = zona.mean(axis=1)
    k = int(np.argmax(perfil))
    if perfil[k] < PICO_MIN:
        return None
    lo, hi = max(0, k - 3), min(len(perfil), k + 4)
    peso = perfil[lo:hi]
    return arriba + float((np.arange(lo, hi) * peso).sum() / peso.sum()), float(perfil[k])


def calibrar(manifiesto: Path) -> tuple[Camara, dict]:
    man = json.loads(Path(manifiesto).read_text(encoding="utf-8"))
    base = camara_de_manifiesto({k: v for k, v in man.items() if k != "camara_modelo"})  # parte del campo de visión, no de una calibración previa
    log = leer_log(REPO / man["log"])
    desfase = float(man["sincronia"]["desfase_s"])
    cruces = np.where(np.diff(log.vuelta) > 0)[0]
    if len(cruces) == 0:
        raise ValueError("el log no cruza la meta: hace falta al menos una vuelta completa")
    cap = cv2.VideoCapture(man["video"], cv2.CAP_FFMPEG)
    filas, resto, evento, eventos = [], [], [], []
    for i in cruces:
        t_c = float(log.t_s[i + 1])
        ventana = (log.t_s > t_c - ANTES_S) & (log.t_s < t_c)
        v = log.velocidad_kmh[ventana]
        if len(v) == 0 or v.max() - v.min() > VARIACION_MAX_KMH:
            eventos.append({"t_log_s": round(t_c, 2), "usado": False, "motivo": "velocidad no constante"})
            continue
        cap.set(cv2.CAP_PROP_POS_MSEC, (t_c - desfase - ANTES_S) * 1000.0)
        n0 = len(filas)
        while True:
            t_v = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if t_v > t_c - desfase + DESPUES_S:
                break
            ok, fot = cap.read()
            if not ok:
                break
            r = fila_de_meta(fot, base)
            if r is None or r[0] >= FILA_MAX - 5:
                continue
            filas.append(r[0])
            evento.append(len(eventos))
            resto.append(float(metros_restantes(log, t_c, np.array([t_v + desfase]))[0]))
        eventos.append({"t_log_s": round(t_c, 2), "usado": True, "fotogramas": len(filas) - n0})
    cap.release()
    if len(filas) < 15:
        raise ValueError(f"solo {len(filas)} fotogramas con la línea de meta: no basta para calibrar")
    cam, info = ajustar_altura_cabeceo(np.array(filas), np.array(resto), base, evento=np.array(evento))
    info.update({"eventos": eventos, "fov_h_deg": base.fov_h_deg, "horizonte_v": round(cam.horizonte_v, 1)})
    return cam, info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("manifiesto", type=Path)
    ap.add_argument("--escribir", action="store_true", help="guarda `camara_modelo` en el manifiesto")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cam, info = calibrar(a.manifiesto)
    print(f"altura {cam.altura_m:.3f} m, cabeceo {np.degrees(cam.cabeceo_rad):.2f}°, cámara {cam.atras_m:.2f} m por detrás del punto del log; "
          f"campo de visión {cam.fov_h_deg:g}° horizontal; horizonte en la fila {cam.horizonte_v:.0f}; rms {info['rms_px']:.2f} px con {info['n']} fotogramas "
          f"({info['descartados']} descartados); cámara por cruce: {info['atras_por_evento_m']} m")
    print("eventos:", json.dumps(info["eventos"], ensure_ascii=False))
    if a.escribir:
        man = json.loads(a.manifiesto.read_text(encoding="utf-8"))
        man["camara_modelo"] = {"fov_h_deg": cam.fov_h_deg, "altura_m": round(cam.altura_m, 4), "cabeceo_rad": round(cam.cabeceo_rad, 5),
                                "atras_m": round(cam.atras_m, 3), "ancho": cam.ancho, "alto": cam.alto}
        a.manifiesto.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("manifiesto actualizado:", a.manifiesto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
