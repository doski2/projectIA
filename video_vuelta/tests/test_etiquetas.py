"""Tests de `etiquetas.py`: el pasillo proyectado cae entre las líneas y la carrocería se ignora."""

import numpy as np

from circuito_virtual.src.mapa import Mapa
from video_vuelta.src import etiquetas as et
from video_vuelta.src.camara import Camara


def _mapa_recto(longitud=400.0, paso=2.0):
    s = np.arange(0.0, longitud, paso)
    return Mapa("recto", longitud, s, np.zeros_like(s), np.zeros_like(s), s.copy())


def test_el_borde_se_proyecta_donde_toca():
    mapa, cam = _mapa_recto(), Camara(atras_m=3.0)
    izq = np.full(mapa.n_puntos, -3.0)
    # coche en s = 100 mirando a +z: el punto a 7 m de la cámara (4 m del punto del log) y 3 m a la izquierda
    u, v, Z = et.borde_en_imagen(cam, mapa, (0.0, 100.0, 0.0, 100.0), izq, np.array([4.0]))
    u2, v2 = cam.pixel(7.0, -3.0)
    assert abs(Z[0] - 7.0) < 1e-6 and abs(u[0] - u2) < 1e-6 and abs(v[0] - v2) < 1e-6


def test_una_cuesta_sube_el_punto_en_la_imagen():
    s = np.arange(0.0, 400.0, 2.0)
    llano = Mapa("llano", 400.0, s, np.zeros_like(s), np.zeros_like(s), s.copy())
    cuesta = Mapa("cuesta", 400.0, s, np.zeros_like(s), np.where(s > 104, (s - 104) * 0.05, 0.0), s.copy())
    cam = Camara(atras_m=3.0)
    n = np.full(llano.n_puntos, -3.0)
    pose = (0.0, 100.0, 0.0, 100.0)
    _, v_llano, _ = et.borde_en_imagen(cam, llano, pose, n, np.array([20.0]))
    _, v_cuesta, _ = et.borde_en_imagen(cam, cuesta, pose, n, np.array([20.0]))
    assert v_cuesta[0] < v_llano[0]


def test_mascara_del_pasillo_entre_los_bordes_y_con_carroceria_ignorada():
    mapa, cam = _mapa_recto(), Camara(atras_m=3.0)
    izq, dcha = np.full(mapa.n_puntos, -3.0), np.full(mapa.n_puntos, 3.0)
    m = et.mascara_pasillo(cam, mapa, (0.0, 100.0, 0.0, 100.0), izq, dcha)
    assert m.shape == (1080, 1920)
    u, v = cam.pixel(8.0, 0.0)
    assert m[int(v), int(u)] == 1  # el centro de la calzada, delante
    u, v = cam.pixel(8.0, -5.0)
    assert m[int(v), int(u)] == 0  # fuera del borde izquierdo
    assert (m == 255).any() and m[1060, 960] == 255 and m[200, 960] == 0
