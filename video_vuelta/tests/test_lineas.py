"""Tests de `lineas.py` con fotogramas sintéticos dibujados con la propia cámara."""

import cv2
import numpy as np

from video_vuelta.src import lineas as ln
from video_vuelta.src.camara import Camara

CAM = Camara(altura_m=1.0, cabeceo_rad=0.104)


def _franja(img, cam, x0, x1, z0=3.0, z1=40.0, color=(245, 245, 245), pendiente=0.0):
    """Dibuja una franja del suelo entre x0 y x1 (m, a la izquierda negativo) con una pendiente dX/dZ."""
    Z = np.linspace(z0, z1, 120)
    ui, vi = cam.pixel(Z, x0 + pendiente * Z)
    ud, vd = cam.pixel(Z, x1 + pendiente * Z)
    pts = np.concatenate([np.stack([ui, vi], 1), np.stack([ud, vd], 1)[::-1]])
    cv2.fillPoly(img, [np.round(pts).astype(np.int32)], color)


def _escena(cam=CAM):
    img = np.full((1080, 1920, 3), 90, np.uint8)
    img[: int(cam.horizonte_v)] = (200, 190, 180)  # cielo azulado, no blanco puro
    return img


def test_detecta_las_dos_lineas_con_su_lateral():
    img = _escena()
    _franja(img, CAM, -3.30, -3.18)  # línea izquierda de 12 cm
    _franja(img, CAM, 2.48, 2.60)  # línea derecha
    r = ln.lineas_del_fotograma(img, CAM)
    assert r["izq"] is not None and r["dcha"] is not None
    assert abs(r["izq"].a - (-3.24)) < 0.04 and abs(r["dcha"].a - 2.54) < 0.04
    assert abs(r["izq"].b) < 0.02


def test_ignora_franja_ancha_de_piano_y_se_queda_con_la_linea():
    img = _escena()
    _franja(img, CAM, -3.30, -3.18)  # línea
    _franja(img, CAM, -4.9, -3.6)  # franja blanca ancha (piano) al lado: no es línea
    r = ln.lineas_del_fotograma(img, CAM)
    assert r["izq"] is not None and abs(r["izq"].a - (-3.24)) < 0.04


def test_sin_lineas_devuelve_none():
    r = ln.lineas_del_fotograma(_escena(), CAM)
    assert r == {"izq": None, "dcha": None}


def test_linea_inclinada_da_pendiente():
    img = _escena()
    _franja(img, CAM, -2.9, -2.78, pendiente=0.15)
    r = ln.lineas_del_fotograma(img, CAM)
    assert r["izq"] is not None and abs(r["izq"].b - 0.15) < 0.02


def test_cielo_blanco_no_cuenta():
    img = _escena()
    img[: int(CAM.horizonte_v)] = 255
    assert ln.lineas_del_fotograma(img, CAM) == {"izq": None, "dcha": None}


def test_se_queda_con_la_linea_mas_cercana_aunque_haya_otra_mas_larga():
    """Una línea del pit lane más lejos y con más puntos no debe ganar a la del borde."""
    img = _escena()
    _franja(img, CAM, -3.30, -3.18, z0=3.0, z1=12.0)  # borde: se ve solo hasta 12 m
    _franja(img, CAM, -7.10, -6.98, z0=3.0, z1=40.0)  # pit lane: se ve mucho más lejos
    r = ln.lineas_del_fotograma(img, CAM, filas=tuple(range(440, 830, 4)))
    assert r["izq"] is not None and abs(r["izq"].a - (-3.24)) < 0.05
