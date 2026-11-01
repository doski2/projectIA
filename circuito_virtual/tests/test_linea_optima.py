"""Tests de D2 (`linea_optima.py`): spline, pasillo, optimizador en un circuito sintético de solución conocida y formato de salida."""

import math

import numpy as np
import pytest

from circuito_virtual.src import linea_optima as lo
from circuito_virtual.src import perfil_velocidad as pv
from circuito_virtual.src.bordes_logs import Observaciones
from circuito_virtual.src.mapa import Mapa

CAR = pv.CarParams([(0.0, 4.0), (200.0, 4.0)], [(0.0, 10.0), (200.0, 10.0)], mu=14.6, k=0.0, v_known_kmh=120.0)


def _rectangulo_redondeado(largo=150.0, ancho=100.0, radio=40.0) -> Mapa:
    """Rectángulo de rectas `largo` × `ancho` con esquinas de `radio`, recorrido a la izquierda, un punto por metro de arco."""
    rectas = (largo, ancho, largo, ancho)
    arco = math.pi / 2 * radio
    total = sum(rectas) + 4 * arco
    n = int(total)
    s = np.arange(n, dtype=float)
    x = np.empty(n)
    z = np.empty(n)
    pos = np.array([0.0, 0.0])
    rumbo = 0.0
    tramos = []  # (longitud, curvatura)
    for r in rectas:
        tramos += [(r, 0.0), (arco, 1.0 / radio)]
    inicio = 0.0
    k = 0
    for i, dist in enumerate(s):
        while dist >= inicio + tramos[k][0]:
            inicio += tramos[k][0]
            # avanza hasta el final del tramo y gira con la curvatura de ese tramo
            l, c = tramos[k]
            if c == 0.0:
                pos = pos + l * np.array([math.cos(rumbo), math.sin(rumbo)])
            else:
                nuevo = rumbo + c * l
                pos = pos + (np.array([math.sin(nuevo) - math.sin(rumbo), -math.cos(nuevo) + math.cos(rumbo)])) / c
                rumbo = nuevo
            k += 1
        l, c = tramos[k]
        d = dist - inicio
        if c == 0.0:
            p = pos + d * np.array([math.cos(rumbo), math.sin(rumbo)])
        else:
            nuevo = rumbo + c * d
            p = pos + np.array([math.sin(nuevo) - math.sin(rumbo), -math.cos(nuevo) + math.cos(rumbo)]) / c
        x[i], z[i] = p
    return Mapa("rectangulo", total, s, x, np.zeros(n), z)


def _pasillo(mapa: Mapa, semi_ancho: float):
    return np.full(mapa.n_puntos, -semi_ancho), np.full(mapa.n_puntos, semi_ancho)


def test_spline_es_local_convexa_periodica_y_suave():
    s = np.arange(0.0, 600.0)
    b, s_nudos = lo.base_spline(600.0, s, 30.0)
    assert b.shape == (600, 20) and len(s_nudos) == 20
    assert np.allclose(b.sum(axis=1), 1.0) and b.min() >= 0.0  # n constante se queda constante y nunca sale del rango de sus puntos de control
    assert (b > 0).sum(axis=1).max() <= 4  # soporte local: cada punto depende de 4 puntos de control
    c = np.zeros(20)
    c[7] = 1.0
    n = b @ c
    assert np.flatnonzero(n > 0).min() >= 7 * 30 - 60 and np.flatnonzero(n > 0).max() <= 7 * 30 + 60  # un solo punto de control solo mueve ±2 tramos
    c = np.sin(2 * np.pi * s_nudos / 600.0)
    n = b @ c
    assert abs(n[0] - n[-1]) < 0.2  # cierra la vuelta sin salto (hay 1 m entre puntos)
    assert np.abs(np.diff(n, 2)).max() < 0.01  # sin quiebros: la derivada segunda es continua


def test_el_pasillo_siempre_incluye_el_eje(tmp_path):
    mapa = _rectangulo_redondeado()
    obs = Observaciones.vacia(mapa)
    obs.izq_dentro[:] = -0.2  # la rueda izquierda nunca pasó de aquí: el centro estaría en +0,65 m y el eje quedaría fuera
    obs.dcha_dentro[:] = 1.0
    obs.dcha_dentro[100:200] = 5.0
    lo_c, hi_c = lo.pasillo_centro(mapa, obs, margen_m=0.3)
    assert np.all(lo_c <= 0.0) and np.all(hi_c >= 0.0)
    assert hi_c[150] == pytest.approx(5.0 - obs.semivia_m - 0.3)  # donde hay margen, se usa


def test_el_borde_medido_manda_sobre_el_comprobado():
    mapa = _rectangulo_redondeado()
    obs = Observaciones.vacia(mapa)
    obs.izq_dentro[:] = -2.0
    obs.izq_fuera[:] = -2.3
    obs.dcha_dentro[:] = 2.0
    obs.dcha_fuera[:] = 2.3
    lo_c, hi_c = lo.pasillo_centro(mapa, obs, margen_m=0.0)
    assert hi_c[0] == pytest.approx(2.15 - obs.semivia_m)  # punto medio de las dos cotas
    assert lo_c[0] == pytest.approx(-2.15 + obs.semivia_m)


def test_la_geometria_con_n_cero_es_el_eje():
    mapa = _rectangulo_redondeado()
    x, z = lo.geometria(mapa, np.zeros(mapa.n_puntos))
    assert np.allclose(x, mapa.x) and np.allclose(z, mapa.z)


def test_la_linea_por_dentro_es_mas_corta_y_el_track_conserva_su_longitud():
    mapa = _rectangulo_redondeado()
    track0, _ = lo.track_de_n(mapa, np.zeros(mapa.n_puntos))
    track_dentro, u = lo.track_de_n(mapa, np.full(mapa.n_puntos, -3.0))  # a la izquierda = por dentro (se recorre girando a la izquierda)
    assert track_dentro.length_m == pytest.approx(track0.length_m - 4 * (math.pi / 2) * 3.0, abs=0.5)
    assert np.all(np.diff(u) > 0)


def test_el_optimizador_corta_las_curvas_y_respeta_el_pasillo():
    mapa = _rectangulo_redondeado()
    lo_c, hi_c = _pasillo(mapa, 4.0)
    res = lo.optimizar(mapa, lo_c, hi_c, CAR, paso_nudos_m=25.0, max_barridos=70)
    assert res.tiempo_s < res.tiempo_base_s * 0.95  # cuatro esquinas de 90° con 8 m de pasillo: sale un 8 %
    assert np.all(res.n >= lo_c - 1e-6) and np.all(res.n <= hi_c + 1e-6)
    # en el vértice de cada esquina (mitad del arco) la línea va por dentro, o sea hacia la izquierda (n < 0)
    arco = math.pi / 2 * 40.0
    assert res.n[int(150.0 + arco / 2)] < -1.5
    # en la recta antes de la esquina se va por fuera (n > 0) para abrir el radio
    assert np.mean(res.n[110:145]) > 0.5
    # el tiempo que da el optimizador es el del solver para esa línea
    assert res.tiempo_s == pytest.approx(lo.tiempo_vuelta(mapa, res.n, CAR), rel=1e-9)


def test_el_optimizador_no_se_mueve_si_no_hay_pasillo():
    mapa = _rectangulo_redondeado()
    cero = np.zeros(mapa.n_puntos)
    res = lo.optimizar(mapa, cero, cero, CAR, paso_nudos_m=25.0, max_barridos=3)
    assert np.all(res.n == 0.0) and res.tiempo_s == res.tiempo_base_s


def test_escribir_linea_con_n_cero_reproduce_la_referencia_y_un_desplazamiento_la_mueve():
    mapa = _rectangulo_redondeado()
    puntos = [{"d": float(si), "pos": [float(xi), 0.0, float(zi)], "spd": 16.6, "ori": [0.0, 0.0, 0.0]} for si, xi, zi in zip(mapa.s, mapa.x, mapa.z)]
    datos = {"track_length": mapa.longitud_m, "points": puntos}
    igual = lo.escribir_linea(mapa, np.zeros(mapa.n_puntos), datos)
    assert all(abs(a["pos"][0] - b["pos"][0]) < 1e-3 and abs(a["pos"][2] - b["pos"][2]) < 1e-3 for a, b in zip(igual["points"], puntos))
    assert all(abs(p["ori"][1]) < 1e-9 for p in igual["points"])  # el rumbo no cambia
    mov = lo.escribir_linea(mapa, np.full(mapa.n_puntos, 2.0), datos, {"ritmo_f": 1.0})
    assert mov["optima"]["ritmo_f"] == 1.0
    d = np.hypot(np.array([p["pos"][0] for p in mov["points"]]) - mapa.x, np.array([p["pos"][2] for p in mov["points"]]) - mapa.z)
    assert np.allclose(d, 2.0, atol=0.01)
    assert datos["points"][0]["pos"][0] == pytest.approx(mapa.x[0])  # no toca la entrada
    with pytest.raises(ValueError):
        lo.escribir_linea(mapa, np.zeros(mapa.n_puntos), {"points": puntos[:-1]})


def test_el_coche_del_teacher_es_el_de_a1_con_limite_lateral_fijo():
    c = lo.coche_a1(9.0)
    base = pv.load_params(lo.COCHE_A1)
    assert c.mu == 9.0 and c.k == 0.0 and c.v_known_kmh == base.v_known_kmh == 125.0
    assert c.accel == base.accel and c.brake == base.brake
    # y su vuelta no pasa de 125 km/h en ningún punto (el tope viene de las tablas de A1)
    mapa = _rectangulo_redondeado()
    perfil = pv.solve(lo.track_de_n(mapa, np.zeros(mapa.n_puntos))[0], c)
    assert perfil.v_ms.max() * 3.6 <= 125.0 + 1e-6


def test_pasillo_estricto_respeta_el_margen_donde_el_eje_no_cabe():
    """V35, 759-771 m: borde izquierdo de la rueda a −1,0 m; el centro necesita n ≥ 0,15 m y el eje dejaba la rueda a 0,15 m del borde."""
    mapa = _rectangulo_redondeado()
    obs = Observaciones.vacia(mapa)
    obs.izq_dentro[:] = -1.0
    obs.dcha_dentro[:] = 5.0
    lo_c, hi_c = lo.pasillo_centro(mapa, obs, margen_m=0.3)
    assert np.all(lo_c == 0.0)  # como siempre: el eje entra
    lo_e, hi_e = lo.pasillo_centro(mapa, obs, margen_m=0.3, incluir_eje=False)
    assert np.allclose(lo_e, 0.15) and np.allclose(hi_e, 5.0 - obs.semivia_m - 0.3)
    izq, dcha = lo.holgura_rueda(obs, np.zeros(mapa.n_puntos))
    assert np.allclose(izq, 0.15) and np.allclose(dcha, 4.15)  # la holgura de la rueda con el eje es la que se vio en el juego
    izq, _ = lo.holgura_rueda(obs, lo_e)
    assert np.allclose(izq, 0.3)


def test_pasillo_estricto_mas_estrecho_que_el_coche_queda_en_el_punto_medio_y_sin_dato_en_el_eje():
    mapa = _rectangulo_redondeado()
    obs = Observaciones.vacia(mapa)
    obs.izq_dentro[:] = -0.2  # lo = 0,95
    obs.dcha_dentro[:] = 1.0  # hi = −0,15
    lo_e, hi_e = lo.pasillo_centro(mapa, obs, margen_m=0.3, incluir_eje=False)
    assert np.allclose(lo_e, 0.4) and np.allclose(hi_e, 0.4)
    obs2 = Observaciones.vacia(mapa)
    obs2.dcha_dentro[:] = 4.0  # sin ninguna cota a la izquierda: ese lado se queda en el eje
    lo_e, hi_e = lo.pasillo_centro(mapa, obs2, margen_m=0.3, incluir_eje=False)
    assert np.all(lo_e == 0.0) and np.allclose(hi_e, 4.0 - obs2.semivia_m - 0.3)


def test_punto_inicial_cabe_en_el_pasillo_y_es_cero_si_el_eje_cabe():
    mapa = _rectangulo_redondeado()
    b, _ = lo.base_spline(mapa.longitud_m, mapa.s, 25.0)
    lo_c, hi_c = _pasillo(mapa, 2.0)
    assert np.all(lo.punto_inicial(b, lo_c, hi_c) == 0.0)
    lo_e = np.full(mapa.n_puntos, 0.15)
    lo_e[300:340] = 0.6  # un tramo estrecho: todos los puntos de control que lo sostienen suben a 0,6
    hi_e = np.full(mapa.n_puntos, 3.0)
    n = b @ lo.punto_inicial(b, lo_e, hi_e)
    assert np.all(n >= lo_e - 1e-9) and np.all(n <= hi_e + 1e-9)


def test_el_optimizador_parte_de_un_pasillo_sin_eje_y_no_sale_de_el():
    mapa = _rectangulo_redondeado()
    lo_e = np.full(mapa.n_puntos, 0.5)
    hi_e = np.full(mapa.n_puntos, 4.0)
    res = lo.optimizar(mapa, lo_e, hi_e, CAR, paso_nudos_m=25.0, max_barridos=20)
    assert np.all(res.n >= lo_e - 1e-6) and np.all(res.n <= hi_e + 1e-6)
    assert res.tiempo_s <= lo.tiempo_vuelta(mapa, np.full(mapa.n_puntos, 0.5), CAR) + 1e-9  # nunca peor que la línea de partida
    assert res.tiempo_base_s == pytest.approx(lo.tiempo_vuelta(mapa, np.zeros(mapa.n_puntos), CAR), rel=1e-9)  # la referencia sigue siendo el eje


def test_los_topes_de_pendiente_y_de_salto_de_curvatura_se_cumplen_y_la_linea_sigue_ganando():
    mapa = _rectangulo_redondeado()
    lo_c, hi_c = _pasillo(mapa, 4.0)
    libre = lo.optimizar(mapa, lo_c, hi_c, CAR, paso_nudos_m=25.0, max_barridos=40)
    suave = lo.optimizar(mapa, lo_c, hi_c, CAR, paso_nudos_m=25.0, max_barridos=40, pendiente_max=0.5 * libre.pendiente_max)
    assert suave.pendiente_max <= 0.5 * libre.pendiente_max + 1e-9
    assert suave.tiempo_s < suave.tiempo_base_s  # con el tope sigue ganando al eje (el descenso es local: no se compara con la ejecución libre)
    sin_salto = lo.optimizar(mapa, lo_c, hi_c, CAR, paso_nudos_m=25.0, max_barridos=40, salto_max=0.5 * libre.salto_max)
    assert sin_salto.salto_max <= max(0.5 * libre.salto_max, lo.curvatura_continua(lo.track_de_n(mapa, np.zeros(mapa.n_puntos))[0])["salto_max"]) + 1e-9
    assert sin_salto.tiempo_s < sin_salto.tiempo_base_s


def test_si_el_tope_ya_lo_pasa_la_linea_de_partida_el_tope_es_el_de_la_partida():
    mapa = _rectangulo_redondeado()
    lo_c, hi_c = _pasillo(mapa, 4.0)
    res = lo.optimizar(mapa, lo_c, hi_c, CAR, paso_nudos_m=25.0, max_barridos=5, salto_max=0.0, pendiente_max=0.0)
    assert np.all(res.n == 0.0) and res.tiempo_s == res.tiempo_base_s
