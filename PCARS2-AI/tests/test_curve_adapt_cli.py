"""Opciones del ajuste por curva (`curve_adapt_cli.py`): las nuevas y los alias de las de antes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import curve_adapt_cli as cli

CURVAS = {"pista": "x", "curvas": [{"id": 1, "s_ini": 200.0, "s_apice": 250.0, "s_fin": 300.0}, {"id": 2, "s_ini": 800.0, "s_apice": 850.0, "s_fin": 900.0}]}
RECETA = ["--lat-accel-limit", "9.5", "--exit-circle", "18", "--brake-decel-straight", "11"]


def _parse(tmp_path: Path, *argv: str):
    ref = tmp_path / "ref.json"
    ref.write_text("{}", encoding="utf-8")
    (tmp_path / "curvas.json").write_text(json.dumps(CURVAS), encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--lat-accel-limit", type=float, default=0.0)
    p.add_argument("--exit-circle", type=float, default=0.0)
    p.add_argument("--brake-decel-straight", type=float, default=0.0)
    p.add_argument("--pedal-technique", action="store_true")
    p.add_argument("--brake-profile", action="store_true")
    p.add_argument("--experiment", default="")
    cli.add_arguments(p)
    return p.parse_args(list(argv)), str(ref)


def _v1(tmp_path: Path, name: str, base: float, scales) -> str:
    path = tmp_path / name
    path.write_text(json.dumps({"version": 1, "base_limit": base, "scales": {str(i + 1): s for i, s in enumerate(scales)}, "conditions": {"rain": 0}}), encoding="utf-8")
    return str(path)


def test_nothing_asked_nothing_built(tmp_path):
    args, ref = _parse(tmp_path, *RECETA)
    assert cli.build(args, ref, 3500.0) is None


def test_old_options_are_aliases_with_the_same_caps_maps_and_fixed_channels(tmp_path):
    lat = _v1(tmp_path, "lat.json", 9.5, [1.2, 1.0])
    ext = _v1(tmp_path, "exit.json", 18.0, [1.3, 0.85])
    args, ref = _parse(tmp_path, *RECETA, "--pedal-technique", "--brake-profile",
                       "--lat-adapt", "--lat-adapt-fixed", "--lat-adapt-cap", "14", "--lat-adapt-max-scale", "1.5", "--lat-adapt-load", lat,
                       "--exit-adapt", "--exit-adapt-fixed", "--exit-adapt-load", ext, "--brake-adapt")
    rt = cli.build(args, ref, 3500.0)
    assert rt is not None
    ad = rt.adapter
    assert ad.channels == ("lat", "exit", "brake") and ad.cfg.fixed == ("lat", "exit") and ad.cfg.learn
    assert ad.cfg.maxima["lat"] == pytest.approx(14.0) and ad.cfg.maxima["exit"] == pytest.approx(23.4) and ad.cfg.maxima["brake"] == pytest.approx(12.65)
    ad.start({"rain": 0})
    assert ad.values("lat") == {1: 11.4, 2: 9.5} and ad.values("exit") == {1: 23.4, 2: 15.3}


def test_old_default_lat_cap_is_still_ten(tmp_path):
    args, ref = _parse(tmp_path, *RECETA, "--lat-adapt")
    rt = cli.build(args, ref, 3500.0)
    assert rt is not None and rt.adapter.cfg.maxima["lat"] == pytest.approx(10.0)


def test_new_options_channels_maps_and_maxima(tmp_path):
    lat = _v1(tmp_path, "lat.json", 9.5, [1.1, 1.0])
    args, ref = _parse(tmp_path, *RECETA, "--pedal-technique", "--curve-adapt", "--curve-adapt-only", "lat,exit",
                       "--curve-adapt-load", f"lat={lat}", "--curve-adapt-max", "lat=13", "--curve-adapt-save", str(tmp_path / "nuevo.json"))
    rt = cli.build(args, ref, 3500.0)
    assert rt is not None and rt.adapter.channels == ("lat", "exit") and rt.adapter.cfg.maxima["lat"] == 13.0 and rt.save_path.endswith("nuevo.json")
    rt.adapter.start({"rain": 0})
    assert rt.adapter.values("lat")[1] == pytest.approx(10.45)


@pytest.mark.parametrize("argv, msg", [
    (("--curve-adapt", "--lat-adapt"), "no se mezcla"),
    (("--curve-adapt", "--curve-adapt-only", "gas"), "desconocidos"),
    (("--curve-adapt", "--curve-adapt-fixed"), "necesita --curve-adapt-load"),
    (("--lat-adapt", "--lat-adapt-fixed"), "necesita --lat-adapt-load"),
    (("--exit-adapt",), "--pedal-technique"),
    (("--brake-adapt", "--pedal-technique"), "--brake-profile"),
])
def test_impossible_combinations_stop_before_driving(tmp_path, argv, msg):
    args, ref = _parse(tmp_path, *RECETA, *argv)
    with pytest.raises(SystemExit, match=msg):
        cli.build(args, ref, 3500.0)


def test_runtime_applies_values_to_the_teacher_at_start_and_after_each_lap(tmp_path):
    args, ref = _parse(tmp_path, *RECETA, "--curve-adapt", "--curve-adapt-only", "lat")
    rt = cli.build(args, ref, 3500.0)
    assert rt is not None
    got = {}
    teacher = SimpleNamespace(set_lat_scales=lambda s: got.__setitem__("lat", s), set_exit_scales=None, set_brake_scales=None)
    events = []
    rt.start({"rain": 0}, None, teacher, events.append)
    assert rt.started and events[0]["type"] == "curve_adapt_start" and len(got["lat"]) == 3500 and set(got["lat"]) == {1.0}
