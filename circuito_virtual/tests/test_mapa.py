"""Tests del mapa en coordenadas (s, n) (`mapa.py`, D0) con un óvalo sintético y con Sugo."""

import json
import math

import numpy as np
import pytest

from circuito_virtual.src import linea_suave, mapa as mp

STRAIGHT = 400
RADIUS = 50.0


def _oval():
    """Óvalo cerrado: recta de 400 m a lo largo de +x, semicírculo a la izquierda, recta de vuelta y semicírculo; un punto por metro."""
    pts = [(float(s), 0.0) for s in range(STRAIGHT)]
    n_arc = int(math.pi * RADIUS)
    pts += [(STRAIGHT + RADIUS * math.cos(a), RADIUS + RADIUS * math.sin(a)) for a in (-math.pi / 2 + math.pi * i / n_arc for i in range(n_arc))]
    pts += [(float(STRAIGHT - s), 2 * RADIUS) for s in range(STRAIGHT)]
    pts += [(RADIUS * math.cos(a), RADIUS + RADIUS * math.sin(a)) for a in (math.pi / 2 + math.pi * i / n_arc for i in range(n_arc))]
    return pts


def _mapa_ovalo():
    pts = _oval()
    data = {"track_name": "oval", "track_length": float(len(pts)), "points": [{"d": float(i), "pos": [x, 0.0, z]} for i, (x, z) in enumerate(pts)]}
    return mp.Mapa.desde_referencia(data)


def test_round_trip_is_exact_on_straights_and_corners_within_5_cm():
    m = _mapa_ovalo()
    rng = np.random.default_rng(0)
    s = rng.uniform(0, m.longitud_m, 3000)
    n = rng.uniform(-8, 8, 3000)
    s2, n2 = m.xz_a_sn(*m.sn_a_xz(s, n))
    ds = np.abs((s2 - s + m.longitud_m / 2) % m.longitud_m - m.longitud_m / 2)
    assert ds.max() < 0.05 and np.abs(n2 - n).max() < 0.05


def test_n_is_positive_to_the_right_and_kappa_positive_to_the_left():
    m = _mapa_ovalo()
    # la 1ª recta va por +x: la derecha es −z
    x, z = m.sn_a_xz(200.0, 2.0)
    assert x == pytest.approx(200.0, abs=0.01) and z == pytest.approx(-2.0, abs=0.01)
    s, n = m.xz_a_sn(200.0, -2.0)
    assert s == pytest.approx(200.0, abs=0.01) and n == pytest.approx(2.0, abs=0.01)
    assert m.interpola(m.kappa, 200.0) == pytest.approx(0.0, abs=1e-4)
    assert m.interpola(m.kappa, STRAIGHT + 80.0) == pytest.approx(1.0 / RADIUS, rel=0.05)  # el semicírculo gira a la izquierda


def test_round_trip_wraps_around_the_start_line():
    m = _mapa_ovalo()
    x, z = m.sn_a_xz(m.longitud_m - 0.5, 1.5)
    s, n = m.xz_a_sn(x, z)
    assert s[0] == pytest.approx(m.longitud_m - 0.5, abs=0.02) and n[0] == pytest.approx(1.5, abs=0.02)
    s2, _ = m.xz_a_sn(*m.sn_a_xz(m.longitud_m + 3.0, 0.0))  # s fuera de rango se envuelve
    assert s2[0] == pytest.approx(3.0, abs=0.02)


def test_search_hint_gives_the_same_answer_as_the_global_search():
    m = _mapa_ovalo()
    x, z = m.sn_a_xz(np.array([120.0, 700.0, 1100.0]), np.array([1.0, -3.0, 2.0]))
    a = m.xz_a_sn(x, z)
    b = m.xz_a_sn(x, z, s_hint=np.array([115.0, 690.0, 1105.0]))
    assert np.allclose(a[0], b[0], atol=0.01) and np.allclose(a[1], b[1], atol=0.01)


def test_edges_are_unknown_until_measured_and_the_corridor_uses_the_margin():
    m = _mapa_ovalo()
    assert m.bordes_conocidos == 0.0 and np.isnan(m.pasillo(100.0)[0])
    m.borde_izq[:] = -4.0
    m.borde_dcha[:] = 3.0
    lo, hi = m.pasillo(np.array([10.0, 500.0]), margen_m=1.0)
    assert np.allclose(lo, -3.0) and np.allclose(hi, 2.0) and m.bordes_conocidos == 1.0


def test_save_and_load_keep_everything_including_unknown_edges(tmp_path):
    m = _mapa_ovalo()
    m.borde_izq[:100] = -4.0
    m.sup_izq[:100] = 10
    m.meta = {"origen": "prueba"}
    m.guardar(tmp_path / "mapa.json")
    back = mp.Mapa.cargar(tmp_path / "mapa.json")
    assert back.nombre == m.nombre and back.meta == {"origen": "prueba"}
    assert np.allclose(back.x, m.x, atol=1e-3) and np.allclose(back.kappa, m.kappa, atol=1e-3)
    assert np.allclose(back.borde_izq[:100], -4.0) and np.isnan(back.borde_izq[100:]).all() and (back.sup_izq[:100] == 10).all()
    assert back.bordes_conocidos == 0.0


def test_rejects_a_wrong_axis_or_version():
    with pytest.raises(ValueError):
        mp.Mapa("x", 100.0, np.arange(4.0), np.zeros(4), np.zeros(4), np.zeros(4))  # menos de 8 puntos
    with pytest.raises(ValueError, match="versión"):
        mp.Mapa.de_dict({"version": 99})


def test_sugo_map_round_trips_within_5_cm_and_matches_the_production_conventions(tmp_path):
    from reference_recorder import ReferenceLine
    from obs_universal import signed_lateral_error

    m = mp.construir()
    assert m.longitud_m == pytest.approx(3567.0, abs=1.0) and m.n_puntos > 3500
    rng = np.random.default_rng(3)
    s = rng.uniform(0, m.longitud_m, 2000)
    n = rng.uniform(-6, 6, 2000)
    s2, n2 = m.xz_a_sn(*m.sn_a_xz(s, n))
    ds = np.abs((s2 - s + m.longitud_m / 2) % m.longitud_m - m.longitud_m / 2)
    assert ds.max() < 0.05 and np.abs(n2 - n).max() < 0.05
    # el CTE firmado de producción, sobre la misma línea, coincide con n en una recta (1500-1900 m)
    datos = json.loads(mp.DEFAULT_REF.read_text(encoding="utf-8"))
    suave, _ = linea_suave.smooth_reference(datos)
    ruta = tmp_path / "suave.json"
    ruta.write_text(json.dumps(suave), encoding="utf-8")
    ref = ReferenceLine.load(str(ruta))
    for s0, n0 in ((1550.0, 2.0), (1700.0, -1.5), (1850.0, 0.7)):
        x, z = m.sn_a_xz(s0, n0)
        assert signed_lateral_error(ref, (float(x), 0.0, float(z)), s0) == pytest.approx(n0, abs=0.08)
        assert m.interpola(m.kappa, s0) == pytest.approx(ref.curvature(s0), abs=0.002)


def test_the_committed_sugo_map_is_loadable():
    from pathlib import Path

    ruta = Path(mp.DEFAULT_OUT)
    if not ruta.is_file():
        pytest.skip("el mapa de Sugo no está generado")
    m = mp.Mapa.cargar(ruta)
    assert m.nombre == "SUGO_GP" and m.longitud_m == pytest.approx(3567.0, abs=1.0)
