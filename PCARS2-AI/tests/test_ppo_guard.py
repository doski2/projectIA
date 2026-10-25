# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
"""Puerta de velocidad y protección para dejar PPO sin vigilancia."""

import json
from unittest.mock import MagicMock

from ppo_guard import SpeedGate, SpeedGateCallback


def _ep(reason="lap_done", cte=0.9, speed=61.0):
    return {"term_reason": reason, "ep_cte_mean": cte, "ep_speed_kmh": speed}


def _gate(**kw):
    return SpeedGate(target_kmh=60.0, **kw)


def test_three_clean_episodes_raise_the_target_by_one_small_step():
    g = _gate(step_kmh=2.5)
    assert [g.on_episode(_ep()) for _ in range(3)] == ["none", "none", "raise"]
    assert g.target_kmh == 62.5 and g.safe_target_kmh == 60.0


def test_a_slow_or_wobbly_lap_breaks_the_streak_without_counting_as_a_failure():
    g = _gate()
    g.on_episode(_ep()); g.on_episode(_ep())
    assert g.on_episode(_ep(cte=1.4)) == "none"            # limpia no es: rompe la racha
    assert g.on_episode(_ep(speed=50.0)) == "none"         # no sigue el objetivo
    assert g.clean == 0 and g.fails == 0 and g.target_kmh == 60.0


def test_two_failures_roll_back_to_the_proven_speed():
    g = _gate()
    for _ in range(3):
        g.on_episode(_ep())                                # valida 60, sube a 62,5
    assert g.on_episode(_ep("stuck")) == "none"
    assert g.on_episode(_ep("wrong_way")) == "backoff"
    assert g.target_kmh == 60.0 and g.safe_target_kmh == 60.0


def test_lap_done_with_bad_cte_counts_as_a_failure():
    g = _gate()
    g.on_episode(_ep(cte=2.0))
    assert g.on_episode(_ep(cte=2.0)) == "backoff"


def test_udp_timeouts_are_neutral_until_a_streak_then_stop():
    g = _gate(max_udp_streak=3)
    assert [g.on_episode(_ep("udp_timeout")) for _ in range(3)] == ["none", "none", "stop"]
    g2 = _gate(max_udp_streak=3)
    g2.on_episode(_ep("udp_timeout")); g2.on_episode(_ep("udp_timeout"))
    g2.on_episode(_ep())                                   # un episodio normal rompe la racha
    assert g2.on_episode(_ep("udp_timeout")) == "none"


def test_too_many_rollbacks_without_progress_stops_the_run():
    g = _gate(max_backoffs=2)
    out = []
    for _ in range(6):
        out.append(g.on_episode(_ep("stuck")))
    assert out == ["none", "backoff", "none", "backoff", "none", "stop"]


def test_progress_resets_the_rollback_budget():
    g = _gate(max_backoffs=1)
    g.on_episode(_ep("stuck")); assert g.on_episode(_ep("stuck")) == "backoff"
    for _ in range(3):
        g.on_episode(_ep())                                # sube: hay progreso
    assert g.backoffs == 0


def test_ceiling_is_respected_and_still_saves_a_safe_point():
    g = _gate(step_kmh=5.0, max_kmh=60.0)
    actions = [g.on_episode(_ep()) for _ in range(3)]
    assert actions[-1] == "safe" and g.target_kmh == 60.0


def _callback(tmp_path, **gate_kw):
    env = MagicMock()
    model = MagicMock()
    cb = SpeedGateCallback(
        env, str(tmp_path / "safe"), str(tmp_path / "estado.json"), SpeedGate(60.0, **gate_kw),
    )
    cb.model = model
    cb.locals = {}
    (tmp_path / "safe.zip").write_bytes(b"x")      # el modelo seguro ya existe
    return cb, env, model


def _finish(cb, info):
    cb.locals = {"dones": [True], "infos": [info]}
    return cb._on_step()


def test_callback_raise_saves_the_safe_model_and_updates_the_env(tmp_path):
    cb, env, model = _callback(tmp_path, step_kmh=2.5)
    results = [_finish(cb, _ep()) for _ in range(3)]
    assert results == [True, True, True]
    model.save.assert_called_with(str(tmp_path / "safe"))
    env.set_speed_target_kmh.assert_called_with(62.5)
    assert json.loads((tmp_path / "estado.json").read_text())["safe_target_kmh"] == 60.0


def test_callback_backoff_restores_the_safe_weights(tmp_path):
    cb, env, model = _callback(tmp_path)
    _finish(cb, _ep("stuck"))
    _finish(cb, _ep("stuck"))
    model.set_parameters.assert_called_once()
    env.set_speed_target_kmh.assert_called_with(60.0)


def test_callback_stop_brakes_restores_and_ends_training(tmp_path):
    cb, env, model = _callback(tmp_path, max_udp_streak=1)
    assert _finish(cb, _ep("udp_timeout")) is False
    env.hold_brake.assert_called_once()
    model.set_parameters.assert_called_once()


def test_callback_ignores_steps_that_do_not_end_an_episode(tmp_path):
    cb, env, model = _callback(tmp_path)
    cb.locals = {"dones": [False], "infos": [{}]}
    assert cb._on_step() is True
    env.set_speed_target_kmh.assert_not_called()


def test_state_file_restores_the_proven_target_on_resume(tmp_path):
    (tmp_path / "estado.json").write_text(json.dumps({"safe_target_kmh": 67.5}))
    cb, env, model = _callback(tmp_path)
    cb._on_training_start()
    env.set_speed_target_kmh.assert_called_with(67.5)
    model.save.assert_called()                             # punto seguro inicial


def test_state_file_is_ignored_when_the_run_did_not_resume(tmp_path):
    """Un estado de velocidad validada solo vale con los pesos que lo validaron."""
    (tmp_path / "estado.json").write_text(json.dumps({"safe_target_kmh": 72.5}))
    env, model = MagicMock(), MagicMock()
    cb = SpeedGateCallback(env, str(tmp_path / "safe"), str(tmp_path / "estado.json"),
                           SpeedGate(60.0), restore_state=False)
    cb.model = model
    cb._on_training_start()
    env.set_speed_target_kmh.assert_called_with(60.0)


def test_gate_defaults_come_from_one_place():
    import ppo_defaults as d
    import ppo_progress

    g = SpeedGate(60.0)
    assert (g.step_kmh, g.max_kmh) == (d.SPEED_STEP_KMH, d.SPEED_MAX_KMH)
    assert (g.clean_cte_m, g.fail_cte_m) == (d.GATE_CLEAN_CTE_M, d.GATE_FAIL_CTE_M)
    assert ppo_progress.CTE_LIMIT_M == d.GATE_FAIL_CTE_M
