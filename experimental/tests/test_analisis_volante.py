"""Tests de `common/analisis_volante.py` (V19): inversiones del volante y métricas sobre señales sintéticas."""

import numpy as np
import pytest

from experimental.common import analisis_volante as av


def test_inversiones_ignora_el_ruido_y_cuenta_los_cambios_de_sentido():
    assert av.inversiones([0.0] * 50) == 0
    ruido = 0.01 * np.sin(np.linspace(0, 40 * np.pi, 600))  # amplitud 0,01 < umbral 0,03
    assert av.inversiones(ruido) == 0
    onda = 0.2 * np.sin(np.linspace(0, 6 * np.pi, 600))  # 3 periodos: 5 cambios de sentido entre el primer y el último extremo
    assert av.inversiones(onda) in (5, 6)
    assert av.inversiones(np.linspace(-0.5, 0.5, 100)) == 0  # un giro monótono no invierte


def test_metricas_de_una_recta_tranquila_y_de_un_zigzag():
    n = 600
    t = np.arange(n) / 60.0
    d = np.arange(n) * 0.5  # 300 m
    quieto = av.metricas(d, t, np.zeros(n), np.zeros(n), np.zeros(n), np.ones(n, dtype=bool))
    assert quieto is not None
    assert quieto["volante_rms"] == 0.0 and quieto["inversiones_100m"] == 0.0 and quieto["tasa"] == 0.0
    zigzag = 0.3 * np.sin(2 * np.pi * t / 2.0)  # periodo de 2 s
    z = av.metricas(d, t, zigzag, 2.0 * zigzag, 5.0 * zigzag, np.ones(n, dtype=bool))
    assert z is not None
    assert z["volante_rms"] == pytest.approx(0.3 / np.sqrt(2), rel=0.02)
    assert z["inversiones_100m"] == pytest.approx(100.0 * (2 * t[-1] / 2.0) / 300.0, rel=0.25)  # 2 inversiones por periodo
    assert z["cte_max"] == pytest.approx(0.6, rel=0.02) and z["deriva_max"] == pytest.approx(1.5, rel=0.02)
    assert z["tasa"] == pytest.approx(4 * 0.3 / 2.0, rel=0.05)  # 4·amplitud por periodo


def test_metricas_sin_datos_suficientes_devuelve_none():
    n = 100
    assert av.metricas(np.arange(n) * 0.1, np.arange(n) / 60.0, np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n, dtype=bool)) is None
    assert av.metricas(np.arange(n) * 0.1, np.arange(n) / 60.0, np.zeros(n), np.zeros(n), np.zeros(n), np.ones(n, dtype=bool)) is None  # solo 10 m


def test_metricas_cuenta_los_metros_recorridos_aunque_la_sesion_pase_por_el_final_de_vuelta():
    n = 1200
    t = np.arange(n) / 60.0
    d = (np.arange(n) * 0.5) % 400.0  # 600 m en dos vueltas de 400 m: la distancia de vuelta vuelve a 0
    m = av.metricas(d, t, np.zeros(n), np.zeros(n), np.zeros(n), np.ones(n, dtype=bool))
    assert m is not None and m["metros"] == pytest.approx(600.0, abs=1.0)
