"""Tests del análisis de A1 con ticks sintéticos (aceleración y deceleración conocidas)."""

import numpy as np
import pytest

from experimental.common import analisis_a1 as a1

DT = 1 / 60


def _ticks(kind, v0_kmh, accel_ms2, seconds, gear=1, t0=0.0, d0=1000.0):
    out = []
    n = int(seconds / DT)
    for i in range(n):
        t = i * DT
        v = v0_kmh / 3.6 + accel_ms2 * t
        out.append({
            "type": "tick", "t_s": t0 + t, "speed_kmh": v * 3.6, "gear": gear, "rpm": 4000.0, "lap": 1, "cte": 0.2,
            "lap_distance": d0 + i, "drive_source": kind,
            "vehicle": {"local_accel": [0.0, 0.0, -accel_ms2], "engine_torque": 120.0, "game_throttle": 1.0},
        })
    return out


def test_derivative_recovers_constant_acceleration():
    t = np.arange(0, 3, DT)
    v = 10 + 2.5 * t
    a = a1.derivative(t, v)
    assert np.nanmedian(a) == pytest.approx(2.5, abs=1e-6)


def test_acel_table_by_gear_and_speed_bin():
    ticks = _ticks("teacher:only", 25, 0, 1) + _ticks("ident:acel", 30, 3.0, 4.0, gear=1, t0=1.0)
    ticks += _ticks("teacher:only", 60, 0, 1, t0=6.0) + _ticks("ident:acel", 62, 2.0, 4.0, gear=2, t0=7.0)
    res = a1.analyze(ticks)
    assert len(res["passes"]) == 2
    table = res["summary"]["ident:acel"]["table"]
    g1 = [r for r in table if r["gear"] == 1]
    g2 = [r for r in table if r["gear"] == 2]
    assert g1 and g2
    assert all(r["a_med"] == pytest.approx(3.0, abs=0.01) for r in g1)
    assert all(r["a_med"] == pytest.approx(2.0, abs=0.01) for r in g2)
    assert res["local_accel_axis2_corr"] is not None


def test_rodar_gives_negative_acceleration():
    res = a1.analyze(_ticks("ident:rodar", 80, -0.6, 8.0, gear=3))
    table = res["summary"]["ident:rodar"]["table"]
    assert table and all(r["a_med"] == pytest.approx(-0.6, abs=0.01) for r in table)


def test_start_of_pass_is_trimmed():
    # los primeros 0,5 s tienen otra pendiente (el pedal aún no ha respondido) y no deben contar
    slow = _ticks("ident:acel", 30, 0.2, 0.5)
    fast = _ticks("ident:acel", 30.0 + 0.2 * 0.5 * 3.6, 3.0, 3.5, t0=0.5)
    res = a1.analyze(slow + fast)
    assert all(r["a_med"] == pytest.approx(3.0, abs=0.05) for r in res["summary"]["ident:acel"]["table"])


def test_split_passes_separates_by_kind_and_gap():
    ticks = (_ticks("ident:acel", 30, 3, 1) + _ticks("teacher:only", 50, 0, 1, t0=1.0)
             + _ticks("ident:acel", 30, 3, 1, t0=2.0) + _ticks("ident:rodar", 80, -0.5, 1, t0=3.0))
    assert [p[0]["drive_source"] for p in a1.split_passes(ticks)] == ["ident:acel", "ident:acel", "ident:rodar"]


def test_no_ident_ticks_returns_empty():
    res = a1.analyze(_ticks("teacher:only", 30, 0, 3))
    assert res["passes"] == []


def test_brake_event_survives_a_downshift_in_the_middle():
    # 100 -> 40 km/h a -10 m/s², con 10 ticks de punto muerto (`ident:cambio`) a mitad
    ticks = _ticks("teacher:only", 100, 0, 0.5)
    brk = _ticks("ident:frenar", 100, -10.0, 1.6, gear=2, t0=0.5, d0=1100.0)
    for x in brk[40:50]:
        x["drive_source"] = "ident:cambio"
        x["gear"] = 0
    ev = a1.analyze(ticks + brk + _ticks("teacher:only", 40, 0, 0.5, t0=2.2))["brake_events"]
    assert len(ev) == 1
    e = ev[0]
    assert e["v_in"] == pytest.approx(100.0, abs=0.5) and e["a_mean"] == pytest.approx(10.0, abs=0.3)
    assert e["a_peak"] == pytest.approx(10.0, abs=0.3) and 0 in e["gears"] and 2 in e["gears"]


def test_brake_table_is_in_the_summary():
    brk = _ticks("ident:frenar", 100, -10.0, 1.8, gear=2)
    res = a1.analyze(brk)
    assert res["summary"]["ident:frenar"]["table"]
    assert all(r["a_med"] < -9.0 for r in res["summary"]["ident:frenar"]["table"])
