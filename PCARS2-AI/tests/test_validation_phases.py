"""Tests de fases de validación y reporte HTML."""

import json
import tempfile
from pathlib import Path

from session_report import write_html_replay
from validation_phases import evaluate_phase, get_phase


def _synthetic_ticks(n: int = 120, lap_reason: str = "accel_straight") -> list:
    ticks = []
    for i in range(n):
        ticks.append({
            "t_s": i * 0.4,
            "cte": 2.0 + (i % 5) * 0.2,
            "speed_kmh": 18.0,
            "teacher_reason": lap_reason if i % 3 else "maintain_speed",
            "off_track": False,
            "stuck": False,
            "safety_override": False,
            "throttle": 0.4,
            "brake": 0.0,
            "steering": 0.1,
        })
    return ticks


def test_f1_passes_with_good_ticks():
    ticks = _synthetic_ticks(150)
    result = evaluate_phase("f1_linea", ticks, laps_completed=1)
    assert result["passed"] is True
    assert result["next_phase"] == "f2_acelerar"


def test_f1_fails_without_lap():
    ticks = _synthetic_ticks(80)
    result = evaluate_phase("f1_linea", ticks, laps_completed=0)
    assert result["passed"] is False


def test_html_report_generated():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.jsonl"
        session = {"type": "session", "phase": "f1_linea", "track": "sugo"}
        path.write_text(
            json.dumps(session) + "\n"
            + "\n".join(
                json.dumps({"type": "tick", **t})
                for t in _synthetic_ticks(120)
            )
            + "\n",
            encoding="utf-8",
        )
        html = write_html_replay(path, laps_completed=1)
        assert html is not None
        assert html.is_file()
        content = html.read_text(encoding="utf-8")
        assert "Teaching validation" in content
        assert "CTE medio" in content


def test_get_phase_defaults():
    p = get_phase("unknown")
    assert p.id == "f1_linea"
