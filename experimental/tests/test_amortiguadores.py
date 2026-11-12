"""Tests de `amortiguadores.py`: rodillas del reglaje, estadísticas con el signo (+ = compresión) y lectura del log por vueltas."""

import json

import numpy as np

from experimental.identificacion import amortiguadores as am


def test_knees_are_transition_over_slow_coefficient():
    k = am.knees()
    assert np.allclose(k[0], (250 / 3600, 210 / 3700))
    assert np.allclose(k[2], (100 / 2300, 200 / 3700))
    assert np.allclose(k[0], k[1]) and np.allclose(k[2], k[3])


def test_stats_split_compression_and_rebound_and_fast_fraction():
    sv = np.array([0.01, 0.02, 0.2, -0.01, -0.3])
    st = am.stats(sv, (0.05, 0.05))
    assert st["n"] == 5
    assert st["comp_max"] == 0.2 and st["reb_max"] == 0.3
    assert st["rapida_comp_pct"] == 20.0 and st["rapida_ext_pct"] == 20.0


def test_histogram_sums_to_100_and_clips_extremes():
    h = am.histogram(np.array([-5.0, -0.2, 0.01, 0.2, 5.0]))
    assert abs(h.sum() - 100.0) < 1e-9
    assert h[0] == 20.0 and h[-1] == 20.0


def test_load_keeps_only_requested_laps(tmp_path):
    p = tmp_path / "log.jsonl"
    rows: list[dict[str, object]] = [{"type": "session"}]
    for lap in (1, 2, 3):
        rows.append({"type": "tick", "lap": lap, "lap_distance": 100.0 * lap, "speed_kmh": 80.0, "brake": 0.0, "throttle": 1.0,
                     "vehicle": {"susp_vel": [0.01 * lap] * 4, "susp_travel": [0.07] * 4, "terrain": [0, 0, 10, 0]}})
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    d = am.load(p, (2, 3))
    assert d["lap"].tolist() == [2, 3]
    assert np.allclose(d["sv"][:, 0], [0.02, 0.03])
    assert np.isin(d["terrain"], am.KERB_TERRAIN)[:, 2].all()
