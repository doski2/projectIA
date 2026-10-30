"""Tests del currículo de aprendizaje online."""

from learning_curriculum import (
    DEFAULT_SPEED_BAND_KMH,
    evaluate_lap,
    evaluate_learn_session,
    evaluate_objectives,
    effective_min_avg_speed,
    get_learn_stage,
    resolve_learn_speed,
    resolve_stage_speed,
    try_advance_speed_band,
    try_advance_stage,
)


def _lap_tick(cte=2.0, override=False, reason="maintain_speed", speed=15.0, throttle=0.1, brake=0.0):
    return {
        "speed_kmh": speed,
        "throttle": throttle,
        "brake": brake,
        "cte": cte,
        "safety_override": override,
        "teacher_reason": reason,
        "stuck": False,
    }


def test_resolve_stage_speed_uses_stage_or_override():
    assert resolve_stage_speed("l1_linea", 0) == 15.0
    assert resolve_stage_speed("l1_linea", 22.0) == 22.0


def test_resolve_learn_speed_band_then_override():
    assert resolve_learn_speed("l1_linea", 30.0, 0) == 30.0
    assert resolve_learn_speed("l1_linea", 30.0, 25.0) == 25.0


def test_effective_min_avg_speed_scales_with_band():
    stage = get_learn_stage("l2_velocidad")
    assert effective_min_avg_speed(stage, 20.0) == 18.0
    assert effective_min_avg_speed(stage, 40.0) == 36.0


def test_advance_l5_to_l6():
    stage = get_learn_stage("l5_rapido")
    new_id, advanced, _ = try_advance_stage("l5_rapido", stage.clean_laps_required)
    assert advanced is True
    assert new_id == "l6_sostenido"


def test_advance_speed_band_after_l7():
    stage = get_learn_stage("l7_banda")
    new_band, advanced, new_stage, msg = try_advance_speed_band(
        DEFAULT_SPEED_BAND_KMH, "l7_banda", stage.clean_laps_required,
    )
    assert advanced is True
    assert new_band == 30.0
    assert new_stage == "l1_linea"
    assert "30" in msg


def test_clean_lap_l1():
    ticks = [_lap_tick() for _ in range(100)]
    ev = evaluate_lap(ticks, "l1_linea")
    assert ev["clean"] is True


def test_dirty_lap_high_cte():
    ticks = [_lap_tick(cte=8.0) for _ in range(50)]
    ev = evaluate_lap(ticks, "l1_linea")
    assert ev["clean"] is False


def test_l1_lap_ignores_launch_below_min_speed():
    ticks = [_lap_tick(speed=v) for v in (0.0, 5.0, 12.0)] + [_lap_tick(speed=20.0) for _ in range(100)]
    ev = evaluate_lap(ticks, "l1_linea", speed_band_kmh=20.0)
    assert ev["clean"] is True
    assert ev["min_speed_kmh"] == 20.0


def test_l1_lap_with_stall_is_dirty():
    """P23 / H31: el coche se arrastra a 11 km/h con CTE bueno y la vuelta no debe contar."""
    ticks = [_lap_tick(speed=20.0) for _ in range(100)]
    ticks += [_lap_tick(speed=11.0) for _ in range(20)]
    ticks += [_lap_tick(speed=20.0) for _ in range(100)]
    ev = evaluate_lap(ticks, "l1_linea", speed_band_kmh=20.0)
    assert ev["clean"] is False
    assert ev["min_speed_kmh"] == 11.0
    assert "vel mín" in ev["summary"]


def test_l1_lap_that_never_reaches_speed_is_dirty():
    ticks = [_lap_tick(speed=10.0) for _ in range(100)]
    ev = evaluate_lap(ticks, "l1_linea", speed_band_kmh=20.0)
    assert ev["clean"] is False
    assert ev["min_speed_kmh"] is None
    assert "sin alcanzar" in ev["summary"]


def test_l1_lap_overlap_limit():
    ticks = [_lap_tick(speed=20.0) for _ in range(10000)]
    ticks[5].update(throttle=0.1, brake=0.03)  # 1 tick: 0,01 %, dentro del límite
    assert evaluate_lap(ticks, "l1_linea", speed_band_kmh=20.0)["clean"] is True
    for t in ticks[100:120]:  # 21 ticks: 0,21 %
        t.update(throttle=0.1, brake=0.03)
    ev = evaluate_lap(ticks, "l1_linea", speed_band_kmh=20.0)
    assert ev["clean"] is False
    assert "gas+freno" in ev["summary"]


def _timed(speeds, straight, dt=0.1, t0=0.0):
    out = []
    for i, (v, s) in enumerate(zip(speeds, straight)):
        t = _lap_tick(speed=v)
        t.update(t_s=t0 + i * dt, straight=s)
        out.append(t)
    return out


def test_min_speed_ignores_curves_and_their_exit():
    """60 km/h: el teacher frena en curva (35) y la sale acelerando; solo cuenta la recta una vez a velocidad."""
    ticks = _timed([60.0] * 50, [True] * 50)
    ticks += _timed([40.0, 35.0, 35.0, 38.0], [False] * 4, t0=5.0)
    ticks += _timed([40.0, 45.0, 50.0, 55.0] + [60.0] * 40, [True] * 44, t0=6.0)
    ev = evaluate_lap(ticks, "l1_linea", speed_band_kmh=60.0)
    assert ev["clean"] is True
    assert ev["min_speed_kmh"] == 55.0  # la recta de salida cuenta desde que llega a 51 (85 % de 60)


def test_min_speed_catches_stall_on_straight():
    ticks = _timed([60.0] * 50 + [40.0] * 10 + [60.0] * 50, [True] * 110)
    ev = evaluate_lap(ticks, "l1_linea", speed_band_kmh=60.0)
    assert ev["clean"] is False
    assert ev["min_speed_kmh"] == 40.0


def test_min_speed_long_straight_that_never_reaches_speed_is_dirty():
    ticks = _timed([60.0] * 20, [True] * 20) + _timed([30.0] * 150, [True] * 150, t0=2.0)
    # una sola racha: alcanza 60 y cae a 30 -> sucia por caída
    assert evaluate_lap(ticks, "l1_linea", speed_band_kmh=60.0)["clean"] is False
    solo_lenta = _timed([30.0] * 150, [True] * 150)  # 14,9 s sin llegar a 51: más que los 10 s de gracia
    assert evaluate_lap(solo_lenta, "l1_linea", speed_band_kmh=60.0)["min_speed_kmh"] is None


def test_short_straight_that_does_not_reach_speed_is_forgiven():
    ticks = _timed([60.0] * 50, [True] * 50)
    ticks += _timed([35.0] * 30, [False] * 30, t0=5.0)
    ticks += _timed([40.0, 42.0, 44.0], [True] * 3, t0=8.0)  # recta corta, sin llegar a 51
    ticks += _timed([35.0] * 30, [False] * 30, t0=8.3)
    ev = evaluate_lap(ticks, "l1_linea", speed_band_kmh=60.0)
    assert ev["clean"] is True


def test_straight_speed_dev_is_informative():
    ticks = _timed([60.0, 61.0] * 40, [True] * 80)
    ev = evaluate_lap(ticks, "l1_linea", speed_band_kmh=60.0)
    assert ev["straight_dev_kmh"] == 0.5
    assert ev["clean"] is True


def test_l2_lap_not_affected_by_min_speed_or_overlap():
    ticks = [_lap_tick(speed=20.0) for _ in range(100)]
    ticks[10].update(speed=5.0)
    ticks[20].update(throttle=0.5, brake=0.5)
    assert evaluate_lap(ticks, "l2_velocidad")["clean"] is True


def test_advance_after_clean_streak():
    stage = get_learn_stage("l1_linea")
    new_id, advanced, _ = try_advance_stage("l1_linea", stage.clean_laps_required)
    assert advanced is True
    assert new_id == "l2_velocidad"


def test_no_advance_without_streak():
    _, advanced, msg = try_advance_stage("l1_linea", 0)
    assert advanced is False
    assert "0/" in msg


def test_objectives_l1():
    objs = evaluate_objectives(
        "l1_linea",
        {"avg_cte": 3.0, "pct_safety_override": 5.0, "avg_speed_kmh": 16.0, "pct_brake_reason": 10.0},
        [{"lap_time_s": 120.0}],
        clean_streak=2,
    )
    assert len(objs) == 3
    assert all(o["ok"] for o in objs)


def test_dirty_lap_reports_stuck_in_summary():
    ticks = [_lap_tick() for _ in range(50)]
    for t in ticks[:10]:
        t["stuck"] = True
    ev = evaluate_lap(ticks, "l1_linea")
    assert ev["clean"] is False
    assert "stuck" in ev["summary"]


def test_evaluate_learn_session_ignores_settle_ticks():
    ticks = []
    for _ in range(100):
        ticks.append({
            "t_s": len(ticks) * 0.1,
            "cte": 2.0,
            "speed_kmh": 20.0,
            "safety_override": False,
            "off_track": False,
            "stuck": False,
            "teacher_reason": "hold",
            "drive_source": "bc",
        })
    for _ in range(20):
        ticks.append({
            "t_s": len(ticks) * 0.1,
            "cte": 2.0,
            "speed_kmh": 5.0,
            "safety_override": False,
            "off_track": False,
            "stuck": True,
            "teacher_reason": "hold",
            "drive_source": "settle:finish_line",
        })

    ev = evaluate_learn_session(ticks, 1, "l1_linea", clean_streak=2)
    assert ev["metrics"]["pct_stuck"] == 0.0


def test_objectives_l2_speed_band_scales_target():
    objs = evaluate_objectives(
        "l2_velocidad",
        {"avg_cte": 3.0, "pct_safety_override": 5.0, "avg_speed_kmh": 27.0, "pct_brake_reason": 10.0},
        [{"lap_time_s": 120.0}],
        clean_streak=2,
        speed_band_kmh=30.0,
    )
    vel = next(o for o in objs if o["id"] == "velocidad")
    assert vel["threshold"] == "≥ 27.0km/h"
    assert vel["ok"] is True
