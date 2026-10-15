"""Tests de mix_drive_action / select_bc_action (extraídos de imitation_driver.run)."""

from types import SimpleNamespace

import imitation_driver as im

BC = (0.8, 0.0, 0.1)
TEACHER = (0.2, 0.3, -0.1)
TELEM = SimpleNamespace(speed=10.0)


def _choose(src, inc=False, ped=BC):
    return lambda *a, **k: (ped, src, inc)


def test_guard_active_uses_teacher(monkeypatch):
    m = im.mix_drive_action("hybrid", 0.5, BC, TEACHER, TELEM, False, True)
    assert (m.action, m.drive_source, m.used_teacher, m.mix_alpha, m.override_inc) == (
        TEACHER, "teacher", True, None, False)


def test_hybrid_blend(monkeypatch):
    monkeypatch.setattr(im, "choose_bc_drive_pedals", _choose("bc"))
    m = im.mix_drive_action("hybrid", 0.5, BC, TEACHER, TELEM, False, False)
    assert m.drive_source == "hybrid" and m.mix_alpha == 0.5 and not m.used_teacher
    assert m.action == im.blend_actions(BC, TEACHER, 0.5)


def test_hybrid_override_counts(monkeypatch):
    monkeypatch.setattr(im, "choose_bc_drive_pedals", _choose("bc"))
    m = im.mix_drive_action("hybrid", 0.5, BC, TEACHER, TELEM, True, False)
    assert m.drive_source == "teacher" and m.used_teacher and m.override_inc
    assert m.mix_alpha == 0.0 and m.action == TEACHER


def test_autonomous_passthrough(monkeypatch):
    monkeypatch.setattr(im, "choose_bc_drive_pedals", _choose("teacher:safety", True, TEACHER))
    m = im.mix_drive_action("autonomous", 0.5, BC, TEACHER, TELEM, True, False)
    assert (m.action, m.drive_source, m.used_teacher, m.override_inc) == (
        TEACHER, "teacher:safety", True, True)


def test_select_bc_action_fallback_to_teacher(monkeypatch):
    monkeypatch.setattr(im, "build_obs", lambda *a: "legacy")
    out = im.select_bc_action(None, None, False, "hybrid", 1, 2, 3, 5.0, "r", TEACHER)
    assert out == ("legacy", TEACHER, "legacy_19", None)


def test_select_bc_action_universal(monkeypatch):
    monkeypatch.setattr(im, "build_obs_universal", lambda *a: "obs")
    monkeypatch.setattr(im, "decode_action", lambda a: BC)
    calls = []

    class M:
        def predict(self, obs, **kw):
            calls.append(kw)
            return "a", 7

    out = im.select_bc_action(M(), None, False, "autonomous", 1, 2, 3, 5.0, "r", TEACHER)
    assert out == ("obs", BC, im.OBS_SCHEMA, 7) and calls == [{"use_predicted_reason": True}]
    im.select_bc_action(M(), None, False, "hybrid", 1, 2, 3, 5.0, "r", TEACHER)
    assert calls[-1] == {"reason": "r"}
