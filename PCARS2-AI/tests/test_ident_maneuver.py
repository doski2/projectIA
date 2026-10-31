"""Tests de las maniobras de identificación (A1)."""

import pytest

from ident_maneuver import MAX_CAP_KMH, MAX_NEUTRAL_S, IdentManeuver, find_straights, select_straights

LENGTH = 3000.0
# Una recta de 1000 a 1700 m y otra que cruza la meta: de 2700 a 3000 + 200 m.
STRAIGHTS = [(1000.0, 1700.0), (2700.0, 3200.0)]


def _acel(cap=80.0, **kw):
    return IdentManeuver("acel", STRAIGHTS, LENGTH, cap_kmh=cap, **kw)


def _rodar(floor=30.0, **kw):
    return IdentManeuver("rodar", STRAIGHTS, LENGTH, floor_kmh=floor, **kw)


def _u(m, d, v_kmh, t=0.0, cte=0.0, allowed=True):
    return m.update(d, v_kmh / 3.6, cte, t, allowed)


def test_straight_found_between_two_curves():
    def curv(d):
        return 1 / 50.0 if (d < 300 or d >= 1700) else 0.0

    (start, end), = find_straights(curv, LENGTH, min_len_m=300)
    assert start == pytest.approx(300.0, abs=25) and end == pytest.approx(1700.0, abs=25)  # la media suaviza los bordes


def test_straight_crossing_the_finish_line():
    def curv(d):
        return 1 / 50.0 if 1000 <= d < 2000 else 0.0

    (start, end), = find_straights(curv, LENGTH, min_len_m=300)
    # de 2000 m hasta 1000 m de la vuelta siguiente: el fin pasa de la longitud de la pista
    assert start == pytest.approx(2000.0, abs=25) and end == pytest.approx(LENGTH + 1000.0, abs=25)


def test_alternating_noise_does_not_split_a_straight():
    def curv(d):
        return 0.002 if int(d) % 2 else -0.002  # ruido de signo alterno: media ≈ 0

    assert find_straights(curv, LENGTH) == [(0.0, LENGTH)]


def test_short_straights_are_dropped():
    def curv(d):
        return 0.0 if 100 <= d < 250 else 1 / 40.0

    assert find_straights(curv, LENGTH, min_len_m=300) == []


def test_acel_starts_inside_the_usable_zone_only():
    m = _acel()
    assert _u(m, 1010.0, 30.0) is None  # antes del margen de salida (20 m)
    assert _u(m, 1030.0, 30.0) == (1.0, 0.0)
    assert m.count == 1 and m.drive_source == "ident:acel"


def test_acel_ends_at_cap():
    m = _acel(cap=80.0)
    _u(m, 1030.0, 30.0)
    assert _u(m, 1200.0, 79.0) == (1.0, 0.0)
    assert _u(m, 1250.0, 80.0) is None
    assert not m.active
    assert _u(m, 1260.0, 50.0) is None  # una sola maniobra por pasada


def test_acel_ends_before_the_curve():
    m = _acel(end_margin_m=150.0)
    _u(m, 1030.0, 30.0)
    assert _u(m, 1550.0, 60.0) == (1.0, 0.0)
    assert _u(m, 1551.0, 60.0) is None  # 1700 - 150 = 1550: ya no queda sitio


def test_acel_does_not_start_near_the_cap():
    m = _acel(cap=80.0)
    assert _u(m, 1100.0, 79.0) is None


def test_rodar_coasts_down_to_floor():
    m = _rodar(floor=30.0)
    assert _u(m, 1030.0, 80.0) == (0.0, 0.0)
    assert _u(m, 1200.0, 45.0) == (0.0, 0.0)
    assert _u(m, 1300.0, 30.0) is None
    assert not m.active


def test_rodar_does_not_start_slow():
    m = _rodar(floor=30.0)
    assert _u(m, 1100.0, 33.0) is None


def test_cut_when_not_allowed_or_off_line():
    m = _acel()
    _u(m, 1030.0, 30.0)
    assert _u(m, 1040.0, 32.0, allowed=False) is None
    assert not m.active
    m2 = _acel()
    _u(m2, 1030.0, 30.0)
    assert _u(m2, 1040.0, 32.0, cte=1.5) is None
    assert not m2.active
    m3 = _acel()
    assert _u(m3, 1030.0, 30.0, cte=1.5) is None  # fuera de la línea no arranca
    assert m3.count == 0


def test_time_limit():
    m = _acel()
    _u(m, 1030.0, 30.0, t=0.0)
    assert _u(m, 1040.0, 31.0, t=1.0) == (1.0, 0.0)
    assert _u(m, 1050.0, 31.0, t=60.0) is None


def test_repeats_on_next_pass():
    m = _acel(cap=80.0)
    _u(m, 1030.0, 30.0)
    _u(m, 1300.0, 80.0)  # techo
    assert _u(m, 1400.0, 30.0) is None
    assert _u(m, 2000.0, 30.0) is None  # fuera de la recta: se libera
    assert _u(m, 1030.0, 30.0) == (1.0, 0.0)  # vuelta siguiente
    assert m.count == 2


def test_window_crossing_the_finish_line():
    m = _acel(cap=80.0)
    assert _u(m, 2750.0, 30.0) == (1.0, 0.0)
    assert _u(m, 2990.0, 50.0) == (1.0, 0.0)
    assert _u(m, 30.0, 60.0) == (1.0, 0.0)  # tras la meta sigue en la misma recta: la recta acaba en 3200 = 200 m
    assert _u(m, 60.0, 62.0) is None  # 200 m de recta - 150 m de margen = 3050 m = 50 m de vuelta: ya no queda zona útil


def test_acelrodar_accelerates_then_coasts():
    m = IdentManeuver("acelrodar", STRAIGHTS, LENGTH, cap_kmh=100.0, floor_kmh=60.0)
    assert _u(m, 1030.0, 40.0) == (1.0, 0.0) and m.drive_source == "ident:acel"
    assert _u(m, 1100.0, 99.0) == (1.0, 0.0) and m.drive_source == "ident:acel"
    assert _u(m, 1150.0, 100.0) == (0.0, 0.0) and m.drive_source == "ident:rodar"  # techo: suelta
    assert _u(m, 1300.0, 80.0) == (0.0, 0.0)
    assert _u(m, 1400.0, 60.0) is None  # suelo: vuelve el teacher
    assert not m.active and m.count == 1
    assert _u(m, 1450.0, 40.0) is None  # una sola pasada por recta


def test_acelrodar_ends_at_zone_end_while_coasting():
    m = IdentManeuver("acelrodar", STRAIGHTS, LENGTH, cap_kmh=100.0, floor_kmh=60.0, end_margin_m=150.0)
    _u(m, 1030.0, 40.0)
    _u(m, 1100.0, 100.0)
    assert _u(m, 1549.0, 90.0) == (0.0, 0.0)
    assert _u(m, 1551.0, 90.0) is None  # sin zona útil: el teacher frena antes de la curva


def test_acelrodar_needs_cap_and_floor():
    with pytest.raises(ValueError):
        IdentManeuver("acelrodar", STRAIGHTS, LENGTH, cap_kmh=0, floor_kmh=60)
    with pytest.raises(ValueError):
        IdentManeuver("acelrodar", STRAIGHTS, LENGTH, cap_kmh=100, floor_kmh=0)


def test_gear_change_does_not_cut_the_pass():
    m = _acel(cap=110.0)
    assert _u(m, 1030.0, 60.0, t=0.0) == (1.0, 0.0)
    assert m.update(1100.0, 70 / 3.6, 0.1, 1.0, True, neutral=True) == (0.0, 0.0)  # cambio: suelta el gas
    assert m.drive_source == "ident:cambio" and m.active
    assert m.update(1101.0, 70 / 3.6, 0.1, 1.2, True, neutral=True) == (0.0, 0.0)
    assert m.update(1103.0, 70 / 3.6, 0.1, 1.3, True) == (1.0, 0.0)  # ya en 2ª: sigue a fondo
    assert m.drive_source == "ident:acel" and m.active
    assert m.count == 1


def test_long_neutral_cuts_the_pass():
    m = _acel(cap=110.0)
    _u(m, 1030.0, 60.0, t=0.0)
    m.update(1100.0, 20.0, 0.1, 1.0, True, neutral=True)
    assert m.update(1105.0, 20.0, 0.1, 1.0 + MAX_NEUTRAL_S + 0.1, True, neutral=True) is None
    assert not m.active
    assert m.update(1110.0, 20.0, 0.1, 3.0, True) is None  # una pasada por recta


def test_does_not_start_in_neutral():
    m = _acel(cap=110.0)
    assert m.update(1030.0, 15.0, 0.1, 0.0, True, neutral=True) is None
    assert m.count == 0


def test_acelrodar_phase_survives_a_shift():
    m = IdentManeuver("acelrodar", STRAIGHTS, LENGTH, cap_kmh=100.0, floor_kmh=60.0)
    _u(m, 1030.0, 40.0)
    m.update(1060.0, 70 / 3.6, 0.1, 1.0, True, neutral=True)
    assert m.update(1062.0, 70 / 3.6, 0.1, 1.2, True) == (1.0, 0.0)
    assert m.update(1100.0, 100 / 3.6, 0.1, 2.0, True) == (0.0, 0.0) and m.drive_source == "ident:rodar"


def test_select_straights():
    assert select_straights(STRAIGHTS, "") == STRAIGHTS
    assert select_straights(STRAIGHTS, "1") == [STRAIGHTS[1]]
    assert select_straights(STRAIGHTS, "1, 0") == [STRAIGHTS[1], STRAIGHTS[0]]
    for bad in ("2", "-1", "a"):
        with pytest.raises(ValueError):
            select_straights(STRAIGHTS, bad)


def test_cap_above_the_gearbox_limit_is_refused():
    """H50: a 130 km/h el coche casi se va; el techo no puede pasar de lo que el cambio automático aguanta."""
    assert MAX_CAP_KMH <= 120.0
    IdentManeuver("acel", STRAIGHTS, LENGTH, cap_kmh=MAX_CAP_KMH)
    with pytest.raises(ValueError, match="máximo permitido"):
        IdentManeuver("acel", STRAIGHTS, LENGTH, cap_kmh=130.0)
    with pytest.raises(ValueError):
        IdentManeuver("acelrodar", STRAIGHTS, LENGTH, cap_kmh=160.0, floor_kmh=60.0)


def _frenar(caps=(60.0, 90.0), floor=30.0, **kw):
    return IdentManeuver("frenar", STRAIGHTS, LENGTH, floor_kmh=floor, caps_kmh=list(caps), **kw)


def test_frenar_sequence_accelerates_brakes_and_repeats():
    m = _frenar()
    assert _u(m, 1030.0, 40.0) == (1.0, 0.0) and m.drive_source == "ident:acel"  # parte de 40: acelera hasta 60
    assert _u(m, 1060.0, 59.0) == (1.0, 0.0)
    assert _u(m, 1070.0, 60.0) == (0.0, 1.0) and m.drive_source == "ident:frenar"  # entrada de 60: frena a fondo
    assert _u(m, 1090.0, 45.0) == (0.0, 1.0)
    assert _u(m, 1100.0, 30.0) == (1.0, 0.0) and m.drive_source == "ident:acel"  # suelo: a por la de 90
    assert _u(m, 1200.0, 89.0) == (1.0, 0.0)
    assert _u(m, 1210.0, 90.0) == (0.0, 1.0)
    assert _u(m, 1240.0, 30.0) is None  # última frenada hecha: vuelve el teacher
    assert not m.active and m.count == 1


def test_frenar_brakes_from_current_speed_if_already_above_first_entry():
    m = _frenar()
    assert _u(m, 1030.0, 70.0) == (0.0, 1.0) and m.drive_source == "ident:frenar"  # entra a 70 > 60: frena desde 70


def test_frenar_keeps_the_brake_through_a_downshift():
    m = _frenar()
    _u(m, 1030.0, 60.0)
    assert m.update(1050.0, 45 / 3.6, 0.1, 1.0, True, neutral=True) == (0.0, 1.0)  # punto muerto frenando: no suelta el freno
    assert m.update(1052.0, 44 / 3.6, 0.1, 1.2, True) == (0.0, 1.0)


def test_frenar_cut_at_zone_end_hands_over_to_the_teacher():
    m = _frenar(end_margin_m=150.0)
    _u(m, 1030.0, 40.0)
    assert _u(m, 1551.0, 50.0) is None


def test_frenar_validates_the_list():
    for caps in ([], [90.0, 60.0], [40.0], [60.0, 120.0]):
        with pytest.raises(ValueError):
            IdentManeuver("frenar", STRAIGHTS, LENGTH, floor_kmh=30.0, caps_kmh=caps)
    with pytest.raises(ValueError):
        IdentManeuver("frenar", STRAIGHTS, LENGTH, floor_kmh=0.0, caps_kmh=[60.0])


def test_invalid_args():
    with pytest.raises(ValueError):
        IdentManeuver("frenar", STRAIGHTS, LENGTH, cap_kmh=80)
    with pytest.raises(ValueError):
        IdentManeuver("acel", STRAIGHTS, LENGTH, cap_kmh=0)
    with pytest.raises(ValueError):
        IdentManeuver("rodar", STRAIGHTS, LENGTH, floor_kmh=0)


def test_short_windows_are_ignored():
    m = IdentManeuver("acel", [(100.0, 250.0)], LENGTH, cap_kmh=80)  # 150 m < margen de salida + margen de llegada
    assert m.windows == []
    assert _u(m, 150.0, 30.0) is None
