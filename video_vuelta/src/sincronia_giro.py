"""Desfase vídeo-log por el giro del coche, para los vídeos cuyo log no empieza con el coche parado (D12 de docs/DECISIONES.md).

`sincronia.py` usa el arranque desde parado; si el log empieza a mitad de vuelta o el coche no se queda quieto al principio, sale un desfase falso (el 2026-11-09 dio −10,18 s
para un vídeo cuyo desfase real era +8,55 s). Aquí se compara la velocidad de giro del log (`orientation[1]`, rad/s) con el desplazamiento horizontal de la imagen entre
fotogramas (correlación de fase de una franja del horizonte): el desfase es el que más correlaciona.

Uso:
    python video_vuelta/src/sincronia_giro.py <video> <log.jsonl> [--desde 40 --hasta 200] [--manifiesto manifiesto.json]

Elegir un tramo con curvas (en una recta larga no hay giro que correlacionar). Con una correlación < 0,8 o dos máximos parecidos el desfase no es fiable. La cámara es la de
`camara.py` (70° horizontales).
"""
from __future__ import annotations

import argparse
import json
import io
import sys
from pathlib import Path

import numpy as np

try:  # pragma: no cover - opencv solo está en .venv
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

FOCAL_PX = 960 / np.tan(np.radians(35.0))  # 1920 px de ancho y 70° horizontales
FRANJA_FILAS = (150, 450)  # franja del horizonte (1080p) cuyo desplazamiento horizontal se mide
PASO_FOTOGRAMAS = 2


def velocidad_de_giro_video(ruta_video: str | Path, desde_s: float, hasta_s: float) -> tuple[np.ndarray, np.ndarray]:
    """(instantes del vídeo, rad/s) de la imagen entre fotogramas separados `PASO_FOTOGRAMAS`. El signo puede ser el contrario al del log (se mira |correlación|)."""
    if cv2 is None:  # pragma: no cover
        raise RuntimeError("falta opencv-python-headless")
    cap = cv2.VideoCapture(str(ruta_video))
    fps = cap.get(cv2.CAP_PROP_FPS)
    i0 = int(desde_s * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, i0)
    tv, dx, previo = [], [], None
    for i in range(i0, int(hasta_s * fps)):
        ok, f = cap.read()
        if not ok:
            break
        if (i - i0) % PASO_FOTOGRAMAS:
            continue
        g = cv2.cvtColor(cv2.resize(f[FRANJA_FILAS[0]:FRANJA_FILAS[1]], (480, 75)), cv2.COLOR_BGR2GRAY).astype(np.float32)
        if previo is not None:
            (sx, _), _ = cv2.phaseCorrelate(previo, g)
            tv.append(i / fps)
            dx.append(sx * 4.0)  # px reales
        previo = g
    cap.release()
    return np.array(tv), -np.array(dx) / FOCAL_PX / (PASO_FOTOGRAMAS / fps)


def velocidad_de_giro_log(ruta_log: str | Path) -> tuple[np.ndarray, np.ndarray]:
    t, yaw = [], []
    for linea in open(ruta_log, encoding="utf-8"):
        if '"type": "tick"' not in linea[:20]:
            continue
        r = json.loads(linea)
        o = (r.get("vehicle") or {}).get("orientation")
        if o:
            t.append(r["t_s"])
            yaw.append(o[1])
    t = np.array(t)
    return t, np.gradient(np.unwrap(np.array(yaw)), t)


def mejor_desfase(tv: np.ndarray, giro_video: np.ndarray, t_log: np.ndarray, giro_log: np.ndarray, rango: tuple[float, float] = (-2.0, 14.0), paso: float = 0.05) -> dict:
    """Desfase `t_log = t_video + desfase` que más correlaciona (en valor absoluto) y la lista de los mejores máximos."""
    a = giro_video - giro_video.mean()
    desfases = np.arange(rango[0], rango[1], paso)
    cs = np.empty(len(desfases))
    for k, d in enumerate(desfases):
        b = np.interp(tv + d, t_log, giro_log)
        b = b - b.mean()
        cs[k] = float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-12))
    orden = np.argsort(-np.abs(cs))[:5]
    k = int(orden[0])
    return {"metodo": "giro", "desfase_s": round(float(desfases[k]), 2), "correlacion": round(float(cs[k]), 3),
            "otros_maximos": [(round(float(desfases[j]), 2), round(float(cs[j]), 3)) for j in orden[1:]]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("log")
    ap.add_argument("--desde", type=float, default=40.0, help="segundo del vídeo desde el que se mide (un tramo con curvas)")
    ap.add_argument("--hasta", type=float, default=200.0)
    ap.add_argument("--manifiesto", help="manifiesto.json donde escribir el bloque «sincronia»")
    a = ap.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    tv, gv = velocidad_de_giro_video(a.video, a.desde, a.hasta)
    t, gl = velocidad_de_giro_log(a.log)
    res = mejor_desfase(tv, gv, t, gl)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    if abs(res["correlacion"]) < 0.8:
        print("AVISO: correlación baja; el desfase no es fiable (probar otro tramo)")
    if a.manifiesto:
        p = Path(a.manifiesto)
        man = json.loads(p.read_text(encoding="utf-8"))
        man["sincronia"] = {"metodo": "giro", "desfase_s": res["desfase_s"], "correlacion": res["correlacion"], "tramo_video_s": [a.desde, a.hasta]}
        p.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("manifiesto actualizado:", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
