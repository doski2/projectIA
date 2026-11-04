"""Límite lateral por curva que se ajusta vuelta a vuelta (`--lat-adapt`, lat_adapt.py) y su efecto en el perfil del teacher."""

import math
import time
from pathlib import Path

import pytest

from lat_adapt import LatAdaptConfig, LatAdapter, Zone, drift_deg
from reference_recorder import ReferenceLine
from teacher_controller import TeacherConfig, TeachingController
from tests.test_brake_profile import RECETA

SUGO = str(Path(__file__).resolve().parents[1] / "src" / "refs" / "sugo_ai.json")
LARGO = 3500.0
ZONAS = [Zone(1, 200.0, 300.0), Zone(2, 400.0, 500.0), Zone(3, 800.0, 900.0)]


def _adaptador(**kw) -> LatAdapter:
    return LatAdapter(ZONAS, base_limit=9.5, track_length=LARGO, **kw)


def _vuelta(ad: LatAdapter, lap: int, cte=None, deriva=None, fuera=None):
    """Alimenta una vuelta entera (un tick cada 10 m). `cte`/`deriva`/`fuera`: {id de curva: valor}. Devuelve el resumen que da el primer tick de la vuelta siguiente."""
    cte, deriva, fuera = cte or {}, deriva or {}, fuera or {}
    for d in range(0, int(LARGO), 10):
        zona = next((z for z in ZONAS if z.s0 <= d <= z.s1), None)
        zid = zona.id if zona else 0
        beta = math.radians(deriva.get(zid, 0.0))
        ad.observe(lap, float(d), cte.get(zid, 0.2), 20.0 * math.sin(beta), -20.0 * math.cos(beta), bool(fuera.get(zid, False)))
    return ad.observe(lap + 1, 0.0, 0.0, 0.0, -20.0, False)


def test_drift_deg_matches_the_session_summary_formula():
    assert drift_deg(1.0, -20.0) == pytest.approx(2.862, abs=0.01)
    assert drift_deg(5.0, -3.0) == 0.0  # por debajo de 5 m/s no se mide


def test_a_clean_curve_goes_up_a_dirty_one_goes_down_and_freezes():
    ad = _adaptador()
    assert _vuelta(ad, 1) is None  # la vuelta de salida no cuenta
    up = _vuelta(ad, 2, cte={1: 0.5, 2: 2.5, 3: 1.5})
    assert up["decisions"] == {"1": "igual", "2": "baja", "3": "igual"}  # 1 tiene la vecina 2 en mal estado; 3 está entre 1,2 y 1,8
    assert ad.scales[2] == pytest.approx(0.92) and ad.frozen[2] == 2
    # vuelta siguiente, todo limpio: la 2 está congelada; la 1 ya no tiene la vecina mala pero la 2 sigue congelada (no es «mala»)
    up = _vuelta(ad, 3)
    assert up["decisions"]["2"] == "congelada" and up["decisions"]["1"] == "sube" and up["decisions"]["3"] == "sube"
    assert ad.scales[1] == pytest.approx(1.04) and ad.scales[2] == pytest.approx(0.92)


def test_wheels_off_or_drift_make_a_curve_bad_and_the_limits_are_capped():
    ad = _adaptador(cap_limit=10.0)
    _vuelta(ad, 1)
    r = _vuelta(ad, 2, fuera={1: True}, deriva={3: 5.0})
    assert r["decisions"]["1"] == "baja" and r["decisions"]["3"] == "baja"
    # tope: 10 / 9,5 = 1,0526 como máximo, aunque el multiplicador permitido sea 1,15
    for lap in range(3, 12):
        _vuelta(ad, lap)
    assert max(ad.scales.values()) == pytest.approx(10.0 / 9.5)
    assert max(ad.limits().values()) <= 10.0 + 1e-9


def test_scales_never_go_below_the_minimum():
    ad = _adaptador()
    _vuelta(ad, 1)
    for lap in range(2, 20):
        _vuelta(ad, lap, cte={2: 3.0})
    assert ad.scales[2] == pytest.approx(LatAdaptConfig().min_scale)


def test_incomplete_laps_and_laps_without_data_are_ignored():
    ad = _adaptador()
    _vuelta(ad, 1)
    for d in range(0, 1000, 10):  # media vuelta (reinicio): no se fía
        ad.observe(2, float(d), 3.0, 0.0, -20.0, False)
    assert ad.observe(3, 0.0, 0.0, 0.0, -20.0, False) is None
    assert all(v == 1.0 for v in ad.scales.values())


def test_scales_per_meter_cover_each_curve_and_its_exit_only():
    ad = _adaptador()
    ad.scales[2] = 0.9
    s = ad.scales_per_m()
    assert len(s) == int(LARGO) and s[450] == pytest.approx(0.9) and s[514] == pytest.approx(0.9)  # hasta la salida + 15 m
    assert s[520] == 1.0 and s[100] == 1.0 and s[399] == 1.0


def test_base_limit_above_the_cap_means_curves_can_go_down_but_not_up():
    ad = LatAdapter(ZONAS, base_limit=12.0, track_length=LARGO, cap_limit=10.0)
    _vuelta(ad, 1)
    _vuelta(ad, 2)
    assert max(ad.scales.values()) == 1.0


def _controlador(**cfg) -> TeachingController:
    return TeachingController(ReferenceLine.load(SUGO), TeacherConfig(**{**RECETA, "pedal_technique": True, "brake_profile": True, **cfg}))


def test_teacher_without_scales_keeps_the_same_profile_and_with_scales_only_changes_those_meters():
    base = _controlador()
    perfil0 = list(base.braking_profile())
    assert base._lat_scales is None
    n = len(perfil0)
    scales = [1.0] * n
    for d in range(300, 400):
        scales[d] = 0.8
    base.set_lat_scales(scales)
    perfil1 = base.braking_profile()
    assert max(abs(a - b) for a, b in zip(perfil0[1500:], perfil1[1500:])) < 1e-9  # lejos de la zona (y de la frenada que llega a ella) no cambia nada
    assert min(perfil1[300:400]) <= min(perfil0[300:400]) + 1e-9
    base.set_lat_scales(None)
    assert base.braking_profile() == perfil0  # volver a None restaura exactamente el perfil original


def test_recomputing_the_profile_after_a_lap_is_fast_enough_for_the_control_loop():
    c = _controlador(profile_peak_min_m=60.0, profile_peak_min_kmh=8.0)
    c.braking_profile()
    c.set_lat_scales([0.95] * len(c.braking_profile()))
    t0 = time.perf_counter()
    c.braking_profile()
    assert time.perf_counter() - t0 < 0.5  # si esto se acerca a 0,5 s, el coche conduciría a ciegas varios metros al cerrar cada vuelta
