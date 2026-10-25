"""Curado del buffer online: dedupe, tope de maintain_speed y carga compacta."""

import json

from curate_dataset import curate, load_curated
from obs_universal import OBS_SCHEMA, OBS_UNIVERSAL_DIM


def _row(i, speed=0.1, act=(0.5, -1.0, 0.0), reason="maintain_speed", rid=1, quality=1.0,
         stage="l1_linea", band=20.0, schema=OBS_SCHEMA, track="SUGO_GP"):
    obs = [0.0] * OBS_UNIVERSAL_DIM
    obs[0] = speed
    return {
        "origin": "TEACHER", "obs": obs, "action": list(act), "quality": quality,
        "teacher_reason": reason, "reason_id": rid, "obs_schema": schema,
        "track_name": track, "learn_stage": stage, "speed_band_kmh": band, "lap_distance": float(i),
    }


def _write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_collapses_near_identical_consecutive_rows(tmp_path):
    src, dst = tmp_path / "b.jsonl", tmp_path / "c.npz"
    _write(src, [_row(i, speed=0.1 + i * 1e-4) for i in range(100)])
    stats = curate(str(src), str(dst), maintain_cap=1.0)
    assert stats["kept"] == 1 and stats["read"] == 100


def test_keeps_rows_that_change_and_never_mixes_bands(tmp_path):
    src, dst = tmp_path / "b.jsonl", tmp_path / "c.npz"
    rows = [_row(i, speed=0.1 * (i % 2 + 1), band=20.0) for i in range(10)]
    rows += [_row(i, speed=0.1, band=30.0) for i in range(3)]   # misma obs, otra banda
    _write(src, rows)
    stats = curate(str(src), str(dst), maintain_cap=1.0)
    assert stats["kept"] == 10 + 1


def test_filters_quality_and_schema(tmp_path):
    src, dst = tmp_path / "b.jsonl", tmp_path / "c.npz"
    _write(src, [
        _row(0, speed=0.1, quality=0.5),
        _row(1, speed=0.2, schema="legacy_19"),
        _row(2, speed=0.3, quality=0.95),
    ])
    stats = curate(str(src), str(dst), min_quality=0.9, maintain_cap=1.0)
    assert stats["kept"] == 1


def test_caps_maintain_speed_and_keeps_every_rare_reason(tmp_path):
    src, dst = tmp_path / "b.jsonl", tmp_path / "c.npz"
    rows = [_row(i, speed=0.02 * i) for i in range(1, 91)]
    rows += [_row(i, speed=0.5 + 0.02 * i, reason="recover_line", rid=3) for i in range(10)]
    _write(src, rows)
    curate(str(src), str(dst), maintain_cap=0.4)
    _, _, rid, _ = load_curated(str(dst))
    assert (rid == 3).sum() == 10
    assert (rid == 1).sum() == 6          # 0,4 / 0,6 x 10 filas raras


def test_load_curated_filters_like_the_buffer(tmp_path):
    src, dst = tmp_path / "b.jsonl", tmp_path / "c.npz"
    rows = [_row(i, speed=0.1 * (i + 1), stage="l1_linea", band=20.0) for i in range(5)]
    rows += [_row(i, speed=0.1 * (i + 1), stage="l2_velocidad", band=60.0) for i in range(4)]
    _write(src, rows)
    curate(str(src), str(dst), maintain_cap=1.0)
    obs, act, rid, meta = load_curated(str(dst), learn_stage="l2_velocidad", speed_band_kmh=60.0)
    assert obs.shape == (4, OBS_UNIVERSAL_DIM) and act.shape == (4, 3) and len(rid) == 4
    assert meta == []
    obs_all, _, _, _ = load_curated(str(dst))
    assert len(obs_all) == 9
    assert len(load_curated(str(dst), track_name="OTRA")[0]) == 0
