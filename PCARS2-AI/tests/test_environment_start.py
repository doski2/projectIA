# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
"""Rampa de velocidad objetivo, datos extra por episodio y comprobación de arranque en pista."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import environment
from environment import PCARS2Env, SPEED_TARGET_WINDOW


def _env(**kw):
    env = object.__new__(PCARS2Env)
    env._speed_target_ms = 60.0 / 3.6
    env._spd_win_steps = SPEED_TARGET_WINDOW - 1
    env._spd_win_sum = (SPEED_TARGET_WINDOW - 1) * 59.0 / 3.6
    env._speed_ramp = True
    for k, v in kw.items():
        setattr(env, k, v)
    return env


def test_speed_target_ramps_up_by_default(capsys):
    env = _env()
    env._speed_target_reward(59.0 / 3.6)
    assert round(env._speed_target_ms * 3.6) == 65


def test_speed_target_stays_fixed_without_ramp(capsys):
    env = _env(_speed_ramp=False)
    env._speed_target_reward(59.0 / 3.6)
    assert round(env._speed_target_ms * 3.6) == 60
    assert env._spd_win_steps == 0            # la ventana sigue rodando sin subir el objetivo


def test_info_carries_gear_and_speed_target():
    env = object.__new__(PCARS2Env)
    env._last_telem = SimpleNamespace(position=(0, 0, 0), speed=10.0, gear=0)
    env._last_timings = SimpleNamespace(lap_distance=100.0, current_lap=1, sector=1)
    env._ref = SimpleNamespace(cross_track_error=lambda p, d: 0.5, speed_delta=lambda s, d: 0.0)
    env._step_count, env._term_reason, env._lap_time_s = 5, "stuck", None
    env._speed_target_ms = 70.0 / 3.6
    info = env._build_info(0.3, 0.0, 0.0, 0.0)
    assert info["gear"] == 0 and info["speed_target_kmh"] == 70.0


def _env_arranque(ctes):
    env = object.__new__(PCARS2Env)
    env._controller = MagicMock()
    env._last_telem = SimpleNamespace(position=(0, 0, 0), speed=0.0)
    env._last_timings = SimpleNamespace(lap_distance=0.0)
    env._ref = SimpleNamespace(cross_track_error=MagicMock(side_effect=list(ctes)))

    def reponer_telemetria():
        env._last_telem = SimpleNamespace(position=(0, 0, 0), speed=0.0)
        env._last_timings = SimpleNamespace(lap_distance=500.0)

    env._wait_for_telemetry = MagicMock(side_effect=reponer_telemetria)
    return env


def test_start_on_track_does_not_reposition(monkeypatch):
    monkeypatch.setattr(environment.time, "sleep", lambda s: None)
    env = _env_arranque([0.4])
    assert env._ensure_on_track() is True
    env._controller.press_button.assert_not_called()


def test_start_in_the_pit_repositions_again_until_on_track(monkeypatch, capsys):
    monkeypatch.setattr(environment.time, "sleep", lambda s: None)
    env = _env_arranque([11.7, 0.5])
    env._last_timings = SimpleNamespace(lap_distance=500.0)
    assert env._ensure_on_track() is True
    assert env._controller.press_button.call_count == 1
    assert env._wait_for_telemetry.call_count == 1


def test_start_gives_up_after_the_retries(monkeypatch, capsys):
    monkeypatch.setattr(environment.time, "sleep", lambda s: None)
    env = _env_arranque([11.7] * 10)
    env._last_timings = SimpleNamespace(lap_distance=500.0)
    assert env._ensure_on_track() is False
    assert env._controller.press_button.call_count == environment.START_REPOSITION_RETRIES
    assert "fuera de la pista" in capsys.readouterr().out


def test_reset_engages_first_gear_before_warmup(monkeypatch):
    """El coche sale de Back en punto muerto: hay que meter la 1ª antes del calentamiento."""
    calls = []
    env = object.__new__(PCARS2Env)
    env._controller = MagicMock()
    env._shifter = object()
    env._last_telem = SimpleNamespace(gear=0)
    env._sync_physics_frame = MagicMock(return_value=True)
    monkeypatch.setattr(
        environment, "engage_first_gear",
        lambda ctrl, sh, get_telem, sync: calls.append((ctrl, sh, get_telem(), sync)) or True,
    )
    assert env._engage_first() is True
    ctrl, sh, telem, sync = calls[0]
    assert ctrl is env._controller and sh is env._shifter and telem.gear == 0
    assert sync == env._sync_physics_frame


def test_no_engage_when_already_in_first(monkeypatch):
    env = object.__new__(PCARS2Env)
    env._last_telem = SimpleNamespace(gear=1)
    monkeypatch.setattr(environment, "engage_first_gear", lambda *a: (_ for _ in ()).throw(AssertionError))
    assert env._engage_first() is True


def test_grid_start_behind_the_line_is_not_repositioned(monkeypatch):
    """En la parrilla (lap_distance ~0) el CTE es distancia hasta la línea, no estar fuera de pista."""
    monkeypatch.setattr(environment.time, "sleep", lambda s: None)
    env = _env_arranque([11.7])
    env._last_timings = SimpleNamespace(lap_distance=0.0)
    assert env._ensure_on_track() is True
    env._controller.press_button.assert_not_called()


def _env_rodando(speeds):
    env = object.__new__(PCARS2Env)
    env._controller = MagicMock()
    env._last_telem = SimpleNamespace(speed=speeds[0])
    it = iter(speeds[1:])

    def sync():
        env._last_telem = SimpleNamespace(speed=next(it))
        return True

    env._sync_physics_frame = MagicMock(side_effect=sync)
    return env


def test_reposition_brakes_to_a_stop_before_pressing_back(monkeypatch):
    """Back no funciona con el coche rodando: hay que parar primero."""
    monkeypatch.setattr(environment.time, "sleep", lambda s: None)
    env = _env_rodando([17.0, 12.0, 6.0, 2.0, 0.3])
    order = []
    env._controller.apply_action.side_effect = lambda *a: order.append(("accion", a))
    env._controller.press_button.side_effect = lambda b: order.append(("boton", b))
    env._reposition_car()
    assert order[0] == ("accion", (0.0, 1.0, 0.0))
    assert order[-1] == ("boton", "back")
    assert env._sync_physics_frame.call_count == 4


def test_reposition_does_not_brake_when_already_stopped(monkeypatch):
    monkeypatch.setattr(environment.time, "sleep", lambda s: None)
    env = _env_rodando([0.2])
    env._reposition_car()
    env._sync_physics_frame.assert_not_called()
    env._controller.press_button.assert_called_once_with("back")


def test_brake_to_stop_gives_up_after_the_timeout(monkeypatch, capsys):
    monkeypatch.setattr(environment.time, "sleep", lambda s: None)
    monkeypatch.setattr(environment, "STOP_BEFORE_BACK_TIMEOUT_S", 0.0)
    env = _env_rodando([17.0, 17.0, 17.0])
    assert env._brake_to_stop() is False
    assert "No consigo parar" in capsys.readouterr().out


def _env_tras_actualizacion(speed, gear):
    env = object.__new__(PCARS2Env)
    env._controller = MagicMock()
    env._shifter = object()
    env._last_telem = SimpleNamespace(speed=speed, gear=gear)
    env._sync_physics_frame = MagicMock(return_value=True)
    return env


def test_resume_after_update_engages_first_when_the_car_is_stopped(monkeypatch):
    """El freno de la pausa de PPO deja el coche parado en mitad de la pista, a veces en punto muerto."""
    calls = []
    monkeypatch.setattr(environment, "engage_first_gear", lambda *a: calls.append(a) or True)
    env = _env_tras_actualizacion(speed=0.2, gear=0)
    env.resume_after_update()
    assert env._sync_physics_frame.called and len(calls) == 1


def test_resume_after_update_leaves_a_moving_or_in_gear_car_alone(monkeypatch):
    monkeypatch.setattr(environment, "engage_first_gear", lambda *a: (_ for _ in ()).throw(AssertionError))
    _env_tras_actualizacion(speed=15.0, gear=3).resume_after_update()
    _env_tras_actualizacion(speed=0.0, gear=1).resume_after_update()      # parado pero en 1ª: arranca solo
