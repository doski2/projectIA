"""Tests del solver de perfil de velocidad de A2 (`perfil_velocidad.py`) con pistas sintéticas de solución conocida."""

import math

import numpy as np
import pytest

from experimental.identificacion import perfil_velocidad as pv

N = 1000


def _car(mu=14.6, k=0.0, v_known_kmh=120.0, brake_delay_s=0.0):
    return pv.CarParams([(0.0, 4.0), (200.0, 4.0)], [(0.0, 10.0), (200.0, 10.0)], mu, k, v_known_kmh, brake_delay_s)


def _track(kappa=None, grade=None):
    return pv.Track(float(N), np.zeros(N) if kappa is None else kappa, np.zeros(N) if grade is None else grade)


def test_straight_lap_runs_at_the_cap():
    prof = pv.solve(_track(), _car(), cap_kmh=100.0)
    assert prof.time_s == pytest.approx(N / (100 / 3.6), rel=1e-3)
    assert prof.share_at_cap == pytest.approx(1.0)


def test_tables_limit_the_cap_to_the_known_range():
    prof = pv.solve(_track(), _car(v_known_kmh=90.0), cap_kmh=150.0)
    assert prof.v_ms.max() == pytest.approx(90 / 3.6)


def test_bend_speed_is_sqrt_mu_over_kappa_and_the_car_brakes_before_it():
    kappa = np.zeros(N)
    kappa[500:560] = 0.02  # R = 50 m
    prof = pv.solve(_track(kappa), _car(), cap_kmh=120.0)
    v_bend = math.sqrt(14.6 / 0.02)
    assert prof.v_ms[520] == pytest.approx(v_bend, rel=1e-3)
    before = prof.v_ms[400:500]
    assert np.all(np.diff(before) <= 1e-9) and before[0] > v_bend  # va bajando hasta la curva
    # a 10 m/s² de freno: la distancia de frenado de 120 a 97 km/h es la que dice la cinemática
    assert (np.flatnonzero(prof.v_ms[:500] < 120 / 3.6 - 1e-6)[0]) == pytest.approx(500 - (120 / 3.6) ** 2 / 20 + v_bend ** 2 / 20, abs=3)
    assert prof.share_lateral > 0 and prof.share_braking > 0 and prof.share_accel > 0


def test_downforce_term_k_raises_the_bend_speed():
    kappa = np.zeros(N)
    kappa[500:560] = 0.02
    base = pv.solve(_track(kappa), _car(), cap_kmh=120.0).v_ms[520]
    more = pv.solve(_track(kappa), _car(k=0.005), cap_kmh=120.0).v_ms[520]
    assert more > base
    assert more == pytest.approx(math.sqrt(14.6 / (0.02 - 0.005)), rel=1e-3)


def test_uphill_slows_the_acceleration_and_helps_the_braking():
    flat = pv.simulate_accel(_track(), _car(), 100.0, 10.0, 30.0)
    up = pv.simulate_accel(_track(grade=np.full(N, 0.10)), _car(), 100.0, 10.0, 30.0)
    assert up[0] == pytest.approx(flat[0] * 4.0 / (4.0 - 9.81 * 0.10), rel=0.02)  # 4 m/s² frente a 4 - 0,98
    b_flat = pv.simulate_brake(_track(), _car(), 100.0, 30.0, 10.0)
    b_up = pv.simulate_brake(_track(grade=np.full(N, 0.10)), _car(), 100.0, 30.0, 10.0)
    assert b_up[0] < b_flat[0]


def test_brake_delay_adds_time_and_distance_and_makes_the_lap_slower():
    kappa = np.zeros(N)
    kappa[500:560] = 0.02
    t0, d0 = pv.simulate_brake(_track(), _car(), 0.0, 30.0, 10.0)
    t1, d1 = pv.simulate_brake(_track(), _car(brake_delay_s=0.05), 0.0, 30.0, 10.0)
    assert t1 == pytest.approx(t0 + 0.05, abs=0.01) and d1 == pytest.approx(d0 + 30 * 0.05, abs=0.1)
    slow = pv.solve(_track(kappa), _car(brake_delay_s=0.1), cap_kmh=120.0)
    fast = pv.solve(_track(kappa), _car(), cap_kmh=120.0)
    assert slow.time_s > fast.time_s


def test_table_points_parse_the_ranges_and_cut_from_the_minimum_speed():
    rows = [{"v_kmh": "30-40", "a_med": 5.8}, {"v_kmh": "10-20", "a_med": 10.0}, {"v_kmh": "40-50", "a_med": 5.7}]
    assert pv.table_points(rows) == [(15.0, 10.0), (35.0, 5.8), (45.0, 5.7)]
    assert pv.table_points(rows, min_kmh=30.0) == [(35.0, 5.8), (45.0, 5.7)]


def test_car_params_round_trip(tmp_path):
    car = _car(brake_delay_s=0.04)
    pv.save_params(car, tmp_path / "p.json", {"x": 1})
    back = pv.load_params(tmp_path / "p.json")
    assert back.to_dict() == pytest.approx(car.to_dict()) or back.to_dict() == car.to_dict()


def test_grade_from_ticks_recovers_a_known_slope():
    ticks = [{"lap": 1, "lap_distance": d + 0.5, "vehicle": {"position": [0.0, 0.05 * d, d]}} for d in range(N)]
    # una cuesta del 5 % en todo el perímetro no es periódica: se mira el interior, lejos de la costura de la vuelta
    g = pv.grade_from_ticks(ticks, N)
    assert g is not None and g[500] == pytest.approx(0.05, abs=1e-6)


def test_grade_from_ticks_needs_a_complete_lap():
    ticks = [{"lap": 1, "lap_distance": float(d), "vehicle": {"position": [0.0, 0.0, float(d)]}} for d in range(300)]
    assert pv.grade_from_ticks(ticks, N) is None


def test_sugo_reference_lap_at_60_kmh_takes_the_reference_time():
    track = pv.Track.from_reference()
    assert track.length_m == pytest.approx(3567.0, abs=1.0)
    prof = pv.solve(track, _car(), cap_kmh=60.0)
    assert prof.time_s == pytest.approx(track.length_m / (60 / 3.6), rel=0.03)
    assert np.isfinite(track.kappa).all() and track.kappa.max() < 0.1
