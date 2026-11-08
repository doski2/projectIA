"""Detección de la línea blanca del borde en un fotograma de la cámara de capó (D5 de docs/DECISIONES.md).

Una línea blanca de la pista es una franja clara y poco saturada de 5-30 cm de ancho. Las franjas del piano, el
cielo y los muros son blancos pero mucho más anchos: se descartan por el ancho que tendrían en metros a esa
distancia (se calcula con la cámara). De los candidatos de todas las filas se queda, a cada lado, la recta sobre el
suelo (X = a + b·Z, en el sistema del coche) con más puntos que la apoyan.

No hace nada con el juego ni con el log: recibe un fotograma BGR y una `Camara`.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from video_vuelta.src.camara import Camara

V_MIN = 185  # brillo mínimo del blanco
S_MAX = 50  # saturación máxima del blanco
ANCHO_M = (0.04, 0.35)  # ancho que debe tener la franja sobre el suelo
FILAS = tuple(range(500, 830, 6))  # entre ≈ 12 m y ≈ 3,4 m por delante con la cámara de Sugo (el capó empieza hacia la fila 850)
TOLERANCIA_M = 0.06  # distancia de un punto a la recta para contar como apoyo
MIN_PUNTOS = 8
PENDIENTE_MAX = 0.5  # |dX/dZ|: la línea va más o menos paralela al coche


@dataclass
class Linea:
    """Recta X = a + b·Z sobre el suelo (ejes del coche, origen en la cámara) y los puntos que la apoyan."""

    a: float
    b: float
    Z: np.ndarray
    X: np.ndarray

    def x_en(self, Z):
        return self.a + self.b * np.asarray(Z, dtype=float)


def mascara_blanca(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return (hsv[..., 2] >= V_MIN) & (hsv[..., 1] <= S_MAX)


def _tramos(fila: np.ndarray) -> list[tuple[int, int]]:
    """Tramos [ini, fin) de True consecutivos (se cierran huecos de 1 píxel)."""
    f = fila.copy()
    f[1:-1] |= fila[:-2] & fila[2:]
    d = np.diff(np.concatenate([[0], f.astype(np.int8), [0]]))
    return list(zip(np.where(d == 1)[0].tolist(), np.where(d == -1)[0].tolist()))


def candidatos(mascara: np.ndarray, cam: Camara, filas=FILAS, ancho_m=ANCHO_M) -> tuple[np.ndarray, np.ndarray]:
    """Puntos (Z, X) del suelo cuya franja blanca tiene un ancho de línea. Una fila puede dar varios."""
    Zs, Xs = [], []
    for v in filas:
        ppm = float(cam.px_por_metro(v))
        if not np.isfinite(ppm):
            continue
        lo, hi = max(2.0, ancho_m[0] * ppm), ancho_m[1] * ppm
        for ini, fin in _tramos(mascara[v]):
            if lo <= fin - ini <= hi:
                Z, X = cam.suelo((ini + fin - 1) / 2.0, v)
                Zs.append(float(Z))
                Xs.append(float(X))
    return np.array(Zs), np.array(Xs)


def _mejor_recta(Z: np.ndarray, X: np.ndarray, tol: float, min_puntos: int, pendiente_max: float) -> Linea | None:
    """La recta más cercana al coche entre las bien apoyadas (≥ la mitad de apoyos que la mejor).

    El borde de la pista es la línea blanca más cercana a cada lado; otras líneas blancas más lejos (pit lane, muros pintados)
    pueden tener más puntos pero no son el borde."""
    n = len(Z)
    if n < min_puntos:
        return None
    modelos: list[tuple[int, float, float, float]] = []  # apoyos, a, b, |a|
    paso = max(1, n // 40)
    for i in range(0, n, paso):
        for j in range(i + 1, n, paso):
            if abs(Z[j] - Z[i]) < 1.0:
                continue
            b = (X[j] - X[i]) / (Z[j] - Z[i])
            if abs(b) > pendiente_max:
                continue
            a = X[i] - b * Z[i]
            k = int((np.abs(X - (a + b * Z)) <= tol).sum())
            if k >= min_puntos:
                modelos.append((k, a, b, abs(a)))
    if not modelos:
        return None
    mejor_k = max(m[0] for m in modelos)
    buenos = [m for m in modelos if m[0] >= max(min_puntos, 0.5 * mejor_k)]
    a0 = min(m[3] for m in buenos)
    cluster = [m for m in buenos if m[3] <= a0 + 0.3]  # la misma línea vista desde distintas parejas
    k, a, b, _ = max(cluster, key=lambda m: m[0])
    dentro = np.abs(X - (a + b * Z)) <= tol
    b, a = np.polyfit(Z[dentro], X[dentro], 1)  # ajuste fino con todos los apoyos
    dentro = np.abs(X - (a + b * Z)) <= tol
    if dentro.sum() < min_puntos:
        return None
    b, a = np.polyfit(Z[dentro], X[dentro], 1)
    return Linea(float(a), float(b), Z[dentro], X[dentro])


def lineas_del_fotograma(bgr: np.ndarray, cam: Camara, filas=FILAS, tol: float = TOLERANCIA_M, min_puntos: int = MIN_PUNTOS,
                         pendiente_max: float = PENDIENTE_MAX) -> dict[str, Linea | None]:
    """Línea blanca de cada lado (``izq`` con X < 0, ``dcha`` con X > 0) o None si no se ve con claridad."""
    Z, X = candidatos(mascara_blanca(bgr), cam, filas)
    lineas: dict[str, Linea | None] = {}
    for lado, sel in (("izq", X < -0.3), ("dcha", X > 0.3)):
        lineas[lado] = _mejor_recta(Z[sel], X[sel], tol, min_puntos, pendiente_max)
    return lineas
