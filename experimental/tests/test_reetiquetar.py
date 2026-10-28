import json

import numpy as np
import pytest

from experimental.common import reetiquetar as rt


def _act(thr, brk, steer=0.1):
    return [2 * thr - 1, 2 * brk - 1, steer]


def test_menor_zeroes_smaller_pedal_and_keeps_steering():
    act = np.array([_act(0.2, 0.08), _act(0.05, 0.4), _act(0.3, 0.0), _act(0.0, 0.0), _act(0.2, 0.2)], dtype=np.float32)
    out = rt.relabel_actions(act, "menor")
    thr, brk = (out[:, 0] + 1) / 2, (out[:, 1] + 1) / 2
    assert np.allclose(thr, [0.2, 0.0, 0.3, 0.0, 0.2], atol=1e-6) and np.allclose(brk, [0.0, 0.4, 0.0, 0.0, 0.0], atol=1e-6)
    assert np.allclose(out[:, 2], act[:, 2]) and rt.overlap_share(out) == 0.0 and rt.overlap_share(act) > 0.0


def test_neto_leaves_a_single_axis():
    out = rt.relabel_actions(np.array([_act(0.2, 0.08), _act(0.05, 0.4)], dtype=np.float32), "neto")
    thr, brk = (out[:, 0] + 1) / 2, (out[:, 1] + 1) / 2
    assert np.allclose(thr, [0.12, 0.0], atol=1e-6) and np.allclose(brk, [0.0, 0.35], atol=1e-6)
    with pytest.raises(ValueError):
        rt.relabel_actions(out, "otro")


def test_jsonl_and_npz_do_not_touch_originals_and_drop_reasons(tmp_path):
    src = tmp_path / "base.jsonl"
    rows = [
        {"action": _act(0.2, 0.08), "teacher_reason": "maintain_speed", "obs": [0.0]},
        {"action": _act(0.5, 0.0), "teacher_reason": "accel_straight", "obs": [0.0]},
        {"action": _act(0.1, 0.3), "teacher_reason": "brake_overspeed", "obs": [0.0]},
    ]
    src.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    original = src.read_text(encoding="utf-8")

    npz = tmp_path / "cur.npz"
    rid = np.array([rt.encode_reason_id(r["teacher_reason"]) for r in rows])
    np.savez(npz, obs=np.zeros((3, 17), np.float32), act=np.array([r["action"] for r in rows], np.float32), rid=rid,
             quality=np.ones(3, np.float32), stage=np.array(["l1", "l1", "l1"]))

    res = rt.run([src, npz], "menor", ["maintain_speed"], out_dir=tmp_path / "out")
    assert src.read_text(encoding="utf-8") == original
    out_rows = [json.loads(line) for line in (tmp_path / "out" / "base_sinsolape.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["teacher_reason"] for r in out_rows] == ["accel_straight", "brake_overspeed"] and out_rows[0]["relabel"] == "menor"
    z = np.load(tmp_path / "out" / "cur_sinsolape.npz")
    assert len(z["act"]) == len(z["obs"]) == len(z["stage"]) == 2 and rt.overlap_share(z["act"]) == 0.0
    assert res["archivos"][str(tmp_path / "out" / "base_sinsolape.jsonl")]["descartadas"] == 1
    with pytest.raises(FileExistsError):
        rt.run([src], "menor", [], out_dir=tmp_path / "out")
