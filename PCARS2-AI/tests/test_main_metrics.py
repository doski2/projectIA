"""Tests de MetricsAccumulator y _load_or_create_model (extraídos de main.train)."""

from types import SimpleNamespace

import numpy as np

import main as m


def _obs(speed_norm=0.0, prog=0.0):
    o = np.zeros((1, 19))
    o[0][0], o[0][18] = speed_norm, prog
    return o


def test_accumulator_empty_is_zeros():
    acc = m.MetricsAccumulator()
    assert acc.csv_values() == [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_accumulator_speed_actions_cte():
    acc = m.MetricsAccumulator(track_length=1000.0)
    acc.add_step(_obs(0.5), [[1.0, 0.0, -0.5]], [{"cte": 2.0}], [False])
    acc.add_step(_obs(1.0), [[0.0, 1.0, 0.5]], [{"cte": 4.0}], [False])
    v = acc.csv_values()
    assert v[0] == round((0.5 + 1.0) * 97.0 * 3.6 / 2, 1)
    assert v[1] == round(97.0 * 3.6, 1)
    assert v[2] == 3.0 and v[3:6] == [0.0, 0.5, 0.5]


def test_accumulator_terminations_and_percentages():
    acc = m.MetricsAccumulator()
    for tr in ("stuck", "lap_done", "lap_done", "TimeLimit.truncated"):
        acc.add_step(None, None, [{"term_reason": tr}], [True])
    v = acc.csv_values()
    assert v[7] == 4
    assert v[8:] == [25.0, 0.0, 0.0, 0.0, 50.0, 25.0]  # stuck, pit, wrong, noprog, lap, timelimit


def test_accumulator_distance_wraparound_and_reset():
    acc = m.MetricsAccumulator(track_length=1000.0)
    for p in (0.9, 0.1):  # 0.9 desde 0 = +900 m ; 0.9→0.1 = wrap +200 m
        acc.add_step(_obs(prog=p), None, None, None)
    assert acc.csv_values()[6] == 1.1
    acc.reset()
    assert acc.csv_values()[6] == 0.0


class _FakePPO:
    loaded = []

    @classmethod
    def load(cls, path, **kw):
        cls.loaded.append((path, kw["custom_objects"] if "custom_objects" in kw else None))
        return SimpleNamespace(path=path, ent_coef=None, vf_coef=None)


def _args(**kw):
    base = dict(model=None, base_model=None, fresh=False, model_dir="models")
    base.update(kw)
    return SimpleNamespace(**base)


def test_model_arg_continues_and_keeps_timesteps(monkeypatch):
    _FakePPO.loaded.clear()
    monkeypatch.setattr(m, "_reset_log_std", lambda *a, **k: None)
    model, reset = m._load_or_create_model(_args(model="x.zip"), _FakePPO, None, None, "d", "p", "s")
    assert reset is False and model.ent_coef == 0.007 and model.vf_coef == 1.0


def test_base_model_transfers(monkeypatch):
    model, reset = m._load_or_create_model(_args(base_model="b.zip"), _FakePPO, None, None, "d", "p", "s")
    assert reset is True and model.ent_coef == 0.01


def test_fresh_creates_from_scratch(monkeypatch):
    monkeypatch.setattr(m, "_create_ppo_from_scratch", lambda env, tb: "new")
    assert m._load_or_create_model(_args(fresh=True), _FakePPO, None, None, "d", "p", "s") == ("new", True)


def test_auto_without_checkpoints_falls_back_to_scratch(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "_find_best_model", lambda *a, **k: None)
    monkeypatch.setattr(m, "_create_ppo_from_scratch", lambda env, tb: "new")
    out = m._load_or_create_model(_args(model_dir=str(tmp_path)), _FakePPO, None, None, "d", "p", "s")
    assert out == ("new", True)
