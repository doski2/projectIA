"""Modelo de la cámara de capó (D5 de docs/DECISIONES.md): del píxel al suelo y del suelo al píxel.

Cámara estenopeica (campo de visión horizontal conocido) a ``altura_m`` sobre una calzada plana, inclinada
``cabeceo_rad`` hacia abajo, sin alabeo ni guiñada respecto al coche. Ejes del coche: Z hacia delante, X hacia la
derecha. ``atras_m`` es lo que la cámara queda por detrás del punto que el log llama «posición» (la línea de meta se
cruza en el log cuando está a ``atras_m`` por delante de la cámara).

Calibración (``ajustar_altura_cabeceo``): la fila de una línea del suelo que se acerca, frente a los metros que le
quedan al coche hasta el instante de referencia, da la altura, el cabeceo y ``atras_m``. Se usa la línea de meta en
los cruces a velocidad constante; la salida desde parado no vale (el coche se «sienta» al acelerar y cambia el cabeceo).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np


@dataclass(frozen=True)
class Camara:
    ancho: int = 1920
    alto: int = 1080
    fov_h_deg: float = 70.0
    altura_m: float = 1.02
    cabeceo_rad: float = float(np.radians(5.98))
    atras_m: float = 3.01
    cx: float | None = None
    cy: float | None = None

    @property
    def f(self) -> float:
        """Focal en píxeles (la misma en horizontal y en vertical: píxeles cuadrados)."""
        return (self.ancho / 2.0) / float(np.tan(np.radians(self.fov_h_deg / 2.0)))

    @property
    def c(self) -> tuple[float, float]:
        return (self.ancho / 2.0 if self.cx is None else self.cx, self.alto / 2.0 if self.cy is None else self.cy)

    @property
    def horizonte_v(self) -> float:
        """Fila del horizonte (calzada plana)."""
        return self.c[1] - self.f * float(np.tan(self.cabeceo_rad))

    def profundidad(self, v):
        """Distancia a lo largo del eje óptico a la que el suelo corta la fila ``v`` (NaN por encima del horizonte)."""
        v = np.asarray(v, dtype=float)
        ay = (v - self.c[1]) / self.f
        den = np.sin(self.cabeceo_rad) + ay * np.cos(self.cabeceo_rad)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(den > 1e-6, self.altura_m / den, np.nan)

    def suelo(self, u, v):
        """Píxel -> suelo: (Z adelante, X derecha) en metros respecto a la cámara. NaN por encima del horizonte."""
        u, v = np.asarray(u, dtype=float), np.asarray(v, dtype=float)
        ax = (u - self.c[0]) / self.f
        ay = (v - self.c[1]) / self.f
        t = self.profundidad(v)
        return t * (np.cos(self.cabeceo_rad) - ay * np.sin(self.cabeceo_rad)), t * ax

    def pixel(self, Z, X, abajo_m=None):
        """Suelo -> píxel: (u, v) de un punto a Z metros delante y X metros a la derecha de la cámara.

        ``abajo_m``: cuánto por debajo de la cámara está el punto (por defecto la altura de la cámara: calzada plana). Con cuestas es
        la altura de la cámara menos lo que el punto sube sobre el plano de la calzada bajo el coche."""
        Z, X = np.asarray(Z, dtype=float), np.asarray(X, dtype=float)
        th = self.cabeceo_rad
        h = self.altura_m if abajo_m is None else np.asarray(abajo_m, dtype=float)
        yc = h * np.cos(th) - Z * np.sin(th)
        zc = Z * np.cos(th) + h * np.sin(th)
        with np.errstate(divide="ignore", invalid="ignore"):
            return self.c[0] + self.f * X / zc, self.c[1] + self.f * yc / zc

    def px_por_metro(self, v):
        """Píxeles por metro lateral en la fila ``v`` (cambia con la distancia)."""
        return self.f / self.profundidad(v)


def _levenberg(resid, p0, iteraciones: int = 200) -> np.ndarray:
    p = np.array(p0, dtype=float)
    lam = 1e-3
    for _ in range(iteraciones):
        r0 = resid(p)
        J = np.empty((len(r0), len(p)))
        for k in range(len(p)):
            dp = np.zeros(len(p))
            dp[k] = 1e-6
            J[:, k] = (resid(p + dp) - r0) / 1e-6
        A = J.T @ J
        paso = np.linalg.solve(A + lam * np.diag(np.diag(A)) + 1e-12 * np.eye(len(p)), -J.T @ r0)
        if np.sum(resid(p + paso) ** 2) < np.sum(r0 ** 2):
            p, lam = p + paso, lam * 0.5
        else:
            lam *= 4.0
    return p


def ajustar_altura_cabeceo(filas_px, restante_m, base: Camara | None = None, inicial=(0.9, 0.05, 4.0), evento=None) -> tuple[Camara, dict]:
    """Ajusta altura, cabeceo y ``atras_m`` con las filas de una línea del suelo que se acerca.

    ``filas_px``: fila (v) de la línea en cada fotograma; ``restante_m``: metros que le quedan al coche, según el log,
    hasta el instante de referencia (el cruce de meta del log) en ese fotograma. ``evento``: a qué cruce pertenece cada fotograma; el instante
    del cruce solo se conoce a ±1 tick del log (±0,14 m a 30 km/h, y cerca de la cámara son ≈ 20 px), así que cada cruce tiene su propio
    ``atras_m`` y la cámara lleva la media. Devuelve la cámara y el residuo.
    """
    base = base or Camara()
    v, r = np.asarray(filas_px, dtype=float), np.asarray(restante_m, dtype=float)
    ev = np.zeros(len(v), dtype=int) if evento is None else np.unique(np.asarray(evento), return_inverse=True)[1]
    n_ev = int(ev.max()) + 1
    cy = base.c[1]

    def predecir(p, r_, ev_):
        h, th, zc = p[0], p[1], np.asarray(p[2:])[ev_]
        return cy + base.f * np.tan(np.arctan2(h, np.maximum(zc + r_, 0.2)) - th)

    p0 = np.concatenate([inicial[:2], np.full(n_ev, inicial[2])])
    p = _levenberg(lambda q: predecir(q, r, ev) - v, p0)
    res = predecir(p, r, ev) - v
    usados = np.ones(len(v), dtype=bool)
    for _ in range(3):  # recorta los fotogramas donde la «línea» era otra cosa y reajusta
        umbral = max(2.0, 3.0 * 1.4826 * float(np.median(np.abs(res[usados]))))
        nuevos = np.abs(res) <= umbral
        if nuevos.sum() < 10 or (nuevos == usados).all():
            break
        usados = nuevos
        p = _levenberg(lambda q: predecir(q, r[usados], ev[usados]) - v[usados], p)
        res = predecir(p, r, ev) - v
    cam = replace(base, altura_m=float(p[0]), cabeceo_rad=float(p[1]), atras_m=float(np.mean(p[2:])))
    return cam, {"rms_px": float(np.sqrt(np.mean(res[usados] ** 2))), "n": int(usados.sum()), "descartados": int((~usados).sum()),
                 "atras_por_evento_m": [round(float(z), 3) for z in p[2:]]}


def camara_de_manifiesto(man: dict) -> Camara:
    """Cámara de un manifiesto: `camara_modelo` (calibrada) si lo trae; si no, el campo de visión y la resolución del manifiesto y lo demás por defecto."""
    campos = dict(man.get("camara_modelo") or {})
    if "fov_h_deg" not in campos and man.get("campo_de_vision_horizontal_deg"):
        campos["fov_h_deg"] = float(man["campo_de_vision_horizontal_deg"])
    if man.get("resolucion") and "ancho" not in campos:
        campos["ancho"], campos["alto"] = int(man["resolucion"][0]), int(man["resolucion"][1])
    return Camara(**campos)
