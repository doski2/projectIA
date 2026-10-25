"""Informe de progreso de PPO: dice si la política va mejorando o solo se mantiene."""

from ppo_progress import assess


def _m(step, speed, cte, std=0.1, stuck=0, lap=0, kl=0.01):
    return {
        "total_timesteps": str(step), "avg_speed_kmh": str(speed), "avg_cte": str(cte),
        "std": str(std), "pct_stuck": str(stuck), "pct_lap_done": str(lap), "approx_kl": str(kl),
    }


def _ep(step, fin="lap_done", lap=None, target=60.0):
    return {"total_timesteps": str(step), "fin": fin, "lap_time_s": "" if lap is None else str(lap),
            "objetivo_kmh": str(target)}


def _status(report, key):
    return next(r for r in report if r[0] == key)[1]


def test_improving_run_is_flagged_as_good():
    metrics = [_m(i * 2048, 56 + i * 0.2, 0.9) for i in range(40)]
    eps = [_ep(20000, lap=215.0), _ep(40000, lap=212.0), _ep(60000, lap=209.0), _ep(80000, lap=207.0)]
    rep = assess(metrics, eps)
    assert _status(rep, "ritmo") == "bien" and _status(rep, "vueltas") == "bien"
    assert _status(rep, "estabilidad") == "bien" and _status(rep, "conclusion") == "bien"


def test_flat_run_is_neutral_not_good():
    metrics = [_m(i * 2048, 59.0, 0.9) for i in range(40)]
    eps = [_ep(20000, lap=212.0), _ep(40000, lap=212.4), _ep(60000, lap=211.9)]
    rep = assess(metrics, eps)
    assert _status(rep, "ritmo") == "igual" and _status(rep, "conclusion") != "bien"


def test_degrading_cte_or_stuck_is_bad():
    metrics = [_m(i * 2048, 59, 0.9 if i < 20 else 1.9) for i in range(40)]
    assert _status(assess(metrics, []), "estabilidad") == "mal"
    metrics = [_m(i * 2048, 59, 0.9, stuck=50 if i > 30 else 0) for i in range(40)]
    assert _status(assess(metrics, []), "estabilidad") == "mal"


def test_not_enough_data_says_so():
    rep = assess([_m(2048, 59, 0.9)], [])
    assert _status(rep, "conclusion") == "pocos datos"


def test_since_keeps_only_rows_from_that_time_on():
    from ppo_progress import since

    rows = [{"timestamp": "21:10:00"}, {"timestamp": "22:43:05"}, {"timestamp": "23:01:00"}]
    assert [r["timestamp"] for r in since(rows, "22:43")] == ["22:43:05", "23:01:00"]


def test_a_single_isolated_stuck_is_not_a_bad_verdict():
    metrics = [_m(i * 2048, 59, 0.9, stuck=100 if i == 33 else 0) for i in range(40)]
    eps = [_ep(i * 20000, lap=212.0) for i in range(1, 11)] + [_ep(300000, fin="stuck")]
    assert _status(assess(metrics, eps), "estabilidad") == "bien"
    eps += [_ep(310000, fin="stuck"), _ep(320000, fin="stuck")]       # 3 de 13: ya es un patrón
    assert _status(assess(metrics, eps), "estabilidad") == "mal"
