"""Tests de la línea suavizada para alta velocidad (`linea_suave.py`, H61) con un óvalo sintético de solución conocida."""

import math
from pathlib import Path

import numpy as np
import pytest

from circuito_virtual.src import linea_suave as ls

STRAIGHT = 400
RADIUS = 50.0


def _oval(bump_m=0.0, bump_at=200):
    """Óvalo cerrado: dos rectas de 400 m y dos semicírculos de 50 m, un punto por metro; `bump_m` desplaza lateralmente 6 m de la 1ª recta."""
    pts = []
    for s in range(STRAIGHT):
        off = bump_m * math.sin(math.pi * (s - bump_at) / 6.0) ** 2 if abs(s - bump_at) < 6 else 0.0
        pts.append((float(s), off))
    n_arc = int(math.pi * RADIUS)
    for i in range(n_arc):
        a = -math.pi / 2 + math.pi * i / n_arc
        pts.append((STRAIGHT + RADIUS * math.cos(a), RADIUS + RADIUS * math.sin(a)))
    for s in range(STRAIGHT):
        pts.append((float(STRAIGHT - s), 2 * RADIUS))
    for i in range(n_arc):
        a = math.pi / 2 + math.pi * i / n_arc
        pts.append((RADIUS * math.cos(a), RADIUS + RADIUS * math.sin(a)))
    return pts


def _data(points):
    return {"track_name": "oval", "track_length": float(len(points)), "lap_time": 60.0, "resolution": 1.0,
            "points": [{"d": float(i), "pos": [x, 0.0, z], "spd": 16.6, "gear": 2, "ori": [0.0, 0.0, 0.0]} for i, (x, z) in enumerate(points)]}


def test_a_small_kink_in_a_straight_is_removed_and_the_corner_is_untouched():
    data = _data(_oval(bump_m=0.3))
    out, report = ls.smooth_reference(data)
    x = np.array([p["pos"][0] for p in out["points"]])
    z = np.array([p["pos"][2] for p in out["points"]])
    k_before = np.abs(ls.curvature(ls._smooth(np.array([p["pos"][0] for p in data["points"]]), 3),
                                   ls._smooth(np.array([p["pos"][2] for p in data["points"]]), 3)))[190:210].max()
    k_after = np.abs(ls.curvature(ls._smooth(x, 3), ls._smooth(z, 3)))[190:210].max()
    assert k_before > 0.003 and k_after < 0.002
    # el centro del semicírculo (a unos 20 m del final de la recta) no cambia
    corner = slice(STRAIGHT + 60, STRAIGHT + 100)
    x0 = np.array([p["pos"][0] for p in data["points"]])
    z0 = np.array([p["pos"][2] for p in data["points"]])
    assert np.hypot(x - x0, z - z0)[corner].max() < 0.01
    assert report and max(r["desplazamiento_m"] for r in report) <= ls.MAX_DISPLACEMENT_M


def test_keeps_the_point_count_other_fields_and_the_input_untouched():
    data = _data(_oval(bump_m=0.3))
    before = [list(p["pos"]) for p in data["points"]]
    out, _ = ls.smooth_reference(data)
    assert len(out["points"]) == len(data["points"])
    assert all(o["spd"] == 16.6 and o["gear"] == 2 and o["ori"] == [0.0, 0.0, 0.0] and o["pos"][1] == 0.0 for o in out["points"])
    assert [list(p["pos"]) for p in data["points"]] == before  # la entrada no se modifica
    assert out["suavizada"]["sigma_m"] == ls.SIGMA_M


def test_a_clean_oval_is_barely_moved():
    out, _ = ls.smooth_reference(_data(_oval()))
    assert out["suavizada"]["desplazamiento_max_m"] < 0.05


def test_refuses_to_move_the_line_more_than_the_limit():
    with pytest.raises(ValueError, match="más del máximo"):
        ls.smooth_reference(_data(_oval(bump_m=0.3)), max_displacement=0.05)


def test_cli_does_not_overwrite_its_input(tmp_path, capsys):
    path = tmp_path / "ref.json"
    import json

    path.write_text(json.dumps(_data(_oval(bump_m=0.3))), encoding="utf-8")
    with pytest.raises(SystemExit):
        ls.main(["--entrada", str(path), "--salida", str(path)])
    out = tmp_path / "suave.json"
    assert ls.main(["--entrada", str(path), "--salida", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["suavizada"]["origen"].startswith("linea_suave")


def test_sugo_reference_loses_its_straight_kinks_with_less_than_a_metre_of_shift():
    import json

    data = json.loads(ls.DEFAULT_IN.read_text(encoding="utf-8"))
    out, report = ls.smooth_reference(data)
    assert len(out["points"]) == len(data["points"])
    assert out["suavizada"]["desplazamiento_max_m"] <= 1.0
    kink = [r for r in report if r["d0"] <= 3300 <= r["d1"]]
    assert kink and kink[0]["kappa_antes"] > 0.005 and kink[0]["kappa_despues"] < 0.002  # el quiebro de 3300 m de H60
    real = np.array([p["pos"][2] for p in data["points"]]), np.array([p["pos"][2] for p in out["points"]])
    assert np.abs(real[0] - real[1])[912:955].max() < 0.01  # la curva real de 50 m no se toca
