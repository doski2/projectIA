"""Etiquetas automáticas de «pasillo» para entrenar un segmentador (D7 de docs/DECISIONES.md).

Con el mapa de la pista, sus límites medidos (`borde_izq` / `borde_dcha` en `n`), la posición y el rumbo del coche en cada fotograma y la cámara,
se proyecta el pasillo sobre la imagen: es la máscara «calzada legal» sin etiquetar nada a mano. Sirve para cualquier pista que tenga mapa y límites,
y, dibujada sobre el fotograma, valida toda la cadena (cámara, rumbo, mapa y constantes): si el límite cae donde se ve el borde, todo cuadra.

La proyección usa la altura del mapa (cuestas): un punto de la calzada está por debajo de la cámara `altura − (y_punto − y_coche − pendiente · Z)`.
"""
from __future__ import annotations

import numpy as np

from circuito_virtual.src.mapa import Mapa
from video_vuelta.src.camara import Camara


def borde_en_imagen(cam: Camara, mapa: Mapa, pose: tuple, n_borde: np.ndarray, delante_m: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(u, v, Z) de un borde `n_borde` (un valor por punto del mapa) en los puntos `delante_m` metros por delante del coche a lo largo de la pista.

    `pose` = (x, z, rumbo, s) del coche. Los puntos sin dato, detrás de la cámara o por encima del horizonte salen como NaN."""
    x, z, rumbo, s_coche = pose[0], pose[1], pose[2], pose[3]
    s = s_coche + np.asarray(delante_m, dtype=float)
    n = mapa.interpola(n_borde, s)
    wx, wz = mapa.sn_a_xz(s, n)
    dx, dz = wx - x, wz - z
    Z = dx * np.sin(rumbo) + dz * np.cos(rumbo) + cam.atras_m  # hacia delante de la cámara
    X = dx * np.cos(rumbo) - dz * np.sin(rumbo)
    y_coche = float(mapa.interpola(mapa.y, s_coche))
    pendiente = float(mapa.interpola(mapa.pendiente, s_coche))
    sube = mapa.interpola(mapa.y, s) - y_coche - pendiente * Z  # cuánto está el punto sobre el plano de la calzada bajo el coche
    u, v = cam.pixel(np.where(Z > 0.5, Z, np.nan), X, abajo_m=cam.altura_m - sube)
    return u, v, Z


def poligono_pasillo(cam: Camara, mapa: Mapa, pose: tuple, izq: np.ndarray, dcha: np.ndarray, hasta_m: float = 60.0, paso_m: float = 1.0):
    """Polígono (N, 2) del pasillo entre los dos bordes, o None si no se ve. Recorta a la imagen por arriba (horizonte) y por los lados."""
    delante = np.arange(-cam.atras_m + 0.6, hasta_m, paso_m)
    ui, vi, _ = borde_en_imagen(cam, mapa, pose, izq, delante)
    ud, vd, _ = borde_en_imagen(cam, mapa, pose, dcha, delante)
    ok = np.isfinite(ui) & np.isfinite(vi) & np.isfinite(ud) & np.isfinite(vd) & (vi > cam.horizonte_v - 40)
    if ok.sum() < 3:
        return None
    ui, vi, ud, vd = ui[ok], vi[ok], ud[ok], vd[ok]
    return np.concatenate([np.stack([ui, vi], 1), np.stack([ud, vd], 1)[::-1]])


def mascara_pasillo(cam: Camara, mapa: Mapa, pose: tuple, izq: np.ndarray, dcha: np.ndarray, forma: tuple[int, int] = (1080, 1920),
                    hasta_m: float = 60.0) -> np.ndarray:
    """Máscara uint8 de la imagen completa: 1 = dentro del pasillo, 0 = fuera, 255 = carrocería del coche (ignorar al entrenar)."""
    import cv2

    alto, ancho = forma
    m = np.zeros((alto, ancho), np.uint8)
    poli = poligono_pasillo(cam, mapa, pose, izq, dcha, hasta_m)
    if poli is not None:
        cv2.fillPoly(m, [np.clip(np.round(poli), -50000, 50000).astype(np.int32)], 1)
    m[carroceria(forma)] = 255
    return m


def carroceria(forma: tuple[int, int] = (1080, 1920)) -> np.ndarray:
    """Zona fija de la imagen que ocupan el morro y las ruedas delanteras de la cámara de capó (la cámara va rígida al chasis)."""
    alto, ancho = forma
    ys, xs = np.mgrid[0:alto, 0:ancho]
    f, c = ys / alto, xs / ancho
    morro = (f > 0.79) & (c > 0.33) & (c < 0.68)
    rueda_izq = (f > 0.78) & (c < 0.22)
    rueda_dcha = (f > 0.78) & (c > 0.79)
    return morro | rueda_izq | rueda_dcha
