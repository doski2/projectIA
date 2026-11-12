"""Comprueba que una grabación de la vuelta es utilizable (D2 de docs/DECISIONES.md).

Uso:  python video_vuelta/src/comprobar_video.py <video.mp4> [--esperado 1920x1080] [--fps 60]

Mira, leyendo el vídeo entero en orden:
  * resolución y fps frente a lo acordado;
  * regularidad de los fotogramas (huecos mayores que 1,5 periodos = fotogramas perdidos);
  * fotogramas «rotos»: imagen casi plana y clara, que es lo que sale cuando se pierde un fotograma de
    referencia y el decodificador solo dibuja las diferencias (ocurrió el 2026-11-08 en la prueba de
    las 12:28: bien hasta 8,7 s y roto el 94 % restante).
Sale con código 1 si algo no cumple.
"""
from __future__ import annotations

import argparse
import io
import sys

import cv2
import numpy as np


def _roto(gris: np.ndarray) -> bool:
    """Franja central (carretera) casi plana y clara."""
    h = gris.shape[0]
    medio = gris[int(0.30 * h):int(0.75 * h)]
    return bool(np.median(medio) > 160 and medio.std() < 25)


def comprobar(ruta: str, esperado: tuple[int, int], fps_esperado: float) -> dict:
    cap = cv2.VideoCapture(ruta, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        return {"abierto": False}
    ancho, alto = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ts: list[float] = []
    rotos: list[bool] = []
    while True:
        ok, fot = cap.read()
        if not ok:
            break
        ts.append(cap.get(cv2.CAP_PROP_POS_MSEC))
        rotos.append(_roto(cv2.cvtColor(fot[::4, ::4], cv2.COLOR_BGR2GRAY)))
    cap.release()
    t = np.array(ts)
    d = np.diff(t)
    periodo = 1000.0 / fps_esperado
    huecos = [(round(float(t[i]) / 1000, 2), round(float(d[i]), 1)) for i in np.where(d > 1.5 * periodo)[0]]
    rotos_a = np.array(rotos)
    primero_roto = float(t[int(np.argmax(rotos_a))] / 1000) if rotos_a.any() else None
    return {
        "abierto": True,
        "resolucion": (ancho, alto),
        "resolucion_ok": (ancho, alto) == esperado,
        "duracion_s": float(t[-1] / 1000) if len(t) else 0.0,
        "fotogramas": len(t),
        "regulares_pct": float(100 * np.mean(np.abs(d - periodo) < 1.0)) if len(d) else 0.0,
        "huecos": huecos,
        "rotos_pct": float(100 * rotos_a.mean()) if len(rotos_a) else 0.0,
        "primer_roto_s": primero_roto,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--esperado", default="1920x1080")
    ap.add_argument("--fps", type=float, default=60.0)
    a = ap.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    ancho, alto = (int(x) for x in a.esperado.lower().split("x"))
    r = comprobar(a.video, (ancho, alto), a.fps)
    if not r["abierto"]:
        print("NO SE PUEDE ABRIR el vídeo")
        return 1
    print(f"resolución {r['resolucion'][0]}x{r['resolucion'][1]}  ({'OK' if r['resolucion_ok'] else 'NO es ' + a.esperado})")
    print(f"duración {r['duracion_s']:.1f} s, {r['fotogramas']} fotogramas, {r['regulares_pct']:.1f} % a periodo exacto")
    print(f"huecos (fotogramas perdidos): {len(r['huecos'])}  {r['huecos'][:10]}")
    if r["rotos_pct"] > 1.0:
        print(f"ROTO: {r['rotos_pct']:.0f} % de los fotogramas, desde {r['primer_roto_s']:.1f} s")
    else:
        print("sin fotogramas rotos")
    ok = r["resolucion_ok"] and r["rotos_pct"] <= 1.0
    print("RESULTADO:", "utilizable" if ok else "NO utilizable")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
