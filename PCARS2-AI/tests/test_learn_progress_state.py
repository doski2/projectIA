"""Tests de LearnProgress / advance_progress / announce_autonomy (extraídos de learn_driver.run)."""

from types import SimpleNamespace

import learn_driver as ld


def test_record_lap_streaks():
    p = ld.LearnProgress(stage_id="s", speed_band=20.0)
    for clean in (True, True, False, True):
        p.record_lap(clean)
    assert p.clean_streak == 1 and p.max_clean_streak == 2


def test_advance_stage_persists_and_resets(monkeypatch, capsys):
    monkeypatch.setattr(ld, "try_advance_stage", lambda s, c: ("s2", True, "sube"))
    monkeypatch.setattr(ld, "try_advance_speed_band", lambda b, s, c: (b, False, s, ""))
    p = ld.LearnProgress(stage_id="s1", speed_band=20.0, clean_streak=3)
    calls = []
    ld.advance_progress(p, lambda: calls.append(1))
    assert (p.stage_id, p.clean_streak, p.goal_reached, len(calls)) == ("s2", 0, True, 1)
    assert "*** sube ***" in capsys.readouterr().out


def test_advance_band(monkeypatch):
    monkeypatch.setattr(ld, "try_advance_stage", lambda s, c: (s, False, "no"))
    monkeypatch.setattr(ld, "try_advance_speed_band", lambda b, s, c: (25.0, True, "L1", "banda"))
    p = ld.LearnProgress(stage_id="s1", speed_band=20.0, clean_streak=2, autonomy_announced=True)
    calls = []
    ld.advance_progress(p, lambda: calls.append(1))
    assert (p.speed_band, p.stage_id, p.clean_streak) == (25.0, "L1", 0)
    assert p.goal_reached and not p.autonomy_announced and len(calls) == 1


def test_band_message_without_advance_marks_goal(monkeypatch):
    monkeypatch.setattr(ld, "try_advance_stage", lambda s, c: (s, False, "no"))
    monkeypatch.setattr(ld, "try_advance_speed_band", lambda b, s, c: (b, False, s, "tope"))
    p = ld.LearnProgress(stage_id="s1", speed_band=20.0)
    ld.advance_progress(p, lambda: None)
    assert p.goal_reached


def test_announce_autonomy_once(monkeypatch, capsys):
    stage = SimpleNamespace(autonomous_ready=True, clean_laps_required=2)
    monkeypatch.setattr(ld, "get_learn_stage", lambda sid: stage)
    p = ld.LearnProgress(stage_id="s", speed_band=20.0, max_clean_streak=1)
    ld.announce_autonomy(p)
    assert not p.autonomy_announced
    p.max_clean_streak = 2
    ld.announce_autonomy(p)
    ld.announce_autonomy(p)
    assert p.autonomy_announced
    assert capsys.readouterr().out.count("autonomía total") == 1
