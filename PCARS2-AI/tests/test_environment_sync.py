# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
"""Sincronización de frames y cadencia de terminación del entorno (auditoría 7.1.1-7.1.3)."""

import numpy as np
import pytest
from unittest.mock import MagicMock

import environment
import safety_monitor
from environment import PCARS2Env, termination_frame_count
from test_udp_sync import _frame


def test_physics_key_distinguishes_stopped_car_frames():
    """7.1.1: un coche casi parado sigue produciendo claves distintas."""
    keys = {
        PCARS2Env._physics_key(_frame(0.0, 10.0 + i * 0.001, 5.0, 3.0))
        for i in range(60)
    }
    assert len(keys) == 60


def test_physics_key_distinguishes_slow_car_frames():
    """7.1.1: a 1 m/s y 60 Hz cada frame (≈0,017 m) es un frame nuevo."""
    keys = {
        PCARS2Env._physics_key(_frame(1.0, 10.0 + i * (1.0 / 60), 5.0, 3.0))
        for i in range(120)
    }
    assert len(keys) == 120


def test_game_fps_is_60_and_shared():
    """7.1.3: el juego emite a 60 Hz y la constante tiene una única fuente."""
    assert safety_monitor.GAME_FPS == 60.0
    assert environment.GAME_FPS == safety_monitor.GAME_FPS
    assert termination_frame_count(environment.STUCK_TIME_S) == 480


def _env_sin_udp():
    env = object.__new__(PCARS2Env)
    env._frame_skip = 1
    env._controller = MagicMock()
    env._last_telem = None
    env._sync_physics_frame = MagicMock(return_value=False)
    env._build_obs = MagicMock(return_value=np.zeros(19, dtype=np.float32))
    env._build_info = MagicMock(return_value={})
    env._prev_steering = 0.0
    env._term_reason = "?"
    env._sync_fail_steps = 0
    return env


def test_step_truncates_when_udp_keeps_timing_out():
    """7.1.2: sin frames nuevos de forma sostenida el episodio termina, no se cuelga."""
    env = _env_sin_udp()
    results = [env.step(np.zeros(3, dtype=np.float32)) for _ in range(environment.MAX_SYNC_FAILURES)]
    assert not any(r[3] for r in results[:-1])
    assert results[-1][3] is True
    assert results[-1][4]["term_reason"] == "udp_timeout"


def test_step_resets_sync_failure_counter_on_good_frame():
    env = _env_sin_udp()
    env.step(np.zeros(3, dtype=np.float32))
    assert env._sync_fail_steps == 1
    env._sync_physics_frame.return_value = True
    env._step_count = 0
    env._ep_reward = 0.0
    env._last_timings = None
    env._compute_reward = MagicMock(return_value=0.0)
    env._check_done = MagicMock(return_value=(False, False))
    env.step(np.zeros(3, dtype=np.float32))
    assert env._sync_fail_steps == 0


def test_shared_termination_constants_single_source():
    """7.2.2: las constantes comunes viven en safety_monitor y environment las reutiliza."""
    for name in ("GRACE_STEPS", "NO_PROGRESS_DIST_M", "PIT_ZONE_MARGIN_M", "WRONGWAY_ANGLE_RAD",
                 "WRONGWAY_TIME_S", "WRONGWAY_NEAR_FINISH_S"):
        assert getattr(environment, name) == getattr(safety_monitor, name)


def test_observation_space_per_schema():
    """7.1.4: el entorno puede observar con `universal_v1` (17 dim, CTE con signo)."""
    assert environment.observation_space_for("legacy_19").shape == (19,)
    assert environment.observation_space_for("universal_v1").shape == (17,)
    with pytest.raises(ValueError):
        environment.observation_space_for("otro")


def test_universal_obs_has_signed_cte():
    from types import SimpleNamespace
    from obs_universal import OBS_UNIVERSAL_DIM

    ref = MagicMock()
    ref.lookup.return_value = SimpleNamespace(position=(0.0, 0.0, 0.0))
    ref.heading_vector.return_value = (0.0, 1.0)   # rumbo +z → derecha = +x
    ref.heading_error.return_value = 0.0
    ref.curvature.return_value = 0.0
    ref.speed_lookahead.return_value = 0.0
    timings = SimpleNamespace(lap_distance=100.0)

    def obs_en(x):
        env = object.__new__(PCARS2Env)
        env._obs_schema = "universal_v1"
        env._last_telem = _frame(10.0, x, 0.0, 0.0)
        env._last_timings = timings
        env._ref = ref
        env._speed_target_ms = 5.0
        return env._build_obs()

    der, izq = obs_en(2.0), obs_en(-2.0)
    assert der.shape == (OBS_UNIVERSAL_DIM,)
    assert der[1] > 0 > izq[1]
