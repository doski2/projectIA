"""Tests de la perturbación de velocidad (P24)."""

import pytest

from speed_perturbation import MAX_COAST_S, MAX_RECOVER_S, SpeedPerturber

TARGET = 20.0 / 3.6


def _run(p, d, v_kmh, t, allowed=True):
    return p.update(d, v_kmh / 3.6, TARGET, t, allowed)


def test_no_coast_before_first_mark():
    p = SpeedPerturber(period_m=250.0)
    assert _run(p, 120.0, 20.0, 1.0) is False
    assert _run(p, 249.0, 20.0, 2.0) is False
    assert p.count == 0


def test_coasts_until_drop_then_releases_until_recovered():
    p = SpeedPerturber(period_m=250.0, drop_kmh=4.5)
    assert _run(p, 251.0, 20.0, 10.0) is True
    assert p.count == 1
    assert _run(p, 260.0, 18.0, 11.0) is True  # aún no ha perdido 4,5
    assert _run(p, 270.0, 15.4, 12.0) is False  # ya: se suelta
    assert p.state == "recovering"
    assert _run(p, 280.0, 17.0, 13.0) is False  # sigue sin tocar nada hasta volver
    assert _run(p, 290.0, 19.9, 14.0) is False
    assert p.state == "idle"
    assert _run(p, 300.0, 20.0, 15.0) is False  # el siguiente punto es 500 m
    assert _run(p, 501.0, 20.0, 30.0) is True
    assert p.count == 2


def test_does_not_start_when_not_at_speed():
    p = SpeedPerturber(period_m=250.0)
    assert _run(p, 255.0, 14.0, 1.0) is False
    assert p.count == 0


def test_skips_mark_it_could_not_use():
    p = SpeedPerturber(period_m=250.0)
    _run(p, 255.0, 14.0, 1.0)
    _run(p, 505.0, 14.0, 2.0)  # dos puntos seguidos sin poder
    assert _run(p, 520.0, 20.0, 3.0) is False
    assert _run(p, 751.0, 20.0, 4.0) is True


def test_coast_has_time_limit():
    p = SpeedPerturber(period_m=250.0)
    assert _run(p, 251.0, 20.0, 0.0) is True
    assert _run(p, 255.0, 19.9, MAX_COAST_S - 0.1) is True
    assert _run(p, 260.0, 19.9, MAX_COAST_S + 0.1) is False
    assert p.state == "recovering"


def test_recovery_has_time_limit():
    p = SpeedPerturber(period_m=250.0)
    _run(p, 251.0, 20.0, 0.0)
    _run(p, 255.0, 15.0, 1.0)
    assert p.state == "recovering"
    _run(p, 260.0, 15.0, 1.0 + MAX_RECOVER_S + 1.0)
    assert p.state == "idle"


def test_not_allowed_cuts_the_coast():
    p = SpeedPerturber(period_m=250.0)
    assert _run(p, 251.0, 20.0, 0.0) is True
    assert _run(p, 255.0, 19.0, 1.0, allowed=False) is False
    assert p.state == "recovering"
    assert _run(p, 260.0, 19.0, 2.0, allowed=False) is False
    assert p.state == "recovering"


def test_marks_repeat_on_new_lap():
    p = SpeedPerturber(period_m=250.0)
    _run(p, 251.0, 20.0, 0.0)
    _run(p, 255.0, 15.0, 1.0)
    _run(p, 260.0, 20.0, 2.0)
    assert p.state == "idle"
    _run(p, 3560.0, 14.0, 3.0)  # lento al final de la vuelta: no perturba y el siguiente punto queda lejos
    assert _run(p, 5.0, 20.0, 4.0) is False  # vuelta nueva: los puntos se repiten desde 250 m
    assert _run(p, 251.0, 20.0, 5.0) is True


def test_invalid_args():
    with pytest.raises(ValueError):
        SpeedPerturber(period_m=0.0)
    with pytest.raises(ValueError):
        SpeedPerturber(period_m=100.0, drop_kmh=0.0)
