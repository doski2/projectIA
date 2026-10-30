"""Tests de la puerta por ciclos de la rampa (C1, D20)."""

import pytest

from ramp_gate import CYCLE_CLEAN, CYCLE_DIRTY, DROP, RISE, STOP, TOP, RampGate, bands_from


def _cycle(g, *laps):
    """Vuelta de salida (cualquiera) + las lanzadas; devuelve el evento del cierre."""
    assert g.on_lap(True) is None
    ev = None
    for clean in laps:
        ev = g.on_lap(clean)
    return ev


def test_bands_from_step():
    assert bands_from(60, 80, 5) == [60.0, 65.0, 70.0, 75.0, 80.0]
    assert bands_from(60, 80, 7.5) == [60.0, 67.5, 75.0]
    with pytest.raises(ValueError):
        bands_from(60, 50, 5)
    with pytest.raises(ValueError):
        bands_from(60, 80, 0)


def test_out_lap_does_not_score():
    g = RampGate(bands=[60, 65])
    assert g.on_lap(False) is None  # la de salida, sucia, no cuenta
    assert g.on_lap(True) is None
    assert g.on_lap(True) == CYCLE_CLEAN


def test_two_clean_cycles_rise():
    g = RampGate(bands=[60, 65, 70])
    assert _cycle(g, True, True) == CYCLE_CLEAN
    assert g.band == 60
    assert _cycle(g, True, True) == RISE
    assert g.band == 65 and g.clean_cycles == 0 and g.pos == 0


def test_dirty_lap_makes_cycle_dirty_and_resets_clean_cycles():
    g = RampGate(bands=[60, 65])
    assert _cycle(g, True, True) == CYCLE_CLEAN
    assert _cycle(g, True, False) == CYCLE_DIRTY
    assert g.band == 60 and g.clean_cycles == 0
    assert _cycle(g, True, True) == CYCLE_CLEAN  # los ciclos limpios deben ser seguidos
    assert _cycle(g, True, True) == RISE


def test_three_dirty_cycles_drop_a_band():
    g = RampGate(bands=[60, 65, 70], index=1)
    assert _cycle(g, False, False) == CYCLE_DIRTY
    assert _cycle(g, True, False) == CYCLE_DIRTY
    assert _cycle(g, False, True) == DROP
    assert g.band == 60 and g.dirty_cycles == 0


def test_three_dirty_cycles_at_lowest_band_stop():
    g = RampGate(bands=[60, 65])
    _cycle(g, False, False)
    _cycle(g, False, False)
    assert _cycle(g, False, False) == STOP


def test_top_of_ramp_ends_it():
    g = RampGate(bands=[60, 65], index=1)
    assert _cycle(g, True, True) == CYCLE_CLEAN
    assert _cycle(g, True, True) == TOP
    assert g.band == 65


def test_dirty_cycles_need_to_be_consecutive():
    g = RampGate(bands=[60, 65])
    _cycle(g, False, False)
    _cycle(g, False, False)
    assert _cycle(g, True, True) == CYCLE_CLEAN  # corta la racha de sucios
    assert g.dirty_cycles == 0


def test_longer_cycle():
    g = RampGate(bands=[60, 65], laps_per_cycle=3, cycles_to_rise=1)
    assert g.cycle_laps == 4
    assert _cycle(g, True, True, True) == RISE


def test_save_and_load_roundtrip(tmp_path):
    g = RampGate(bands=[60, 65, 70])
    _cycle(g, True, True)
    g.on_lap(True)  # a medias de otro ciclo
    f = tmp_path / "sub" / "ramp.json"
    g.save(f)
    h = RampGate.load(f)
    assert h == g and h.band == 60 and h.pos == 1 and h.clean_cycles == 1


def test_restart_cycle_discards_partial_cycle():
    g = RampGate(bands=[60, 65])
    g.on_lap(True)
    g.on_lap(False)  # a medias de un ciclo sucio
    g.restart_cycle()
    assert g.pos == 0 and g.cycle_clean is True
    assert _cycle(g, True, True) == CYCLE_CLEAN  # la sucia no cuenta


def test_load_missing_or_broken(tmp_path):
    assert RampGate.load(tmp_path / "no.json") is None
    (tmp_path / "x.json").write_text("{no es json", encoding="utf-8")
    assert RampGate.load(tmp_path / "x.json") is None
    (tmp_path / "y.json").write_text('{"otra": 1}', encoding="utf-8")
    assert RampGate.load(tmp_path / "y.json") is None


def test_invalid_params():
    with pytest.raises(ValueError):
        RampGate(bands=[])
    with pytest.raises(ValueError):
        RampGate(bands=[60], laps_per_cycle=0)
