"""Tests de `experimental/identificacion/patinazo_traccion.py` (techo del patinazo trasero, A/B del control de tracción)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from experimental.identificacion import patinazo_traccion as pt

CALIB = 0.9425


def _tick(i: int, lap: int, s: float, gas: float, slip: float, gear: int = 2, clutch: int = 0, gas_pedido: float | None = None) -> dict:
    front = 100.0
    rear = front * CALIB * (1.0 + slip)
    return {"type": "tick", "tick": i, "lap": lap, "lap_distance": s, "speed_kmh": 90.0, "gear": gear,
            "steering": 0.0, "throttle": gas if gas_pedido is None else gas_pedido, "brake": 0.0,
            "vehicle": {"tyre_rps": [front, front, -rear, -rear], "game_throttle": gas, "game_brake": 0.0, "clutch": clutch}}


def _write(tmp_path: Path, ticks: list) -> Path:
    p = tmp_path / "log.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "session", "track": "pista_que_no_existe"}) + "\n")
        for t in ticks:
            fh.write(json.dumps(t) + "\n")
    return p


def test_gear_stable_excludes_the_ticks_around_a_gear_change():
    gear = np.array([2] * 10 + [0] + [3] * 10)
    ok = pt.gear_stable(gear, 2)
    assert not ok[:2].any() and not ok[-2:].any()
    assert ok[2:8].all()
    assert not ok[8:13].any()
    assert ok[13:19].all()


def test_slip_is_measured_against_the_light_throttle_ratio_and_the_ceiling_is_located(tmp_path):
    ticks = []
    i = 0
    for k in range(30):  # calibración: poco gas, sin patinazo
        ticks.append(_tick(i, 4, 100.0 + k, 0.1, 0.0))
        i += 1
    for k in range(30):  # gas a fondo: 2 % de patinazo
        ticks.append(_tick(i, 4, 200.0 + k, 1.0, 0.02))
        i += 1
    for k in range(10):  # techo del 6 % en otra zona
        ticks.append(_tick(i, 5, 900.0 + k, 1.0, 0.06))
        i += 1
    for k in range(10):  # final de un cambio: embrague entrando y gas cortado; no cuenta ni para calibrar ni para medir
        ticks.append(_tick(i, 5, 950.0 + k, 0.0, 0.04, clutch=150, gas_pedido=1.0))
        i += 1
    for k in range(10):
        ticks.append(_tick(i, 5, 1000.0 + k, 0.1, 0.0))
        i += 1
    r = pt.analyze(_write(tmp_path, ticks), (4, 6), margin=1)
    assert abs(r["calibracion"] - CALIB) < 1e-6
    assert abs(r["max"] - 6.0) < 1e-6
    assert abs(r["p50"] - 2.0) < 1e-6
    assert r["n_techo"] == 10
    (zona,) = r["techo"].values()
    assert zona["s"] == (900.0, 909.0) and zona["marchas"] == [2]
