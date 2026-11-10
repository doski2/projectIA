"""Tests de `metricas_volante.py`: signo del desvío hacia dentro, fracción de pista desde el borde interior, picos, vueltas, agregado y comparación."""

import json
import math

import numpy as np
import pytest

from circuito_virtual.src.curvas import Catalogo, Curva
from circuito_virtual.src.mapa import Mapa
from experimental.common import metricas_volante as mv

R = 100.0
L = 2 * math.pi * R  # ≈ 628 m


def _mapa() -> Mapa:
    """Círculo recorrido en sentido antihorario en (x, z): curva a izquierdas, n + = derecha = hacia fuera."""
    s = np.arange(0.0, math.floor(L))
    th = s / R
    return Mapa("circulo", L, s, R * np.cos(th), np.zeros_like(s), R * np.sin(th))


def _pista(sentido="izq") -> mv.Pista:
    mapa = _mapa()
    cat = Catalogo([Curva(1, sentido, 100.0, 150.0, 200.0, R, 100.0, "radio constante")], L, "circulo")
    return mv.Pista(mapa, cat, np.full(mapa.n_puntos, -5.0), np.full(mapa.n_puntos, 5.0))


def _n_coche(s):
    """El coche va 1,5 m a la izquierda (por dentro) con el pico a 30 m del vértice, y 0,5 m a la derecha a 20 m antes del vértice."""
    return -1.5 * np.exp(-(((s - 180.0) / 8.0) ** 2)) + 0.5 * np.exp(-(((s - 130.0) / 6.0) ** 2))


def _ticks(mapa, lap, t0, paso=1.0, hasta=None, volante=-0.2, hierba_en=None):
    out = []
    s = np.arange(0.0, hasta if hasta is not None else mapa.longitud_m - 0.5, paso)
    x, z = mapa.sn_a_xz(s, _n_coche(s))
    for i, si in enumerate(s):
        terreno = [7, 0, 0, 0] if hierba_en is not None and abs(si - hierba_en) < 2 else ([48, 0, 0, 0] if 300 < si < 305 else [0, 0, 0, 0])
        out.append({"type": "tick", "lap": lap, "t_s": t0 + si / 30.0, "lap_distance": float(si), "speed_kmh": 108.0, "signed_cte": 0.0,
                    "throttle": 0.6, "brake": 0.0, "steering": volante,
                    "vehicle": {"position": [float(x[i]), 0.0, float(z[i])], "local_velocity": [1.0, 0.0, -30.0], "local_accel": [-9.0, 0.0, 0.0],
                                "terrain": terreno, "tyre_temp": [60, 58, 50, 48], "tyre_left_c": [61, 59, 0, 0]}})
    return out


def _linea_en_eje(mapa) -> np.ndarray:
    return np.zeros(mapa.n_puntos)


def test_inward_deviation_sign_fraction_from_inner_edge_and_peaks():
    pista = _pista()
    ses = mv.sesion_de_ticks(_ticks(pista.mapa, 1, 0.0) + _ticks(pista.mapa, 2, 30.0))
    fv = mv.fichas(ses, pista, _linea_en_eje(pista.mapa))
    assert sorted(fv) == [1, 2]
    c = fv[1]["curvas"]["C1"]
    assert c["pico_dentro"] == pytest.approx(1.5, abs=0.02) and c["pico_dentro_m"] == pytest.approx(30, abs=1)
    assert c["pico_fuera"] == pytest.approx(0.5, abs=0.02) and c["pico_fuera_m"] == pytest.approx(-20, abs=1)
    # en el vértice + 20 m (s = 170) el coche va por dentro: n < 0 en curva a izquierdas
    v20 = c["v20"]
    esperado = 1.5 * math.exp(-((10 / 8) ** 2))
    assert v20["dentro"] == pytest.approx(esperado, abs=0.01) and v20["n_coche"] == pytest.approx(-esperado, abs=0.01)
    # fracción desde el borde interior (izquierdo, n = −5): la línea en el eje está en 0,5 y el coche más cerca del borde interior
    assert v20["frac_linea"] == pytest.approx(0.5, abs=1e-3) and v20["frac_coche"] == pytest.approx((5 - esperado) / 10, abs=1e-3)
    # volante y lateral se dan en valor útil: volante + hacia la curva (aquí a la izquierda, steering < 0), |lateral|
    assert c["vertice"]["volante"] == pytest.approx(0.2) and c["vertice"]["lateral"] == pytest.approx(9.0)
    assert c["vertice"]["v"] == pytest.approx(108.0) and c["vertice"]["deriva"] == pytest.approx(math.degrees(math.atan2(1, 30)), abs=1e-2)
    assert fv[1]["gomas"] == {"DI": 60.0, "DD": 58.0, "TI": 50.0, "TD": 48.0}
    assert fv[1]["gomas_zonas"]["izq"][:2] == [61.0, 59.0] and fv[1]["gomas_zonas"]["izq"][2] is None  # los 0 son campo sin rellenar


def test_right_hand_curve_flips_the_signs():
    pista = _pista("dcha")
    ses = mv.sesion_de_ticks(_ticks(pista.mapa, 1, 0.0, volante=0.2))
    c = mv.fichas(ses, pista, _linea_en_eje(pista.mapa))[1]["curvas"]["C1"]
    # el mismo coche (que se va a la izquierda) en una curva a derechas va por fuera
    assert c["pico_fuera"] == pytest.approx(1.5, abs=0.02) and c["pico_dentro"] == pytest.approx(0.5, abs=0.02)
    assert c["v20"]["frac_coche"] == pytest.approx(0.531, abs=1e-3) and c["vertice"]["volante"] == pytest.approx(0.2)


def test_deviation_is_measured_against_the_line_not_the_axis():
    pista = _pista()
    ses = mv.sesion_de_ticks(_ticks(pista.mapa, 1, 0.0))
    linea = np.full(pista.mapa.n_puntos, -1.0)  # la línea va 1 m por dentro del eje en toda la vuelta
    c = mv.fichas(ses, pista, linea)[1]["curvas"]["C1"]
    assert c["pico_dentro"] == pytest.approx(0.5, abs=0.02)  # 1,5 m por dentro del eje = 0,5 m por dentro de la línea
    assert c["entrada"]["dentro"] == pytest.approx(-1.0, abs=0.02) and c["entrada"]["frac_linea"] == pytest.approx(0.4, abs=1e-3)


def test_line_n_from_reference_points():
    mapa = _mapa()
    s = np.arange(0.0, mapa.longitud_m - 1, 2.0)
    x, z = mapa.sn_a_xz(s, np.full(len(s), 0.7))
    ref = {"points": [{"d": float(si), "pos": [float(xi), 0.0, float(zi)]} for si, xi, zi in zip(s, x, z)]}
    assert np.allclose(mv.n_de_linea(mapa, ref), 0.7, atol=1e-3)


def test_only_complete_laps_and_lap_level_metrics():
    pista = _pista()
    ticks = _ticks(pista.mapa, 1, 0.0) + _ticks(pista.mapa, 2, 30.0, hierba_en=180.0) + _ticks(pista.mapa, 3, 60.0, hasta=300.0)
    ses = mv.sesion_de_ticks(ticks)
    assert mv.vueltas_completas(ses, pista.mapa.longitud_m) == [1, 2]
    fv = mv.fichas(ses, pista, _linea_en_eje(pista.mapa), vueltas=[2, 3])
    assert sorted(fv) == [2]
    f = fv[2]
    assert f["tiempo_s"] == pytest.approx((math.floor(L) - 1) / 30.0, abs=0.05)
    assert f["fuera"] == 4 + 3 and f["fuera_pista"] == 3  # el piano (48) cuenta como fuera pero no como hierba
    assert f["curvas"]["C1"]["fuera_pista"] == 3
    # |desvío| medio en la curva: el del coche entre s = 100 y 200
    s = np.arange(100.0, 201.0)
    assert f["cte_curvas"] == pytest.approx(float(np.mean(np.abs(_n_coche(s)))), abs=0.01)


def test_aggregate_and_compare():
    pista = _pista()
    fv = mv.fichas(mv.sesion_de_ticks(_ticks(pista.mapa, 1, 0.0) + _ticks(pista.mapa, 2, 30.0)), pista, _linea_en_eje(pista.mapa))
    agr = mv.agregar([fv])
    assert agr["vueltas"] == 2
    media, dt = agr["curvas"]["C1"]["pico_dentro"]
    assert media == pytest.approx(1.5, abs=0.02) and dt == pytest.approx(0.0, abs=1e-6)
    assert mv.agregar([fv], vueltas=[2])["vueltas"] == 1
    otra = json.loads(json.dumps(fv))  # una «sesión» con 0,4 m más de pico por dentro
    for f in otra.values():
        f["curvas"]["C1"]["pico_dentro"] += 0.4
    txt = mv.tabla_comparacion(mv.agregar([{int(k): v for k, v in otra.items()}]), agr)
    fila = next(linea for linea in txt.splitlines() if linea.startswith("C1"))
    assert "+0.40 (0.00)*" in fila


def test_mark_needs_both_noise_and_minimum():
    assert mv.marca(0.3, 0.1, 0.1)
    assert not mv.marca(0.3, 0.2, 0.1)  # dentro del ruido entre vueltas
    assert not mv.marca(0.05, 0.0, 0.1)  # fuera del ruido pero sin importancia


def test_parse_laps_and_time_text():
    assert mv.parse_vueltas("4-6") == [4, 5, 6]
    assert mv.parse_vueltas("3,5,7") == [3, 5, 7]
    assert mv.parse_vueltas("3-4,8") == [3, 4, 8]
    assert mv.parse_vueltas(None) is None
    assert mv.tiempo_txt(108.465) == "1:48.465"


def test_reference_path_falls_back_to_repo_relative(tmp_path):
    assert mv.ruta_referencia({}) is None
    ref = r"D:\otra\maquina\projectIA\circuito_virtual\pistas\sugo_gp\mapa.json"
    assert mv.ruta_referencia({"reference": ref}) == mv.REPO / "circuito_virtual" / "pistas" / "sugo_gp" / "mapa.json"
