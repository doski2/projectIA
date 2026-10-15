# pyright: reportArgumentType=false
"""Tests de humo para helpers compartidos (auditoría, secciones 1 y 4)."""

import argparse
import importlib
import sys
from types import SimpleNamespace

import pytest

from drive_actions import blend_actions
from driver_cli import add_diag_track_arg, add_safety_profile_arg, ns_str
from pretrain_universal import expand_globs
from reference_recorder import slugify
from telemetry_udp import (
    PACKET_CAR_PHYSICS,
    PACKET_PARTICIPANTS,
    PACKET_RACE_DEF,
    PACKET_TIMINGS,
    PACKET_VEHICLE_NAMES,
    apply_packet,
)


def test_slugify():
    assert slugify("  Sugo / GP-Course ") == "sugo_gp_course"
    assert slugify("???") == "unknown"


@pytest.mark.parametrize("prefix", ["", "_"])
def test_apply_packet_slots(prefix):
    st = SimpleNamespace()
    assert apply_packet(st, PACKET_CAR_PHYSICS, "t", prefix) == "physics"
    assert apply_packet(st, PACKET_TIMINGS, "i", prefix) == "timings"
    assert apply_packet(st, PACKET_RACE_DEF, "r", prefix) == "other"
    assert apply_packet(st, PACKET_VEHICLE_NAMES, "v", prefix) == "other"
    assert getattr(st, prefix + "last_telem") == "t"
    assert getattr(st, prefix + "last_timings") == "i"
    assert getattr(st, prefix + "race_data") == "r"
    assert getattr(st, prefix + "vehicle_info") == "v"


def test_apply_packet_ignores_none_and_unknown():
    st = SimpleNamespace()
    assert apply_packet(st, PACKET_CAR_PHYSICS, None) == "other"
    assert apply_packet(st, PACKET_PARTICIPANTS, "x") == "other"
    assert not vars(st)


def test_blend_actions_clamps_alpha():
    assert blend_actions((1, 0, 0), (0, 1, 1), 2.0) == (1.0, 0.0, 0.0)
    assert blend_actions((1, 0, 0), (0, 1, 1), -1.0) == (0.0, 1.0, 1.0)
    assert blend_actions((1, 0, 0), (0, 1, 1), 0.5) == (0.5, 0.5, 0.5)


def test_driver_cli_flags():
    p = argparse.ArgumentParser()
    add_safety_profile_arg(p)
    add_diag_track_arg(p)
    a = p.parse_args([])
    assert a.safety_profile == "l1_margin" and a.diag_track is False
    assert ns_str(argparse.Namespace(n=3), "n") == "3"


def test_expand_globs(tmp_path):
    f = tmp_path / "a.jsonl"
    f.write_text("")
    assert expand_globs([str(tmp_path / "*.jsonl"), str(tmp_path / "no.x")]) == [str(f)]


@pytest.mark.parametrize("mod", ["eval_driver", "eval_universal", "pretrain_universal"])
def test_parse_args_defaults(mod, monkeypatch):
    m = importlib.import_module(mod)
    monkeypatch.setattr(sys, "argv", [mod, "--help"])
    with pytest.raises(SystemExit) as e:
        m.parse_args()
    assert e.value.code == 0
