"""Deceleración de frenada por zona que se ajusta vuelta a vuelta (`--brake-adapt`, brake_adapt.py) y su efecto en el perfil de frenada del teacher."""

from pathlib import Path
from typing import Any

import pytest

from brake_adapt import BrakeAdaptConfig, BrakeAdapter
from lat_adapt import Zone, load_map, save_map
from reference_recorder import ReferenceLine
from teacher_controller import TeacherConfig, TeachingController
from tests.test_brake_profile import RECETA

SUGO = str(Path(__file__).resolve().parents[1] / "src" / "refs" / "sugo_ai.json")
LARGO = 3500.0
ZONAS = [Zone(1, 200.0, 300.0), Zone(2, 400.0, 500.0), Zone(3, 800.0, 900.0)]
DECEL = 11.0


def _adaptador(**kw) -> BrakeAdapter:
    return BrakeAdapter(ZONAS, base_limit=DECEL, track_length=LARGO, **kw)


def _vuelta(ad: BrakeAdapter, lap: int, sobre=None, pedal=None, limitador=None, frena=None) -> Any:
    """Alimenta una vuelta entera (un tick cada 5 m). La frenada de cada curva ocupa los 100 m antes de su final. `sobre` = {id de curva: velocidad sobre el perfil al soltar},
    `pedal`, `limitador` y `frena` (si hay frenada; por defecto sí) igual. Devuelve el resumen del primer tick de la vuelta siguiente."""
    sobre, pedal, limitador, frena = sobre or {}, pedal or {}, limitador or {}, frena or {}
    for d in range(0, int(LARGO), 5):
        zid = next((z.id for z in ZONAS if z.s1 - 100 <= d <= z.s1 and frena.get(z.id, True)), 0)
        ad.observe(lap, float(d), 0.3, 0.0, -20.0, False, braking=zid != 0, pedal=pedal.get(zid, 0.6) if zid else 0.0, limiter_scale=limitador.get(zid, 1.0), over_ms=sobre.get(zid, 0.0))
    return ad.observe(lap + 1, 0.0, 0.0, 0.0, -20.0, False)


def test_zone_of_a_distance_is_the_next_curve_end_and_the_finish_straight_belongs_to_c1():
    ad = _adaptador()
    assert [ad.zone_id(d) for d in (0.0, 150.0, 300.0, 301.0, 450.0, 500.0, 600.0, 900.0)] == [1, 1, 1, 2, 2, 2, 3, 3]
    assert ad.zone_id(3400.0) == 1  # pasada la última curva, la frenada es la de C1


def test_arriving_too_fast_goes_down_and_freezes_two_laps_and_the_others_are_left_alone():
    ad = _adaptador()
    r = _vuelta(ad, 2, sobre={1: 1.6})
    assert r["decisions"]["1"] == "baja" and ad.scales[1] == pytest.approx(0.92) and r["bad"] == [1]
    assert r["decisions"]["2"] == "igual" and r["decisions"]["3"] == "igual"  # a +0,0 m/s no hay que tocar nada
    assert _vuelta(ad, 3)["decisions"]["1"] == "congelada"
    assert _vuelta(ad, 4)["decisions"]["1"] == "congelada"
    assert _vuelta(ad, 5)["decisions"]["1"] == "igual"


def test_braking_more_than_needed_without_forcing_goes_up_but_a_saturated_or_limited_braking_does_not():
    ad = _adaptador()
    r = _vuelta(ad, 2, sobre={1: -0.8, 2: -0.8, 3: -0.8}, pedal={2: 0.97}, limitador={3: 0.4})
    assert r["decisions"] == {"1": "sube", "2": "igual", "3": "igual"}  # C2 va con el pedal a fondo y C3 con el limitador actuando: ahí no se pide más
    assert ad.scales[1] == pytest.approx(1.04) and ad.scales[2] == 1.0
    for lap in range(3, 15):
        _vuelta(ad, lap, sobre={1: -0.8})
    assert ad.scales[1] == pytest.approx(1.15)  # tope
    assert ad.limits()[1] == pytest.approx(DECEL * 1.15, abs=0.01)


def test_the_limiter_alone_is_not_a_reason_to_brake_less():
    ad = _adaptador()
    r = _vuelta(ad, 2, sobre={1: 0.3}, limitador={1: 0.25}, pedal={1: 0.95})  # como C7 en seco: limitador al 25 % y se suelta a +0,3 m/s del perfil
    assert r["decisions"]["1"] == "igual" and r["bad"] == [] and ad.scales[1] == 1.0
    assert r["metrics"]["1"]["limiter_min"] == 0.25 and r["metrics"]["1"]["pedal_max"] == 0.95


def test_a_zone_with_few_braking_ticks_is_not_judged_and_only_the_last_ticks_give_the_release_speed():
    ad = _adaptador()
    r = _vuelta(ad, 2, sobre={2: 3.0}, frena={2: False})
    assert r["decisions"]["2"] == "sin datos" and r["bad"] == []
    ad2 = _adaptador()
    for d in range(0, int(LARGO), 5):  # una frenada que empieza muy pasada y acaba en el perfil: manda el final
        over = 4.0 if d < 240 else 0.2
        ad2.observe(2, float(d), 0.3, 0.0, -20.0, False, braking=200 <= d <= 300, pedal=0.7, over_ms=over)
    m = ad2.observe(3, 0.0, 0.0, 0.0, -20.0, False)["metrics"]["1"]
    assert m["release_over_ms"] == pytest.approx(0.2) and m["over_max_ms"] == pytest.approx(4.0)


def test_fixed_map_measures_but_changes_nothing_the_first_lap_does_not_count_and_a_wrong_config_is_refused():
    ad = _adaptador(config=BrakeAdaptConfig(learn=False))
    assert _vuelta(ad, 1) is None
    r = _vuelta(ad, 2, sobre={1: 3.0})
    assert set(r["decisions"].values()) == {"fijo"} and all(v == 1.0 for v in ad.scales.values())
    from lat_adapt import LatAdaptConfig

    with pytest.raises(TypeError):
        BrakeAdapter(ZONAS, base_limit=DECEL, track_length=LARGO, config=LatAdaptConfig())


def test_scales_per_metre_follow_the_zones_and_the_saved_map_keeps_the_absolute_deceleration(tmp_path: Path):
    ad = _adaptador()
    for lap in range(2, 6):
        _vuelta(ad, lap, sobre={1: -0.8})
    per_m = ad.scales_per_m(int(LARGO))
    assert len(per_m) == int(LARGO) and per_m[250] == ad.scales[1] == per_m[3400] and per_m[450] == 1.0 and per_m[850] == 1.0
    ad.start({"rain": 0, "track_c": 21, "ambient_c": 14, "tyre_start_c": 84.0, "compound": "Lisos"})
    ruta = tmp_path / "frenos.json"
    save_map(ruta, ad.snapshot({"experiment": "x"}))
    datos = load_map(ruta)
    assert datos["base_limit"] == DECEL
    mismo = _adaptador()
    mismo.load_prior(load_map(ruta))
    assert mismo.start({"rain": 0, "track_c": 21, "ambient_c": 14, "tyre_start_c": 84.0, "compound": "Lisos"})["applied"] and mismo.scales[1] == pytest.approx(ad.scales[1], abs=1e-3)
    mojado = _adaptador()
    mojado.load_prior(load_map(ruta))
    assert mojado.start({"rain": 153, "track_c": 13, "ambient_c": 10, "tyre_start_c": 84.0, "compound": "Lisos"})["applied"] is False  # un mapa de seco no se aplica en mojado
    otra = BrakeAdapter(ZONAS, base_limit=12.0, track_length=LARGO)  # otra --brake-decel-straight: se conserva la deceleración absoluta
    otra.load_prior(load_map(ruta))
    otra.start({"rain": 0, "track_c": 21, "ambient_c": 14, "tyre_start_c": 84.0, "compound": "Lisos"})
    assert otra.scales[1] * 12.0 == pytest.approx(ad.scales[1] * DECEL, rel=0.001)


# ── el teacher: la deceleración por metro cambia dónde empieza a frenar el perfil ──────────────────────────────────────────────────────────────────────────────
def _teacher() -> TeachingController:
    return TeachingController(ReferenceLine.load(SUGO), TeacherConfig(**RECETA))


def test_a_lower_deceleration_scale_starts_braking_earlier_and_a_higher_one_later_and_none_changes_nothing():
    t = _teacher()
    base = list(t.braking_profile())
    n = len(base)
    t.set_brake_scales([1.0] * n)
    assert t.braking_profile() == base  # 1,0 en todas partes = el perfil de siempre
    t.set_brake_scales([0.7] * n)
    suave = t.braking_profile()
    t.set_brake_scales([1.3] * n)
    fuerte = t.braking_profile()
    assert all(a <= b + 1e-9 for a, b in zip(suave, base)) and all(a >= b - 1e-9 for a, b in zip(fuerte, base))
    assert sum(suave) < sum(base) < sum(fuerte)  # con menos freno disponible el perfil baja antes de cada curva
    t.set_brake_scales(None)
    assert t.braking_profile() == base


def test_the_scale_only_changes_the_profile_before_its_own_curve():
    t = _teacher()
    base = list(t.braking_profile())
    n = len(base)
    t.set_brake_scales([0.6 if 1000 <= d <= 1100 else 1.0 for d in range(n)])
    cambiado = t.braking_profile()
    dif = [d for d in range(n) if abs(cambiado[d] - base[d]) > 1e-9]
    assert dif and all(d <= 1100 or d >= 1100 - 400 for d in dif) and min(dif) < 1100 and all(abs(cambiado[d] - base[d]) < 1e-9 for d in range(1500, 2500))


def test_entry_phase_is_exposed():
    t = _teacher()
    t._phase = "entry"
    assert t.entry_phase is True
    t._phase = "exit"
    assert t.entry_phase is False
