"""Tests del análisis de A1 con ticks sintéticos (aceleración y deceleración conocidas)."""

import json

import numpy as np
import pytest

from experimental.common import analisis_a1 as a1

DT = 1 / 60


def _ticks(kind, v0_kmh, accel_ms2, seconds, gear=1, t0=0.0, d0=1000.0, slope=0.0):
    """Ticks con aceleración constante y la pista subiendo `slope` (0,1 = 10 %): la posición avanza por z y sube por y."""
    out = []
    n = int(seconds / DT)
    for i in range(n):
        t = i * DT
        v = v0_kmh / 3.6 + accel_ms2 * t
        z = (v0_kmh / 3.6) * t + 0.5 * accel_ms2 * t * t
        out.append({
            "type": "tick", "t_s": t0 + t, "speed_kmh": v * 3.6, "gear": gear, "rpm": 4000.0, "lap": 1, "cte": 0.2,
            "lap_distance": d0 + i, "drive_source": kind,
            "vehicle": {"local_accel": [0.0, 0.0, -accel_ms2], "engine_torque": 120.0, "game_throttle": 1.0,
                        "position": [0.0, slope * z, z]},
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
    assert e["a_mean_raw"] == pytest.approx(10.0, abs=0.3) and e["grade_pct"] == pytest.approx(0.0, abs=0.1)
    assert e["a_peak"] == pytest.approx(10.0, abs=0.3) and 0 in e["gears"] and 2 in e["gears"]


def test_brake_curve_is_in_the_result():
    res = a1.analyze(_ticks("ident:frenar", 100, -10.0, 1.8, gear=2))
    assert res["brake_curve"]
    assert all(r["a_med"] == pytest.approx(-10.0, abs=0.1) for r in res["brake_curve"])


def test_slope_is_removed_from_acceleration():
    """Subiendo un 10 % el coche mide 3,0 m/s², pero en llano daría 3,0 + 9,81 · 0,1 ≈ 3,98."""
    res = a1.analyze(_ticks("ident:acel", 30, 3.0, 4.0, gear=1, slope=0.10))
    table = res["summary"]["ident:acel"]["table"]
    assert table
    for r in table:
        assert r["a_raw_med"] == pytest.approx(3.0, abs=0.02)
        assert r["a_med"] == pytest.approx(3.0 + 9.81 * 0.10, abs=0.05)
        assert r["grade_med_pct"] == pytest.approx(10.0, abs=0.5)


def test_slope_is_removed_from_braking():
    """Frenando cuesta arriba el coche mide -10 m/s²: la pendiente ayuda ≈ 0,98, así que el freno solo da ≈ 9,02."""
    ev = a1.analyze(_ticks("ident:frenar", 100, -10.0, 1.8, gear=2, slope=0.10))["brake_events"]
    assert len(ev) == 1
    assert ev[0]["a_mean_raw"] == pytest.approx(10.0, abs=0.2)
    assert ev[0]["a_mean"] == pytest.approx(10.0 - 0.981, abs=0.2)
    assert ev[0]["grade_pct"] == pytest.approx(10.0, abs=0.5)


def test_missing_position_falls_back_to_no_correction():
    ticks = _ticks("ident:acel", 30, 3.0, 4.0, gear=1)
    for t in ticks:
        t["vehicle"].pop("position")
    r = a1.analyze(ticks)["summary"]["ident:acel"]["table"]
    assert r and all(x["a_med"] == pytest.approx(3.0, abs=0.02) and x["no_grade"] == x["n"] for x in r)


def _arc_ticks(target_kmh, lat, cte, lap=2, t0=0.0, d0=3300.0):
    """Una pasada de 12 s: recta de aproximación y curvas (228-600 m) con aceleración lateral `lat`."""
    out = []
    for i in range(720):
        d = (d0 + i * 1.0) % 3567.0
        in_bends = 228.0 <= d <= 600.0
        out.append({
            "type": "tick", "t_s": t0 + i * DT, "speed_kmh": target_kmh, "gear": 2, "rpm": 6000.0, "lap": lap, "cte": abs(cte),
            "signed_cte": cte if in_bends else 0.1, "heading_err": 0.05, "steering": 0.25 if in_bends else 0.0,
            "lap_distance": d, "drive_source": "ident:arco",
            "vehicle": {"local_accel": [lat if in_bends else 0.5, 0.0, 0.0], "tyre_temp": [90, 90, 88, 88], "tyre_wear": [1, 1, 0, 0]},
        })
    return out


def test_arc_passes_are_summarised_per_pass_with_their_event():
    ticks = _arc_ticks(80.0, 11.0, -1.2) + _ticks("teacher:only", 60, 0, 1, t0=20.0) + _arc_ticks(85.0, 12.5, -1.5, lap=3, t0=30.0)
    events = [
        {"type": "arc_pass", "phase": "start", "k": 0, "target_kmh": 80.0}, {"type": "arc_pass", "phase": "end", "k": 0, "result": "clean"},
        {"type": "arc_pass", "phase": "start", "k": 1, "target_kmh": 85.0},
        {"type": "arc_pass", "phase": "end", "k": 1, "result": "limit", "reason": "|CTE| 2.60 m > 2.5"},
    ]
    rows = a1.analyze(ticks, events)["arc_passes"]
    assert [r["target_kmh"] for r in rows] == [80.0, 85.0]
    assert rows[0]["result"] == "clean" and rows[1]["result"] == "limit" and "CTE" in rows[1]["reason"]
    assert rows[0]["lat_p95"] == pytest.approx(11.0, abs=0.01) and rows[1]["lat_max"] == pytest.approx(12.5, abs=0.01)
    assert rows[0]["max_cte"] == pytest.approx(1.2) and rows[0]["v_bends_med_kmh"] == pytest.approx(80.0)
    # 1/R equivalente = lateral / v²: 11 / (80/3,6)² ≈ 0,0223 1/m (R ≈ 45 m)
    assert rows[0]["lat_over_v2"] == pytest.approx(11.0 / (80 / 3.6) ** 2, rel=0.01)
    assert rows[0]["lap"] == 2 and rows[1]["lap"] == 3


def test_no_arc_ticks_gives_no_arc_rows():
    assert a1.analyze(_ticks("teacher:only", 60, 0, 2))["arc_passes"] == []


def test_brake_distance_survives_crossing_the_finish_line():
    """Una frenada que empieza a 3550 m y acaba tras la meta (3567 m) no puede dar una distancia de 96 000 m (V29)."""
    ticks = _ticks("ident:frenar", 100, -10.0, 1.8, gear=2, d0=3550.0)
    for t in ticks:
        t["lap_distance"] = t["lap_distance"] % 3567.0
    ev = a1.analyze(ticks)["brake_events"]
    assert len(ev) == 1
    assert 90 <= ev[0]["dist_m"] <= 110


def test_report_does_not_crash_when_a_brake_event_has_no_peak(tmp_path, capsys):
    """Una frenada cortada al final de la sesión deja `a_peak` en None; el informe de texto debe imprimirla igualmente (V29)."""
    ticks = _ticks("ident:acel", 30, 3.0, 4.0, gear=1) + _ticks("ident:frenar", 100, -10.0, 0.17, gear=2, t0=5.0)  # 10 ticks de frenada: llega al mínimo, pero no queda tramo central para el pico
    ev = a1.analyze(ticks)["brake_events"]
    assert len(ev) == 1 and ev[0]["a_peak"] is None
    log = tmp_path / "log.jsonl"
    log.write_text(chr(10).join(json.dumps(t) for t in ticks) + chr(10), encoding="utf-8")
    assert a1.main([str(log)]) == 0
    assert "frenadas a fondo" in capsys.readouterr().out
