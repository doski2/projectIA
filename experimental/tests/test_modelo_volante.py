"""Tests de `common/modelo_volante.py` (V39): convenciones de signo, planta, ajuste y simulación en lazo cerrado con datos sintéticos."""

import numpy as np
import pytest

from experimental.common import modelo_volante as mv

PLANTA = mv.Planta(a=10.0, b=0.002, tau=0.2)


def _vuelta(n=2400, v=25.0, kappa=0.0, cte=0.0, rumbo=0.0, volante=0.0, yaw=0.0):
    """Vuelta sintética a velocidad constante en una línea de curvatura constante, con el estado inicial pedido."""
    d = np.arange(n) * v / 60.0
    xs = np.arange(0.0, d.max() + 200.0, 0.5)
    return {"t_s": np.arange(n) / 60.0, "lap_distance": d, "v": np.full(n, v), "signed_cte": np.full(n, cte), "heading_err": np.full(n, rumbo),
            "steering": np.full(n, volante), "yaw": np.full(n, yaw), "tabla": (xs, np.full(len(xs), kappa))}


def test_la_guinada_estacionaria_tiene_el_signo_de_la_convencion_del_juego():
    assert PLANTA.guinada_estacionaria(25.0, -0.1) > 0.0  # volante negativo = izquierda = guiñada positiva
    assert PLANTA.guinada_estacionaria(25.0, 0.1) == pytest.approx(-PLANTA.guinada_estacionaria(25.0, -0.1))
    assert PLANTA.guinada_estacionaria(25.0, -0.1) == pytest.approx(25.0 * 0.1 / (10.0 + 0.002 * 625.0))


def test_en_recta_y_sin_error_el_coche_no_se_mueve():
    _, cte = mv.simular(_vuelta(), 10.0, 150.0, PLANTA)
    assert np.abs(cte).max() < 1e-9


def test_un_desvio_en_recta_se_corrige_sin_cruzar_la_linea_de_forma_brusca():
    v = _vuelta(cte=1.0)
    _, cte = mv.simular(v, 10.0, 400.0, PLANTA)
    assert abs(cte[-1]) < 0.5 < 1.0  # vuelve hacia la línea
    assert np.abs(cte).max() <= 1.2  # y no rebasa mucho


def test_con_la_anticipacion_justa_el_coche_se_queda_en_la_linea_en_una_curva():
    """Con g tal que la anticipación 4,3·(1 + g·v²) iguala lo que pide el coche a 25 m/s, el estado estacionario de la curva se mantiene (CTE ≈ 0)."""
    v, kappa = 25.0, 0.01
    g = ((10.0 + 0.002 * v * v) / 4.3 - 1.0) / (v * v)
    ley = mv.Ley(ff_gain=g)
    assert mv.ff_sobre_necesario(PLANTA, v, ley) == pytest.approx(1.0)
    volante = -(10.0 + 0.002 * v * v) * kappa
    vuelta = _vuelta(kappa=kappa, volante=volante, yaw=v * kappa)
    _, cte = mv.simular(vuelta, 10.0, 300.0, PLANTA, ley)
    assert np.abs(cte).max() < 0.05
    # con la anticipación de A2.0 (0,003) se pasa un 35 % a 30 m/s y el coche se cierra hacia el interior de la curva (CTE al lado de la curvatura)
    assert mv.ff_sobre_necesario(PLANTA, 30.0, mv.Ley()) == pytest.approx(1.348, abs=0.01)
    _, cte_pasado = mv.simular(vuelta, 10.0, 300.0, PLANTA, mv.Ley(ff_gain=0.003))
    assert np.abs(cte_pasado).max() > 5 * np.abs(cte).max()


def test_menos_anticipacion_en_exceso_reduce_el_desvio():
    v, kappa = 30.0, 0.008
    volante = -(10.0 + 0.002 * v * v) * kappa
    vuelta = _vuelta(v=v, kappa=kappa, volante=volante, yaw=v * kappa)
    pico = {g: np.abs(mv.simular(vuelta, 10.0, 400.0, PLANTA, mv.Ley(ff_gain=g))[1]).max() for g in (0.003, 0.002)}
    assert pico[0.002] < pico[0.003]


def test_el_ajuste_recupera_una_planta_sintetica():
    rng = np.random.default_rng(1)
    n = 3000
    t = np.arange(n) / 60.0
    v = 25.0 + 8.0 * np.sin(2 * np.pi * t / 20.0)
    volante = np.cumsum(rng.normal(0, 0.004, n))
    volante = volante - np.convolve(volante, np.ones(240) / 240, mode="same")  # sin deriva lenta
    real = mv.Planta(a=8.0, b=0.004, tau=0.15)
    yaw = np.zeros(n)
    for k in range(n - 1):
        yaw[k + 1] = yaw[k] + (1 / 60.0) / real.tau * (real.guinada_estacionaria(v[k], volante[k]) - yaw[k])
    vuelta = {"t_s": t, "lap_distance": np.cumsum(v / 60.0), "v": v, "signed_cte": np.zeros(n), "heading_err": np.zeros(n), "steering": volante, "yaw": yaw}
    planta, err = mv.ajustar_guinada([vuelta])
    assert err < 0.01
    for vel in (22.0, 28.0, 33.0):  # A y B se compensan entre sí: se compara lo que importa, la ganancia a cada velocidad
        assert planta.guinada_estacionaria(vel, -0.1) == pytest.approx(real.guinada_estacionaria(vel, -0.1), rel=0.08)
    assert planta.tau == pytest.approx(0.15, rel=0.2)


def test_ff_sobre_necesario_crece_con_la_velocidad_y_baja_con_la_ganancia():
    r = [mv.ff_sobre_necesario(PLANTA, v, mv.Ley()) for v in (20.0, 25.0, 30.0, 33.0)]
    assert r == sorted(r) and r[-1] > 1.3
    assert mv.ff_sobre_necesario(PLANTA, 30.0, mv.Ley(ff_gain=0.002)) < mv.ff_sobre_necesario(PLANTA, 30.0, mv.Ley())


# ---- V41: bicicleta, tope del factor de anticipación y comparación del cambio entre sesiones
BICI = mv.Bicicleta(kf=150.0, kr=130.0, a=1.3, c=0.25, ciz=1.0)


def test_la_bicicleta_en_estado_estacionario_da_la_guinada_del_modelo_analitico():
    v, volante = 25.0, -0.05
    est = BICI.estado_inicial(0.0, 0.0)
    for _ in range(60 * 12):
        est = BICI.paso(est, v, volante)
    delta = 0.25 * 0.05
    esperado = v * delta / (BICI.largo + BICI.gradiente_subviraje() * v * v)
    assert BICI.guinada(est) == pytest.approx(esperado, rel=0.01)
    assert BICI.guinada(est) > 0.0  # volante negativo = izquierda = guiñada positiva
    # y el volante necesario por unidad de κ es el que da esa guiñada en una curva de κ = guiñada / v
    assert BICI.necesario(v) * (esperado / v) == pytest.approx(0.05, rel=0.01)


def test_la_bicicleta_subvira_si_el_eje_delantero_es_mas_blando_que_el_trasero():
    blando_delante = mv.Bicicleta(kf=100.0, kr=200.0, a=1.3, c=0.25)
    blando_detras = mv.Bicicleta(kf=200.0, kr=100.0, a=1.3, c=0.25)
    assert blando_delante.gradiente_subviraje() > 0.0 > blando_detras.gradiente_subviraje()
    assert blando_delante.necesario(33.0) > blando_delante.necesario(10.0)  # subvirador: más volante a más velocidad


def test_el_ajuste_de_la_bicicleta_recupera_la_ganancia_de_un_coche_sintetico():
    rng = np.random.default_rng(3)
    n = 4000
    t = np.arange(n) / 60.0
    v = 26.0 + 7.0 * np.sin(2 * np.pi * t / 25.0)
    volante = np.cumsum(rng.normal(0, 0.004, n))
    volante = volante - np.convolve(volante, np.ones(300) / 300, mode="same")
    yaw, beta = np.zeros(n), np.zeros(n)
    est = BICI.estado_inicial(0.0, 0.0)
    for k in range(n):
        beta[k], yaw[k] = est
        est = BICI.paso(est, v[k], volante[k])
    vuelta = {"t_s": t, "lap_distance": np.cumsum(v / 60.0), "v": v, "signed_cte": np.zeros(n), "heading_err": np.zeros(n), "steering": volante, "yaw": yaw, "beta": beta}
    ajustada, _, err_yaw = mv.ajustar_bicicleta([vuelta])
    assert err_yaw < 0.01 and ajustada.signo_beta == 1.0
    for vel in (22.0, 28.0, 33.0):
        assert ajustada.necesario(vel) == pytest.approx(BICI.necesario(vel), rel=0.1)


def test_el_tope_de_velocidad_deja_el_factor_igual_hasta_el_tope_y_plano_despues():
    sin_tope, con_tope = mv.Ley(), mv.Ley(ff_cap_kmh=100.0)
    assert con_tope.factor_ff(80 / 3.6) == pytest.approx(sin_tope.factor_ff(80 / 3.6))
    assert con_tope.factor_ff(100 / 3.6) == pytest.approx(sin_tope.factor_ff(100 / 3.6))
    assert con_tope.factor_ff(125 / 3.6) == pytest.approx(con_tope.factor_ff(100 / 3.6))
    assert con_tope.factor_ff(125 / 3.6) < sin_tope.factor_ff(125 / 3.6)
    assert mv.ff_sobre_necesario(PLANTA, 34.0, con_tope) < mv.ff_sobre_necesario(PLANTA, 34.0, sin_tope)


def test_la_simulacion_sirve_para_cualquiera_de_las_dos_plantas_y_el_cambio_por_ventana_es_finito():
    n = 60 * 130
    v = 25.0
    d = np.arange(n) * v / 60.0
    xs = np.arange(0.0, d.max() + 200.0, 0.5)
    kappa = 0.01 * np.sin(2 * np.pi * xs / 600.0)
    cte = 1.5 * np.sin(2 * np.pi * d / 500.0)
    vuelta = {"t_s": np.arange(n) / 60.0, "lap_distance": d, "v": np.full(n, v), "signed_cte": cte, "heading_err": np.zeros(n), "steering": np.zeros(n), "yaw": np.zeros(n),
              "beta": np.zeros(n), "tabla": (xs, kappa)}
    for planta in (PLANTA, BICI):
        s, c = mv.simular(vuelta, 300.0, 500.0, planta)
        assert len(s) > 100 and np.all(np.isfinite(c))
    nuevas = [{**vuelta, "signed_cte": 0.5 * cte}]
    r = mv.cambio_por_ventana(vuelta, nuevas, BICI, mv.Ley(), mv.Ley(ff_gain=0.002))
    assert r["con_cambio"] >= 1 and len(r["filas"]) >= 5
    assert np.isfinite(r["alta"][0]) or np.isfinite(r["baja"][0])
