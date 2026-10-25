# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
"""Registro por episodio (episodios.csv), tiempo de vuelta y ajustes de actualización de PPO."""

import csv
from types import SimpleNamespace
from unittest.mock import MagicMock

from stable_baselines3 import PPO

import main as m
from environment import PCARS2Env
from episode_log import EpisodeLogger


def _info(reason="lap_done", **kw):
    base = {
        "term_reason": reason, "step": 12000, "lap_distance": 3560.0, "cte": 0.8,
        "speed_kmh": 58.0, "gear": 3, "speed_target_kmh": 60.0, "lap_time_s": 231.4, "episode": {"r": -1850.0, "l": 12000},
    }
    base.update(kw)
    return base


def test_logger_writes_header_once_and_one_row_per_episode(tmp_path):
    path = tmp_path / "episodios.csv"
    log = EpisodeLogger(str(path))
    log.add(_info(), 20480)
    log.add(_info("stuck", lap_distance=1200.0, lap_time_s=None), 22528)
    log.close()
    log2 = EpisodeLogger(str(path))          # nueva ejecución: añade, no repite cabecera
    log2.add(_info(), 30720)
    log2.close()
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    assert [r["fin"] for r in rows] == ["lap_done", "stuck", "lap_done"]
    assert rows[1]["lap_distance_m"] == "1200.0" and rows[1]["lap_time_s"] == ""
    assert rows[0]["lap_time_s"] == "231.4" and rows[0]["total_timesteps"] == "20480"
    assert rows[0]["ep_reward"] == "-1850.0" and rows[0]["pasos"] == "12000"
    assert rows[0]["marcha"] == "3" and rows[0]["objetivo_kmh"] == "60.0"


def _env_cerca_de_meta(prev_time):
    env = object.__new__(PCARS2Env)
    env._last_telem = SimpleNamespace(position=(0, 0, 0), speed=15.0, gear=1)
    env._last_timings = SimpleNamespace(
        lap_distance=5.0, current_lap=3, current_time=0.4, sector=1)
    env._ref = SimpleNamespace(
        cross_track_error=lambda p, d: 0.5, track_length=3500.0, speed_delta=lambda s, d: 0.0)
    env._max_cte_seen = 0.0
    env._step_count = 10          # dentro del periodo de gracia: no comprueba atascos
    env._start_lap = 2
    env._term_reason = "?"
    env._prev_current_time = prev_time
    env._lap_time_s = None
    env._speed_target_ms = 60.0 / 3.6
    return env


def test_lap_time_is_the_last_time_before_the_game_resets_it():
    env = _env_cerca_de_meta(prev_time=231.4)
    assert env._check_done() == (False, True)
    assert env._term_reason == "lap_done" and env._lap_time_s == 231.4
    info = env._build_info(0.3, 0.0, 0.0, 0.0)
    assert info["lap_time_s"] == 231.4


def test_lap_time_absent_when_the_episode_ends_otherwise():
    env = _env_cerca_de_meta(prev_time=100.0)
    env._term_reason = "stuck"
    assert env._build_info(0.3, 0.0, 0.0, 0.0)["lap_time_s"] is None


def _ppo():
    return PPO("MlpPolicy", "Pendulum-v1", n_steps=32, batch_size=32, n_epochs=10,
               policy_kwargs=dict(net_arch=[16]), device="cpu", seed=0)


def test_gentle_update_settings_reach_the_optimizer():
    model = _ppo()
    args = SimpleNamespace(bc_std=0.1, anchor_lr=3e-5, anchor_epochs=4, anchor_target_kl=0.02)
    m._apply_update_settings(model, args)
    assert model.n_epochs == 4 and model.target_kl == 0.02
    model.learn(total_timesteps=64)
    assert model.policy.optimizer.param_groups[0]["lr"] == 3e-5


def test_anchor_from_bc_applies_them_only_there():
    model = MagicMock()
    model.policy.log_std = None
    args = SimpleNamespace(bc_std=0.1, anchor_lr=3e-5, anchor_epochs=4, anchor_target_kl=0.02)
    m._anchor_from_bc(model, args)
    assert args.anchored_to_bc is True and model.n_epochs == 4


def test_logger_rotates_a_file_with_an_old_header(tmp_path):
    path = tmp_path / "episodios.csv"
    path.write_text("timestamp,total_timesteps,fin\n15:00:00,10,stuck\n", encoding="utf-8")
    log = EpisodeLogger(str(path))
    log.add(_info(), 100)
    log.close()
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    assert len(rows) == 1 and "marcha" in rows[0]
    old = [p for p in tmp_path.iterdir() if p.name.startswith("episodios.csv.old")]
    assert len(old) == 1 and "15:00:00,10,stuck" in old[0].read_text(encoding="utf-8")


def test_sync_tolerance_is_about_three_seconds():
    import environment
    assert environment.MAX_SYNC_FAILURES * 0.1 >= 3.0
