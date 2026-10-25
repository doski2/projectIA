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


def test_accumulator_works_with_the_17_dim_universal_obs():
    """universal_v1 no trae el progreso en obs[18]: la distancia sale de info['lap_distance']."""
    acc = m.MetricsAccumulator(track_length=1000.0)
    for d in (900.0, 100.0):  # 0 -> 900 m ; 900 -> 100 = wrap +200 m
        acc.add_step(np.zeros((1, 17)), [[0.0, 0.0, 0.0]], [{"lap_distance": d, "cte": 1.0}], [False])
    v = acc.csv_values()
    assert v[6] == 1.1 and v[2] == 1.0


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
    base = dict(model=None, base_model=None, fresh=False, model_dir="models", bc_std=0.1,
                anchor_lr=3e-5, anchor_epochs=4, anchor_target_kl=0.02)
    base.update(kw)
    return SimpleNamespace(**base)


def test_model_arg_continues_and_keeps_timesteps(monkeypatch):
    _FakePPO.loaded.clear()
    monkeypatch.setattr(m, "_reset_log_std", lambda *a, **k: None)
    model, reset = m._load_or_create_model(_args(model="x.zip"), _FakePPO, None, None, "d", "p", "s")
    assert reset is False and model.ent_coef == 0.007 and model.vf_coef == 1.0


def test_base_model_transfers_and_anchors_to_bc(monkeypatch):
    import ppo_anchor

    anchored = []
    monkeypatch.setattr(ppo_anchor, "anchor_log_std", lambda mod, std: anchored.append(std) or True)
    args = _args(base_model="b.zip")
    model, reset = m._load_or_create_model(args, _FakePPO, None, None, "d", "p", "s")
    assert reset is True and model.ent_coef == 0.01
    assert anchored == [0.1] and args.anchored_to_bc is True


def test_continue_does_not_anchor(monkeypatch):
    monkeypatch.setattr(m, "_reset_log_std", lambda *a, **k: None)
    args = _args(model="x.zip")
    m._load_or_create_model(args, _FakePPO, None, None, "d", "p", "s")
    assert not getattr(args, "anchored_to_bc", False)


def test_fresh_creates_from_scratch(monkeypatch):
    monkeypatch.setattr(m, "_create_ppo_from_scratch", lambda env, tb: "new")
    assert m._load_or_create_model(_args(fresh=True), _FakePPO, None, None, "d", "p", "s") == ("new", True)


def test_auto_without_checkpoints_falls_back_to_scratch(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "_find_best_model", lambda *a, **k: None)
    monkeypatch.setattr(m, "_create_ppo_from_scratch", lambda env, tb: "new")
    out = m._load_or_create_model(_args(model_dir=str(tmp_path)), _FakePPO, None, None, "d", "p", "s")
    assert out == ("new", True)


def test_resume_ppo_continues_the_previous_final_without_re_anchoring(monkeypatch, tmp_path):
    import ppo_anchor

    monkeypatch.setattr(ppo_anchor, "anchor_log_std", lambda *a: (_ for _ in ()).throw(AssertionError))
    final = tmp_path / "pcars2_s_final.zip"
    final.write_bytes(b"x")
    _FakePPO.loaded.clear()
    args = _args(base_model="b.zip", resume_ppo=True)
    model, reset = m._load_or_create_model(args, _FakePPO, None, None, str(tmp_path), "pcars2_s", "s")
    assert _FakePPO.loaded[0][0] == str(final) and reset is False
    assert args.resumed_ppo is True and not getattr(args, "anchored_to_bc", False)
    assert model.n_epochs == 4 and model.target_kl == 0.02


def test_resume_ppo_falls_back_to_the_base_model_when_there_is_no_final(monkeypatch, tmp_path):
    import ppo_anchor

    monkeypatch.setattr(ppo_anchor, "anchor_log_std", lambda mod, std: True)
    args = _args(base_model="b.zip", resume_ppo=True)
    model, reset = m._load_or_create_model(args, _FakePPO, None, None, str(tmp_path), "pcars2_s", "s")
    assert reset is True and args.anchored_to_bc is True
    assert not getattr(args, "resumed_ppo", False)


def test_gate_resume_prefers_the_validated_safe_model(tmp_path):
    """Con puerta de velocidad, se retoma el modelo que validó la velocidad guardada, no un _final sin validar."""
    (tmp_path / "pcars2_s_final.zip").write_bytes(b"f")
    (tmp_path / "pcars2_s_safe.zip").write_bytes(b"s")
    (tmp_path / "estado_gate.json").write_text('{"safe_target_kmh": 65.0}')
    _FakePPO.loaded.clear()
    args = _args(base_model="b.zip", resume_ppo=True, speed_gate=True)
    m._load_or_create_model(args, _FakePPO, None, None, str(tmp_path), "pcars2_s", "s")
    assert _FakePPO.loaded[0][0] == str(tmp_path / "pcars2_s_safe.zip")


def test_gate_resume_uses_final_when_there_is_no_validated_state(tmp_path):
    (tmp_path / "pcars2_s_final.zip").write_bytes(b"f")
    (tmp_path / "pcars2_s_safe.zip").write_bytes(b"s")        # sin estado: el seguro no está validado
    _FakePPO.loaded.clear()
    args = _args(base_model="b.zip", resume_ppo=True, speed_gate=True)
    m._load_or_create_model(args, _FakePPO, None, None, str(tmp_path), "pcars2_s", "s")
    assert _FakePPO.loaded[0][0] == str(tmp_path / "pcars2_s_final.zip")


def test_stop_car_safely_brakes_and_waits_for_it_to_stop(monkeypatch):
    waits = []
    monkeypatch.setattr(m._time, "sleep", lambda s: waits.append(s))
    env = SimpleNamespace(braked=0)
    env.hold_brake = lambda: setattr(env, "braked", env.braked + 1)
    m._stop_car_safely(env)
    assert env.braked == 1 and waits == [m.STOP_CAR_WAIT_S]


def test_stop_car_safely_never_raises(monkeypatch):
    monkeypatch.setattr(m._time, "sleep", lambda s: None)
    env = SimpleNamespace(hold_brake=lambda: (_ for _ in ()).throw(OSError("mando desconectado")))
    m._stop_car_safely(env)       # no debe impedir guardar el modelo
