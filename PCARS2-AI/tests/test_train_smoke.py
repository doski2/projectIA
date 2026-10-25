# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
"""Humo del flujo completo de main.train con un entorno falso: todas las piezas de PPO juntas."""

import csv
import json
import sys
from types import SimpleNamespace

import gymnasium as gym
import numpy as np
import pytest
from stable_baselines3 import PPO

import environment
import main as m
from obs_spaces import DummyEnv
from obs_universal import OBS_SCHEMA, OBS_UNIVERSAL_DIM


class FakeCar(gym.Env):
    """Un 'coche' que cada EP_LEN pasos completa un episodio limpio (o un stuck si se le pide)."""

    EP_LEN = 40
    outcomes: list = []            # fin de cada episodio, en orden; si se agota: lap_done limpio
    instances: list = []

    def __init__(self, **kw):
        self.observation_space = gym.spaces.Box(-1, 1, shape=(OBS_UNIVERSAL_DIM,), dtype=np.float32)
        self.action_space = gym.spaces.Box(-1, 1, shape=(3,), dtype=np.float32)
        self._ref = SimpleNamespace(track_length=3500.0)
        self._t = 0
        self._ep = 0
        self.target_kmh = kw.get("speed_target_kmh", 0.0)
        self.kw = kw
        self.calls = []
        FakeCar.instances.append(self)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._t = 0
        self.calls.append("reset")
        return np.zeros(OBS_UNIVERSAL_DIM, dtype=np.float32), {}

    def step(self, action):
        self._t += 1
        done = self._t >= self.EP_LEN
        fin = "?"
        info = {"cte": 0.8, "speed_kmh": self.target_kmh, "lap_distance": 100.0, "step": self._t}
        if done:
            fin = FakeCar.outcomes[self._ep] if self._ep < len(FakeCar.outcomes) else "lap_done"
            self._ep += 1
            info.update(ep_cte_mean=0.8, ep_speed_kmh=self.target_kmh, gear=1,
                        speed_target_kmh=self.target_kmh,
                        lap_time_s=210.0 if fin == "lap_done" else None)
        info["term_reason"] = fin
        return np.zeros(OBS_UNIVERSAL_DIM, dtype=np.float32), -0.1, False, done, info

    def hold_brake(self):
        self.calls.append("freno")

    def resume_after_update(self):
        self.calls.append("reanudar")

    def set_speed_target_kmh(self, kmh):
        self.target_kmh = kmh
        self.calls.append(f"objetivo={kmh}")

    def wait_for_combo(self, timeout=0):
        return None

    def close(self):
        self.calls.append("close")


@pytest.fixture
def run(tmp_path, monkeypatch):
    FakeCar.outcomes, FakeCar.instances = [], []
    monkeypatch.setattr(environment, "PCARS2Env", FakeCar)
    monkeypatch.setattr(m._time, "sleep", lambda s: None)
    base = tmp_path / "base"
    PPO("MlpPolicy", DummyEnv(OBS_SCHEMA), device="cpu").save(str(base))
    ref = tmp_path / "ref.json"
    ref.write_text("{}")

    def go(*extra, steps=4096):
        argv = ["main.py", "--reference", str(ref), "--car", "c", "--track", "t",
                "--model-dir", str(tmp_path / "models"), "--log-dir", str(tmp_path / "logs"),
                "--obs-schema", "universal_v1", "--base-model", str(base) + ".zip",
                "--timesteps", str(steps), "--speed-target-kmh", "60", "--critic-warmup-steps", "0",
                *extra]
        monkeypatch.setattr(sys, "argv", argv)
        m.train(m.parse_args())
        return FakeCar.instances[-1], tmp_path / "models" / "c__t", tmp_path / "logs" / "c__t"

    return go


def test_full_flow_writes_every_artifact_and_brakes_around_updates(run):
    car, models, logs = run("--resume-ppo", "--speed-gate")
    assert (models / "pcars2_c__t_final.zip").is_file() and (models / "vecnormalize.pkl").is_file()
    assert (models / "pcars2_c__t_safe.zip").is_file() and (models / "estado_gate.json").is_file()
    assert len(list(csv.DictReader(open(logs / "metricas.csv", encoding="utf-8")))) >= 1
    assert len(list(csv.DictReader(open(logs / "episodios.csv", encoding="utf-8")))) >= 10
    assert "Sesión" in (logs / "consola.log").read_text(encoding="utf-8")
    # cada actualización: freno al terminar el rollout y reanudar al empezar el siguiente
    assert car.calls.count("freno") >= 2 and car.calls.count("reanudar") >= 2
    assert car.calls[-1] == "close" and "freno" in car.calls[-3:]    # frena antes de soltar el mando


def test_gate_raises_the_target_after_clean_episodes_and_remembers_it(run):
    car, models, _ = run("--speed-gate", "--speed-step-kmh", "2.5")
    assert any(c.startswith("objetivo=62.5") for c in car.calls)
    state = json.loads((models / "estado_gate.json").read_text())
    assert state["safe_target_kmh"] >= 60.0


def test_gate_stops_the_run_and_restores_the_safe_model_after_repeated_failures(run):
    FakeCar.outcomes = ["stuck"] * 40
    car, models, _ = run("--speed-gate", steps=20000)
    assert any("freno" == c for c in car.calls)
    final = models / "pcars2_c__t_final.zip"
    assert final.is_file()
    # terminó mucho antes de los 20 000 pasos pedidos
    assert car._ep < 40


def test_second_run_resumes_from_the_previous_one(run, capsys):
    run("--resume-ppo", "--speed-gate")
    capsys.readouterr()
    car, _, _ = run("--resume-ppo", "--speed-gate")
    text = capsys.readouterr().out
    assert "Continuando PPO desde la tirada anterior" in text
    assert "Retomo desde la última velocidad validada" in text
