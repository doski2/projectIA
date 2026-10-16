"""Tests del dataset recorder."""

import os
import tempfile

import numpy as np

from dataset_recorder import ORIGIN_TEACHER, DatasetRecorder, load_dataset
from obs_builder import OBS_DIM


def test_record_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.jsonl")
        rec = DatasetRecorder(output_path=path, origin=ORIGIN_TEACHER)
        rec.open()
        obs = np.zeros(OBS_DIM, dtype=np.float32)
        ok = rec.maybe_record(
            obs=obs,
            action=(0.5, 0.0, 0.1),
            lap_distance=100.0,
            cte=1.0,
            heading_err=0.05,
            teacher_reason="cruise",
        )
        rec.close()
        assert ok
        assert rec.samples_written == 1

        obs_arr, act_arr, meta = load_dataset(path, origin=ORIGIN_TEACHER)
        assert len(obs_arr) == 1
        assert meta[0]["origin"] == ORIGIN_TEACHER
        assert meta[0]["teacher_reason"] == "maintain_speed"
        assert "rule" in meta[0]


def test_skip_low_quality():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "bad.jsonl")
        rec = DatasetRecorder(output_path=path, origin=ORIGIN_TEACHER)
        rec.open()
        obs = np.zeros(OBS_DIM, dtype=np.float32)
        ok = rec.maybe_record(
            obs=obs,
            action=(0.0, 0.0, 0.0),
            lap_distance=0.0,
            cte=10.0,
            heading_err=0.0,
            safety=True,
        )
        rec.close()
        assert not ok
        assert rec.samples_skipped == 1
