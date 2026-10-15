# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
"""Tests de los predicados de fin de episodio extraídos de PCARS2Env._check_done."""

from types import SimpleNamespace

from environment import PCARS2Env


def _env(**kw):
    env = object.__new__(PCARS2Env)
    env._ref = SimpleNamespace(track_length=5000.0, heading_at=lambda d: 0.0)
    env._step_count = 1000
    env._stuck_speed_ms = 0.5
    env._stuck_max_steps = 3
    env._stuck_steps = 0
    env._no_progress_max_steps = 5
    env._progress_dist = 0.0
    env._progress_step = 0
    env._prev_check_lap = 1
    env._wrongway_steps = 0
    env._wrongway_max_steps = 2
    env._wrongway_finish_steps = 1
    for k, v in kw.items():
        setattr(env, k, v)
    return env


def test_pit_box_only_near_finish():
    env = _env()
    assert env._check_pit_box(25.0, SimpleNamespace(lap_distance=50.0)) == "pit_box"
    assert env._check_pit_box(25.0, SimpleNamespace(lap_distance=2500.0)) is None
    assert env._check_pit_box(5.0, SimpleNamespace(lap_distance=50.0)) is None


def test_stuck_counts_and_resets():
    env = _env()
    slow, fast = SimpleNamespace(speed=0.0), SimpleNamespace(speed=10.0)
    assert env._check_stuck(slow) is None
    assert env._check_stuck(slow) is None
    assert env._check_stuck(fast) is None and env._stuck_steps == 0
    for _ in range(2):
        assert env._check_stuck(slow) is None
    assert env._check_stuck(slow) == "stuck"


def test_no_progress_timer_and_new_lap_reset():
    env = _env()
    assert env._check_no_progress(SimpleNamespace(lap_distance=0.0, current_lap=1)) == "no_progress"
    env = _env()
    assert env._check_no_progress(SimpleNamespace(lap_distance=0.0, current_lap=2)) is None
    assert env._prev_check_lap == 2 and env._progress_step == 1000
    assert env._check_no_progress(SimpleNamespace(lap_distance=50.0, current_lap=2)) is None
    assert env._progress_dist == 50.0


def test_wrong_way():
    env = _env()
    t = SimpleNamespace(speed=10.0, orientation=(0.0, 0.0, 3.14))
    i = SimpleNamespace(lap_distance=2500.0)
    assert env._check_wrong_way(t, i) is None
    assert env._check_wrong_way(t, i) == "wrong_way"
    # cerca de meta: tolerancia mínima (1 step)
    env = _env()
    assert env._check_wrong_way(t, SimpleNamespace(lap_distance=10.0)) == "wrong_way"
    # recto: resetea el contador; lento: lo conserva sin disparar
    env._wrongway_steps = 1
    assert env._check_wrong_way(SimpleNamespace(speed=10.0, orientation=(0, 0, 0.0)), i) is None
    assert env._wrongway_steps == 0
