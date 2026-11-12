"""Tests de `experimental/common/repetir_ajuste.py` (repetir un log por el ajuste unificado)."""

from __future__ import annotations

import json
from pathlib import Path

from experimental.common import repetir_ajuste as ra

CURVAS = {"pista": "x", "curvas": [{"id": 1, "s_ini": 200.0, "s_apice": 250.0, "s_fin": 300.0}, {"id": 2, "s_ini": 800.0, "s_apice": 850.0, "s_fin": 900.0}]}


def _tick(lap: int, s: float, reason: str = "accel_straight", terrain=(0, 0, 0, 0)) -> dict:
    return {"type": "tick", "lap": lap, "lap_distance": s, "signed_cte": 0.3, "teacher_reason": reason, "throttle": 0.1, "brake": 0.0, "gear": 3,
            "steering": 0.0, "speed_kmh": 108.0,
            "vehicle": {"local_velocity": [0.0, 0.0, -30.0], "terrain": list(terrain), "tyre_temp": [50, 50, 50, 50], "game_throttle": 0.1, "game_brake": 0.0,
                        "tyre_rps": [80.0, 80.0, -75.36, -75.36], "clutch": 0}}


def test_phase_comes_from_the_teacher_reason_in_old_logs():
    assert ra._phase({"teacher_reason": "brake_overspeed"}) == "entry"
    assert ra._phase({"teacher_reason": "lift_lock"}) == "entry"
    assert ra._phase({"teacher_reason": "accel_exit"}) == "exit"
    assert ra._phase({"teacher_reason": "maintain_speed"}) == "drive"
    assert ra._phase({"teacher_reason": "accel_exit", "phase_teacher": "entry"}) == "entry"  # log_schema 5


def test_replay_starts_from_the_applied_map_and_reports_the_old_decisions(tmp_path: Path):
    curvas = tmp_path / "curvas.json"
    curvas.write_text(json.dumps(CURVAS), encoding="utf-8")
    log = tmp_path / "log.jsonl"
    rows = [{"type": "session"}, {"type": "lat_adapt_start", "applied": True, "scales": {"1": 1.2, "2": 1.0}}]
    for lap in (1, 2, 3):
        for s in range(0, 3500, 2):
            rows.append(_tick(lap, float(s), terrain=(7, 0, 7, 0) if lap == 2 and 210 <= s <= 240 else (0, 0, 0, 0)))
        rows.append({"type": "lat_adapt", "lap": lap, "decisions": {"1": "baja", "2": "igual"}})
    rows.append(_tick(4, 0.0))
    log.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    res = ra.replay(log, ["lat"], {"lat": 9.5}, curvas, 3500.0)
    assert res["iniciales"]["lat"][1] == 11.4 and res["razon_libre"] == 0.942
    v2 = next(v for v in res["vueltas"] if v["lap"] == 2)
    assert v2["curvas"]["1"]["lat"]["decision"] == "baja" and v2["curvas"]["1"]["lat"]["veredicto"] == "grave"
    assert res["antes"]["lat"][2] == {"1": "baja", "2": "igual"}
