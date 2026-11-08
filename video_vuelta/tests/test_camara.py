"""Tests de `camara.py`: idas y vueltas píxel <-> suelo y recuperación de la calibración con datos sintéticos."""

import numpy as np

from video_vuelta.src.camara import Camara, ajustar_altura_cabeceo


def test_ida_y_vuelta_suelo_pixel():
    cam = Camara(altura_m=1.0, cabeceo_rad=0.1)
    Z, X = np.array([4.0, 6.0, 12.0, 25.0]), np.array([-3.0, 0.0, 2.5, -6.0])
    u, v = cam.pixel(Z, X)
    Z2, X2 = cam.suelo(u, v)
    assert np.allclose(Z, Z2, atol=1e-9) and np.allclose(X, X2, atol=1e-9)


def test_horizonte_y_por_encima_es_nan():
    cam = Camara(altura_m=1.0, cabeceo_rad=0.1)
    assert abs(cam.horizonte_v - (540 - cam.f * np.tan(0.1))) < 1e-9
    Z, X = cam.suelo(960.0, cam.horizonte_v - 5)
    assert np.isnan(Z) and np.isnan(X)
    # un punto a mucha distancia cae casi en el horizonte
    _, v = cam.pixel(5000.0, 0.0)
    assert abs(v - cam.horizonte_v) < 1.0


def test_punto_centrado_no_tiene_lateral():
    cam = Camara()
    u, _ = cam.pixel(7.0, 0.0)
    assert abs(u - 960.0) < 1e-9


def test_focal_de_70_grados_horizontales():
    assert abs(Camara().f - 960 / np.tan(np.radians(35))) < 1e-9


def test_px_por_metro_baja_con_la_distancia():
    cam = Camara()
    assert cam.px_por_metro(800) > cam.px_por_metro(600) > cam.px_por_metro(450)


def test_ajuste_recupera_altura_cabeceo_y_atras():
    verdad = Camara(altura_m=1.05, cabeceo_rad=0.11, atras_m=2.8)
    restante = np.linspace(6.0, -2.5, 60)  # metros que quedan hasta el instante de referencia
    _, v = verdad.pixel(verdad.atras_m + restante, 0.0)
    rng = np.random.default_rng(0)
    v = v + rng.normal(0, 0.4, v.shape)
    cam, info = ajustar_altura_cabeceo(v, restante)
    assert abs(cam.altura_m - 1.05) < 0.06
    assert abs(cam.cabeceo_rad - 0.11) < 0.008
    assert abs(cam.atras_m - 2.8) < 0.2
    assert info["rms_px"] < 1.0 and info["n"] == 60


def test_cada_cruce_tiene_su_propio_atras_y_se_comparte_la_altura():
    verdad = Camara(altura_m=1.0, cabeceo_rad=0.1, atras_m=3.0)
    restante = np.tile(np.linspace(6.0, -0.5, 45), 2)
    ev = np.repeat([0, 1], 45)
    desfase = np.where(ev == 0, 0.0, 0.14)  # el 2.º cruce se anotó 0,14 m tarde en el log
    _, v = verdad.pixel(verdad.atras_m + restante + desfase, 0.0)
    cam, info = ajustar_altura_cabeceo(v, restante, evento=ev)
    assert abs(cam.altura_m - 1.0) < 0.02 and abs(cam.cabeceo_rad - 0.1) < 0.003
    assert abs(info["atras_por_evento_m"][1] - info["atras_por_evento_m"][0] - 0.14) < 0.03 and info["rms_px"] < 0.5


def test_el_ajuste_recorta_los_atipicos():
    verdad = Camara(altura_m=1.0, cabeceo_rad=0.1, atras_m=3.0)
    restante = np.linspace(6.0, -2.0, 70)
    _, v = verdad.pixel(verdad.atras_m + restante, 0.0)
    rng = np.random.default_rng(1)
    v = v + rng.normal(0, 0.3, v.shape)
    v[::9] += rng.uniform(40, 120, v[::9].shape)  # «líneas» falsas en algunos fotogramas
    cam, info = ajustar_altura_cabeceo(v, restante)
    assert abs(cam.altura_m - 1.0) < 0.08 and abs(cam.cabeceo_rad - 0.1) < 0.01
    assert info["descartados"] >= 6 and info["rms_px"] < 1.0


def test_camara_de_manifiesto_usa_el_campo_de_vision_y_la_calibracion():
    from video_vuelta.src.camara import camara_de_manifiesto

    c = camara_de_manifiesto({"campo_de_vision_horizontal_deg": 90, "resolucion": [1920, 1080]})
    assert c.fov_h_deg == 90 and abs(c.f - 960.0) < 1e-9
    c2 = camara_de_manifiesto({"campo_de_vision_horizontal_deg": 90, "camara_modelo": {"fov_h_deg": 80, "altura_m": 0.95, "cabeceo_rad": 0.09}})
    assert c2.fov_h_deg == 80 and c2.altura_m == 0.95


def test_pixel_con_punto_mas_alto_sube_en_la_imagen():
    cam = Camara(altura_m=1.0, cabeceo_rad=0.1)
    _, v_llano = cam.pixel(10.0, 0.0)
    _, v_cuesta = cam.pixel(10.0, 0.0, abajo_m=0.6)  # el punto está 40 cm más alto que el plano de la calzada
    assert v_cuesta < v_llano
    _, v_igual = cam.pixel(10.0, 0.0, abajo_m=1.0)
    assert abs(v_igual - v_llano) < 1e-9
