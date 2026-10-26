import json
from types import SimpleNamespace

from session_log import LOG_SCHEMA, TeachingSessionRecorder, default_log_path, vehicle_diag, vehicle_extra


def _frame(**extra):
    base = dict(
        steering=-64, raw_steering=127, angular_velocity=(0.1, 0.2, 0.3),
        local_acceleration=(1.5, 0.25, 3.0), terrain=(0, 0, 7, 7),
        tyre_rps=(10.123, 10.0, 9.0, 9.0), throttle=255, brake=0,
    )
    base.update(extra)
    return SimpleNamespace(**base)


def test_extra_fields_added_after_existing_ones():
    t = _frame(
        local_velocity=(20.12345, -0.5, 0.01), position=(1.234, 2.0, 3.0),
        orientation=(0.0, 0.01, 1.5), ride_height=(0.05,) * 4, suspension_travel=(0.02,) * 4,
        tyre_temp=(80, 81, 82, 83), tyre_tread_temp=(90, 91, 92, 93), tyre_wear=(1, 1, 2, 2),
        fuel_level=0.5, brake_bias=60, aero_damage=0, engine_damage=0,
        raw_throttle=200, raw_brake=0, clutch=0,
    )
    d = vehicle_diag(t)
    keys = list(d)
    assert keys[:8] == [
        "game_steer", "raw_steer", "game_throttle", "game_brake",
        "yaw_rate", "lat_accel", "terrain", "tyre_rps",
    ]
    assert d["local_velocity"] == [20.123, -0.5, 0.01]
    assert d["local_accel"] == [1.5, 0.25, 3.0]
    assert d["ang_vel"] == [0.1, 0.2, 0.3]
    assert d["tyre_temp"] == [80, 81, 82, 83]
    assert d["clutch"] == 0


def test_extra_fields_skipped_when_frame_lacks_them():
    assert vehicle_extra(_frame()) == {"local_accel": [1.5, 0.25, 3.0], "ang_vel": [0.1, 0.2, 0.3]}


def test_header_defaults_and_experiment(tmp_path):
    p = tmp_path / "a.jsonl"
    rec = TeachingSessionRecorder.open(p, {"mode": "learn"})
    assert rec._file is not None
    rec._file.close()
    head = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert head["log_schema"] == LOG_SCHEMA and head["origin"] == "main"

    p2 = tmp_path / "b.jsonl"
    rec = TeachingSessionRecorder.open(p2, {"origin": "experimental", "experiment": "rampa_bc"})
    assert rec._file is not None
    rec._file.close()
    head = json.loads(p2.read_text(encoding="utf-8").splitlines()[0])
    assert head["origin"] == "experimental" and head["experiment"] == "rampa_bc"


def test_default_log_path_unchanged():
    p = default_log_path("Sugo", "L1", category="learning")
    assert p.parts[:2] == ("logs", "learning") and p.name.endswith("_sugo_L1.jsonl")


def test_timing_diag_and_tick_row(tmp_path):
    from session_log import timing_diag

    tm = SimpleNamespace(sector=2, current_sector_time=12.34567, current_time=45.6789)
    d = timing_diag(tm)
    assert d == {"sector": 2, "sector_time_s": 12.346, "game_time_s": 45.679}

    rec = TeachingSessionRecorder.open(tmp_path / "t.jsonl", {})

    def tick(timing=None):
        rec.record_tick(
            telem_speed_kmh=10.0, lap=1, lap_distance=5.0, cte=0.0, signed_cte=0.0, heading_err=0.0,
            throttle=0.0, brake=0.0, steering=0.0, teacher_reason="x", timing=timing,
        )

    tick(d)
    tick()
    assert rec._file is not None
    rec._file.close()
    rows = [json.loads(line) for line in (tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[1]["timing"] == d and "timing" not in rows[2]
