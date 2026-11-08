"""Tests de `bordes_video.py`: del punto del suelo al mundo y agregación por metro, sin vídeo."""

import numpy as np

from circuito_virtual.src.mapa import Mapa
from video_vuelta.src import bordes_video as bv
from video_vuelta.src.camara import Camara
from video_vuelta.src.lineas import Linea


def _mapa_recto(longitud=400.0, paso=2.0):
    """Eje recto a lo largo de +z (tx = 0, tz = 1): la derecha del mapa es +x."""
    s = np.arange(0.0, longitud, paso)
    return Mapa("recto", longitud, s, np.zeros_like(s), np.zeros_like(s), s.copy())


def test_rumbo_del_log_es_la_direccion_del_movimiento(tmp_path):
    """orientation[1] = rumbo + π: el coche avanza hacia (sin rumbo, cos rumbo) en (x, z)."""
    import json

    rumbo = 0.7
    ruta = tmp_path / "log.jsonl"
    with open(ruta, "w", encoding="utf-8") as f:
        for k in range(50):
            f.write(json.dumps({"type": "tick", "t_s": k * 0.1, "lap": 1, "lap_distance": k * 0.8, "speed_kmh": 30.0,
                                "vehicle": {"position": [10 + 0.8 * k * np.sin(rumbo), 0.0, 5 + 0.8 * k * np.cos(rumbo)],
                                            "orientation": [0.0, rumbo + np.pi, 0.0]}}) + "\n")
    p = bv.leer_pose(ruta)
    x, z, r, s, v, vuelta = p.en(2.0)
    assert abs(r - rumbo) < 1e-9 and abs(x - (10 + 16 * np.sin(rumbo))) < 1e-6 and vuelta == 1


def test_punto_al_mundo_rumbo_cero_mira_a_z():
    x, z = bv.punto_al_mundo(0.0, 0.0, 0.0, np.array([7.0]), np.array([-2.0]), atras_m=3.0)
    assert np.allclose([x[0], z[0]], [-2.0, 4.0])  # 4 m por delante del punto del log, 2 m a la izquierda


def test_punto_al_mundo_rumbo_noventa_grados():
    x, z = bv.punto_al_mundo(10.0, 5.0, np.pi / 2, np.array([7.0]), np.array([-2.0]), atras_m=3.0)
    assert np.allclose([x[0], z[0]], [14.0, 7.0])  # mira a +x: su izquierda es +z


def test_la_derecha_del_coche_coincide_con_la_n_positiva_del_mapa():
    mapa = _mapa_recto()
    x, z = bv.punto_al_mundo(0.0, 100.0, 0.0, np.array([3.0]), np.array([2.5]), atras_m=3.0)
    s, n = mapa.xz_a_sn(x, z, s_hint=np.array([100.0]))
    assert abs(n[0] - 2.5) < 1e-6 and abs(s[0] - 100.0) < 1e-6


def test_muestras_de_linea_en_el_mapa():
    mapa = _mapa_recto()
    cam = Camara(atras_m=3.0)
    Z = np.linspace(3.0, 12.0, 30)
    linea = Linea(a=-3.2, b=0.0, Z=Z, X=np.full_like(Z, -3.2))
    # coche en s = 100, desplazado n = +0.5 a la derecha del eje, mirando a lo largo de la pista
    s, n, Zl = bv.muestras_de_linea(linea, (0.5, 100.0, 0.0, 100.0, 30.0, 1), cam, mapa)
    assert len(s) > 5
    assert np.allclose(n, 0.5 - 3.2, atol=1e-6)
    assert s.min() > 100.0 and s.max() < 110.0


def test_agregar_da_la_mediana_por_metro_y_las_medidas():
    mapa = _mapa_recto()
    r = bv.agregar([(10.2, -3.0, 6.0), (10.4, -3.2, 6.0), (10.6, -9.0, 6.0), (50.1, -3.1, 6.0)], mapa)
    b = int(10.2 / mapa.longitud_m * mapa.n_puntos)
    assert r["cuenta"][b] == 3 and abs(r["n"][b] - (-3.2)) < 1e-9
    assert np.isnan(r["n"][b + 5])
    assert int(r["cuenta"].sum()) == 4


def test_validar_cuenta_los_metros_dentro_de_la_horquilla(tmp_path):
    import json

    mapa = _mapa_recto(longitud=20.0, paso=1.0)
    n = np.full(20, np.nan)
    n[3], n[4], n[5] = -3.0, -3.0, -6.0  # el 5 cae lejos de la horquilla
    res = {"izq": {"n": n}, "dcha": {"n": np.full(20, np.nan)}}
    obs = {k: [None] * 20 for k in ("izq_dentro", "izq_fuera", "dcha_dentro", "dcha_fuera")}
    for i in (3, 4, 5):
        obs["izq_dentro"][i], obs["izq_fuera"][i] = -2.8, -3.4
    ruta = tmp_path / "obs.json"
    ruta.write_text(json.dumps(obs), encoding="utf-8")
    r = bv.validar(res, ruta, mapa)["izq"]
    assert r["con_horquilla"] == 3 and r["dentro_de_la_horquilla"] == 2


def test_agregar_pondera_lo_cercano():
    mapa = _mapa_recto()
    # dos medidas cercanas (Z = 4) en -3.0 y tres lejanas (Z = 20) en -3.6: manda lo cercano
    r = bv.agregar([(10.1, -3.0, 4.0), (10.2, -3.0, 4.0), (10.3, -3.6, 20.0), (10.4, -3.6, 20.0), (10.5, -3.6, 20.0)], mapa)
    b = int(10.1 / mapa.longitud_m * mapa.n_puntos)
    assert abs(r["n"][b] - (-3.0)) < 1e-9


def _res(izq, dcha):
    return {"izq": {"n": np.array(izq, float)}, "dcha": {"n": np.array(dcha, float)}}


def test_limites_aplican_sesgo_y_limite_fuera():
    n = 60
    r = bv.limites(_res([-5.0] * n, [5.2] * n))
    assert np.allclose(r["izq"], -5.0 - bv.SESGO_CAMARA_M - bv.LIMITE_FUERA_M)
    assert np.allclose(r["dcha"], 5.2 - bv.SESGO_CAMARA_M + bv.LIMITE_FUERA_M)


def test_limites_quitan_picos_y_rellenan_huecos_cortos():
    n = 60
    izq = np.full(n, -5.0)
    dcha = np.full(n, 5.0)
    dcha[30] = 9.0  # pico suelto
    izq[10:14] = np.nan  # hueco corto
    r = bv.limites(_res(izq, dcha), hueco_max=8)
    esperado_dcha = 5.0 - bv.SESGO_CAMARA_M + bv.LIMITE_FUERA_M
    assert abs(r["dcha"][30] - esperado_dcha) < 1e-9
    assert np.isfinite(r["izq"][10:14]).all()


def test_limites_no_rellenan_huecos_largos_ni_ponen_datos_donde_no_hay():
    n = 80
    izq = np.full(n, -5.0)
    izq[20:50] = np.nan
    r = bv.limites(_res(izq, np.full(n, 5.0)), hueco_max=10)
    assert np.isnan(r["izq"][30]) and np.isfinite(r["izq"][60])


def test_limites_descartan_anchos_imposibles():
    n = 40
    r = bv.limites(_res([-0.2] * n, [0.3] * n))  # «dos líneas» a 0,5 m: es una sola vista dos veces
    assert r["descartados"] == n and np.isnan(r["izq"]).all() and np.isnan(r["dcha"]).all()
