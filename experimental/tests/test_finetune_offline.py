import json
from pathlib import Path

import numpy as np
import pytest

from experimental.common import finetune_offline as fo
from obs_universal import OBS_SCHEMA, OBS_UNIVERSAL_DIM


def test_parse_source_relative_to_data_and_first():
    path, first = fo.parse_source("a_buffer.jsonl", Path("d"))
    assert path == Path("d") / "a_buffer.jsonl" and first is None
    assert fo.parse_source("a.jsonl:first=19469", Path("d"))[1] == 19469


@pytest.mark.parametrize("spec", ["a.jsonl:last=5", "a.jsonl:first=0", "a.jsonl:first=x"])
def test_parse_source_rejects_bad_option(spec):
    with pytest.raises(ValueError):
        fo.parse_source(spec, Path("d"))


def test_repeat_reason_duplicates_only_that_reason():
    rid = np.array([fo.encode_reason_id("maintain_speed"), fo.encode_reason_id("accel_straight")] * 2, dtype=np.int64)
    chunk = (np.arange(4, dtype=np.float32).reshape(4, 1), np.zeros((4, 3), dtype=np.float32), rid, [])
    obs, act, out_rid, _ = fo.repeat_reason(chunk, "accel_straight", 3)
    assert len(obs) == 4 + 2 * 2 and len(act) == len(out_rid) == len(obs)
    assert (out_rid == fo.encode_reason_id("accel_straight")).sum() == 2 * 3
    assert fo.repeat_reason(chunk, "accel_straight", 1) is chunk


def test_load_source_first_cuts_before_quality_filter(tmp_path):
    row = {"obs_schema": OBS_SCHEMA, "obs": [0.0] * OBS_UNIVERSAL_DIM, "action": [0, 0, 0], "quality": 0.9,
           "teacher_reason": "maintain_speed"}
    src = tmp_path / "b.jsonl"
    src.write_text("\n".join(json.dumps(row) for _ in range(10)) + "\n", encoding="utf-8")
    assert len(fo.load_source(src)[0]) == 10
    assert len(fo.load_source(src, first=4)[0]) == 4
