"""Tests de la rampa de arcos de A1.3."""

import pytest

from ident_arc import ACTIVATE_WITHIN_M, MAX_ARC_KMH, TAG_ARC, TAG_LANDING, ArcRamp

LENGTH = 3567.0


def _arc(speeds=(80.0, 85.0, 90.0), **kw):
    return ArcRamp(speeds, 3200.0, 600.0, LENGTH, 60.0, **kw)


def _u(a, d, v_kmh=60.0, t=0.0, cte=0.2, heading=0.02, off=False, allowed=True):
    return a.update(d, v_kmh / 3.6, cte, heading, off, t, allowed)


def test_starts_at_the_beginning_of_the_window_with_the_first_speed():
    a = _arc()
    assert _u(a, 3100.0).target_kmh is None  # antes de la ventana
    dec = _u(a, 3210.0, 60.0)
    assert dec.target_kmh == 80.0 and dec.free_lateral and dec.tag == TAG_ARC
    assert dec.event["phase"] == "start" and dec.event["target_kmh"] == 80.0
    assert _u(a, 3500.0, 75.0).target_kmh == 80.0  # sigue mientras dure la ventana


def test_does_not_start_in_the_middle_of_the_window():
    """La salida parada cae dentro de la ventana, pero sin la recta de aceleración la pasada no vale."""
    a = _arc()
    assert _u(a, 25.0, 48.0).target_kmh is None
    assert _u(a, 3200.0 + ACTIVATE_WITHIN_M + 1, 60.0).target_kmh is None
    assert a.state == "idle"


def test_clean_pass_advances_to_the_next_speed_on_the_next_lap():
    a = _arc()
    _u(a, 3210.0)
    _u(a, 300.0, 80.0)  # cruza la meta dentro de la ventana
    dec = _u(a, 601.0, 80.0)  # fuera: pasada limpia
    assert dec.target_kmh is None and dec.event["result"] == "clean"
    assert a.clean_speeds == [80.0] and a.k == 1 and not a.finished
    assert _u(a, 2000.0).target_kmh is None
    assert _u(a, 3210.0).target_kmh == 85.0  # vuelta siguiente: 85


def test_all_speeds_done_finishes():
    a = _arc(speeds=(80.0,))
    _u(a, 3210.0)
    dec = _u(a, 601.0, 80.0)
    assert a.finished and dec.event["result"] == "clean"
    assert _u(a, 3210.0).target_kmh is None  # no hay más pasadas


@pytest.mark.parametrize("kwargs,text", [
    ({"cte": 2.6}, "CTE"),
    ({"heading": 0.31}, "rumbo"),
    ({"off": True}, "asfalto"),
    ({"allowed": False}, "control"),
])
def test_limit_criteria_cut_the_pass_and_finish(kwargs, text):
    a = _arc()
    _u(a, 3210.0)
    dec = _u(a, 300.0, 82.0, t=10.0, **kwargs)
    assert dec.event["result"] == "limit" and text in dec.event["reason"]
    assert a.finished and a.limit_speed_kmh == 80.0 and a.state == "landing"
    assert dec.tag == TAG_LANDING and dec.free_lateral
    assert dec.target_kmh == pytest.approx(82.0)  # arranca desde la velocidad que lleva, no desde la consigna


def test_cte_at_the_limit_does_not_cut():
    a = _arc()
    _u(a, 3210.0)
    assert _u(a, 300.0, 80.0, cte=2.5).tag == TAG_ARC
    assert _u(a, 310.0, 80.0, cte=-2.4, heading=-0.29).tag == TAG_ARC  # el signo no importa


def test_soft_landing_decays_slowly_to_the_band_and_ends_with_the_window():
    a = _arc(decay_kmh_s=6.0)
    _u(a, 3210.0)
    _u(a, 300.0, 100.0, t=10.0, cte=3.0)  # corte a 100 km/h
    assert _u(a, 320.0, 99.0, t=11.0).target_kmh == pytest.approx(94.0)
    assert _u(a, 340.0, 90.0, t=12.0).target_kmh == pytest.approx(88.0)
    assert _u(a, 400.0, 70.0, t=20.0).target_kmh == pytest.approx(60.0)  # no baja de la banda
    assert _u(a, 400.0, 70.0, t=20.0).free_lateral  # sin límite lateral: no se frena a fondo con el volante girado
    dec = _u(a, 601.0, 62.0, t=25.0)
    assert dec.target_kmh is None and a.state == "idle" and a.finished
    assert _u(a, 3210.0).target_kmh is None  # tras el límite no hay más pasadas


def test_validation():
    with pytest.raises(ValueError):
        ArcRamp([], 3200.0, 600.0, LENGTH, 60.0)
    with pytest.raises(ValueError):
        ArcRamp([90.0, 80.0], 3200.0, 600.0, LENGTH, 60.0)
    with pytest.raises(ValueError, match="máximo permitido"):
        ArcRamp([80.0, MAX_ARC_KMH + 1], 3200.0, 600.0, LENGTH, 60.0)
    with pytest.raises(ValueError, match="banda"):
        ArcRamp([62.0], 3200.0, 600.0, LENGTH, 60.0)
    with pytest.raises(ValueError):
        ArcRamp([80.0], 3200.0, 3200.0, LENGTH, 60.0)
    with pytest.raises(ValueError):
        ArcRamp([80.0], 3200.0, 600.0, LENGTH, 60.0, cte_limit_m=0.0)
    assert MAX_ARC_KMH < 115.0
