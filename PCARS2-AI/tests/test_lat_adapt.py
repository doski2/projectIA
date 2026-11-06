"""Límite lateral por curva que se ajusta vuelta a vuelta (`--lat-adapt`, lat_adapt.py) y su efecto en el perfil del teacher."""

import math
import time
from pathlib import Path
from typing import Any, Tuple

import pytest

from lat_adapt import LatAdaptConfig, LatAdapter, Zone, drift_deg, load_map, save_map
from reference_recorder import ReferenceLine
from teacher_controller import TeacherConfig, TeachingController
from tests.test_brake_profile import RECETA

SUGO = str(Path(__file__).resolve().parents[1] / "src" / "refs" / "sugo_ai.json")
LARGO = 3500.0
ZONAS = [Zone(1, 200.0, 300.0), Zone(2, 400.0, 500.0), Zone(3, 800.0, 900.0)]


def _adaptador(**kw) -> LatAdapter:
    return LatAdapter(ZONAS, base_limit=9.5, track_length=LARGO, **kw)


def _vuelta(ad: LatAdapter, lap: int, cte=None, deriva=None, fuera=None, tyre=None) -> Any:
    """Alimenta una vuelta entera (un tick cada 10 m). `cte`/`deriva`/`fuera`: {id de curva: valor}. Devuelve el resumen que da el primer tick de la vuelta siguiente."""
    cte, deriva, fuera = cte or {}, deriva or {}, fuera or {}
    for d in range(0, int(LARGO), 10):
        zona = next((z for z in ZONAS if z.s0 <= d <= z.s1), None)
        zid = zona.id if zona else 0
        beta = math.radians(deriva.get(zid, 0.0))
        ad.observe(lap, float(d), cte.get(zid, 0.2), 20.0 * math.sin(beta), -20.0 * math.cos(beta), bool(fuera.get(zid, False)), tyre_c=tyre)
    return ad.observe(lap + 1, 0.0, 0.0, 0.0, -20.0, False)


def test_drift_deg_matches_the_session_summary_formula():
    assert drift_deg(1.0, -20.0) == pytest.approx(2.862, abs=0.01)
    assert drift_deg(5.0, -3.0) == 0.0  # por debajo de 5 m/s no se mide


def test_a_clean_curve_goes_up_a_dirty_one_goes_down_and_freezes():
    ad = _adaptador()
    assert _vuelta(ad, 1) is None  # la vuelta de salida no cuenta
    up = _vuelta(ad, 2, cte={1: 0.5, 2: 2.5, 3: 1.5})
    assert up["decisions"] == {"1": "igual", "2": "baja", "3": "igual"}  # 1 tiene la vecina 2 en mal estado; 3 está entre 1,2 y 1,8
    assert ad.scales[2] == pytest.approx(0.92) and ad.frozen[2] == 2
    # vuelta siguiente, todo limpio: la 2 está congelada; la 1 ya no tiene la vecina mala pero la 2 sigue congelada (no es «mala»)
    up = _vuelta(ad, 3)
    assert up["decisions"]["2"] == "congelada" and up["decisions"]["1"] == "sube" and up["decisions"]["3"] == "sube"
    assert ad.scales[1] == pytest.approx(1.04) and ad.scales[2] == pytest.approx(0.92)


def test_wheels_off_or_drift_make_a_curve_bad_and_the_limits_are_capped():
    ad = _adaptador(cap_limit=10.0)
    _vuelta(ad, 1)
    r = _vuelta(ad, 2, fuera={1: True}, deriva={3: 5.0})
    assert r["decisions"]["1"] == "baja" and r["decisions"]["3"] == "baja"
    # tope: 10 / 9,5 = 1,0526 como máximo, aunque el multiplicador permitido sea 1,15
    for lap in range(3, 12):
        _vuelta(ad, lap)
    assert max(ad.scales.values()) == pytest.approx(10.0 / 9.5)
    assert max(ad.limits().values()) <= 10.0 + 1e-9


def test_scales_never_go_below_the_minimum():
    ad = _adaptador()
    _vuelta(ad, 1)
    for lap in range(2, 20):
        _vuelta(ad, lap, cte={2: 3.0})
    assert ad.scales[2] == pytest.approx(LatAdaptConfig().min_scale)


def test_incomplete_laps_and_laps_without_data_are_ignored():
    ad = _adaptador()
    _vuelta(ad, 1)
    for d in range(0, 1000, 10):  # media vuelta (reinicio): no se fía
        ad.observe(2, float(d), 3.0, 0.0, -20.0, False)
    assert ad.observe(3, 0.0, 0.0, 0.0, -20.0, False) is None
    assert all(v == 1.0 for v in ad.scales.values())


def test_scales_per_meter_cover_each_curve_and_its_exit_only():
    ad = _adaptador()
    ad.scales[2] = 0.9
    s = ad.scales_per_m()
    assert len(s) == int(LARGO) and s[450] == pytest.approx(0.9) and s[514] == pytest.approx(0.9)  # hasta la salida + 15 m
    assert s[520] == 1.0 and s[100] == 1.0 and s[399] == 1.0


def test_base_limit_above_the_cap_means_curves_can_go_down_but_not_up():
    ad = LatAdapter(ZONAS, base_limit=12.0, track_length=LARGO, cap_limit=10.0)
    _vuelta(ad, 1)
    _vuelta(ad, 2)
    assert max(ad.scales.values()) == 1.0


def _controlador(**cfg) -> TeachingController:
    return TeachingController(ReferenceLine.load(SUGO), TeacherConfig(**{**RECETA, "pedal_technique": True, "brake_profile": True, **cfg}))


def test_teacher_without_scales_keeps_the_same_profile_and_with_scales_only_changes_those_meters():
    base = _controlador()
    perfil0 = list(base.braking_profile())
    assert base._lat_scales is None
    n = len(perfil0)
    scales = [1.0] * n
    for d in range(300, 400):
        scales[d] = 0.8
    base.set_lat_scales(scales)
    perfil1 = base.braking_profile()
    assert max(abs(a - b) for a, b in zip(perfil0[1500:], perfil1[1500:])) < 1e-9  # lejos de la zona (y de la frenada que llega a ella) no cambia nada
    assert min(perfil1[300:400]) <= min(perfil0[300:400]) + 1e-9
    base.set_lat_scales(None)
    assert base.braking_profile() == perfil0  # volver a None restaura exactamente el perfil original


def test_recomputing_the_profile_after_a_lap_is_fast_enough_for_the_control_loop():
    c = _controlador(profile_peak_min_m=60.0, profile_peak_min_kmh=8.0)
    c.braking_profile()
    c.set_lat_scales([0.95] * len(c.braking_profile()))
    t0 = time.perf_counter()
    c.braking_profile()
    assert time.perf_counter() - t0 < 0.5  # si esto se acerca a 0,5 s, el coche conduciría a ciegas varios metros al cerrar cada vuelta


# --- guardar y cargar el mapa (V88) ---------------------------------------------------------------------------------------------------------------------------------

AHORA = {"rain": 0, "track_c": 16, "ambient_c": 12, "tyre_start_c": 72.0, "compound": "Lisos/Lisos/Lisos/Lisos"}


def _mapa(scales=(1.2, 1.1, 0.9), base=9.5, **cond):
    return {"version": 1, "base_limit": base, "scales": {str(i + 1): v for i, v in enumerate(scales)},
            "conditions": {**AHORA, "tyre_ref_c": 45.0, **cond}, "tyre_by_lap": {"2": 55.0, "3": 49.0, "4": 46.0}}


def _con_mapa(mapa, now=None, **kw) -> Tuple[LatAdapter, Any]:
    ad = _adaptador(**kw)
    ad.load_prior(mapa)
    return ad, ad.start(dict(AHORA, **(now or {})))


def test_without_a_map_start_only_remembers_the_conditions():
    ad = _adaptador()
    assert ad.start(AHORA) is None
    assert ad.start_conditions == AHORA and set(ad.scales.values()) == {1.0}


def test_same_conditions_apply_the_saved_map_as_it_is_and_scales_below_one_are_kept():
    ad, info = _con_mapa(_mapa(), cap_limit=100.0, config=LatAdaptConfig(max_scale=1.3))
    assert info["applied"] and info["mismatch"] == 0.0
    assert [ad.scales[i] for i in (1, 2, 3)] == pytest.approx([1.2, 1.1, 0.9])
    # con el tope de siempre (10 m/s² = ×1,0526) el mapa se recorta a ese tope
    ad, _ = _con_mapa(_mapa())
    assert [ad.scales[i] for i in (1, 2, 3)] == pytest.approx([10.0 / 9.5, 10.0 / 9.5, 0.9])


@pytest.mark.parametrize("delta", [+9.5, -9.5])
def test_a_different_track_temperature_trims_the_margin_the_same_whether_warmer_or_colder(delta):
    ad, info = _con_mapa(_mapa(scales=(1.2, 1.1, 0.9)), now={"track_c": 16 + delta}, cap_limit=100.0, config=LatAdaptConfig(max_scale=1.3))
    assert info["mismatch_track"] == pytest.approx(0.5)  # (9,5 − 4) / 11
    assert [ad.scales[i] for i in (1, 2, 3)] == pytest.approx([1.1, 1.05, 0.9])  # solo se recorta lo que está por encima de 1,0


def test_very_different_conditions_fall_back_to_the_base_limit_and_never_below_the_saved_value():
    ad, info = _con_mapa(_mapa(), now={"track_c": 40}, config=LatAdaptConfig(max_scale=1.3), cap_limit=100.0)
    assert info["mismatch"] == 1.0
    assert [ad.scales[i] for i in (1, 2, 3)] == pytest.approx([1.0, 1.0, 0.9])


def test_tyre_temperature_at_the_start_counts_too():
    ad, info = _con_mapa(_mapa(), now={"tyre_start_c": 72.0 + 20.0}, config=LatAdaptConfig(max_scale=1.3), cap_limit=100.0)
    assert info["mismatch_tyre"] == 1.0 and info["mismatch_track"] == 0.0 and ad.scales[1] == pytest.approx(1.0)


def test_a_map_from_rain_or_another_compound_is_ignored():
    ad, info = _con_mapa(_mapa(), now={"rain": 153})
    assert info["applied"] is False and "lluvia" in info["reason"] and ad.prior is None and set(ad.scales.values()) == {1.0}
    ad, info = _con_mapa(_mapa(), now={"compound": "Lluvia/Lluvia/Lluvia/Lluvia"})
    assert info["applied"] is False and "compuesto" in info["reason"] and ad.prior is None


def test_the_saved_multipliers_are_relative_to_their_own_base_limit_and_clipped_to_the_new_cap():
    # guardado con base 9,5 (×1,2 = 11,4 m/s²); hoy base 12: ese límite es ×0,95 sobre la base nueva
    ad = LatAdapter(ZONAS, base_limit=12.0, track_length=LARGO, cap_limit=100.0, config=LatAdaptConfig(max_scale=1.3))
    ad.load_prior(_mapa(scales=(1.2, 1.0, 1.0)))
    ad.start(AHORA)
    assert ad.scales[1] == pytest.approx(0.95) and ad.scales[2] == pytest.approx(9.5 / 12.0)
    # tope más bajo que el del mapa: se recorta
    ad = _adaptador(cap_limit=10.0)
    ad.load_prior(_mapa(scales=(1.26, 1.0, 1.0)))
    ad.start(AHORA)
    assert ad.limits()[1] <= 10.0 + 1e-9


def test_with_a_loaded_map_the_climb_slows_down_while_the_tyres_do_not_follow_the_saved_temperature_curve():
    igual, _ = _con_mapa(_mapa(scales=(1.0, 1.0, 1.0)))
    _vuelta(igual, 1)
    r = _vuelta(igual, 2, tyre=55.0)  # justo lo guardado para la vuelta 2
    assert r["cond_factor"] == 0.0 and igual.scales[1] == pytest.approx(1.04)
    frio, _ = _con_mapa(_mapa(scales=(1.0, 1.0, 1.0)))
    _vuelta(frio, 1)
    r = _vuelta(frio, 2, tyre=55.0 - 25.0)  # 25 °C más frías: desajuste total
    assert r["cond_factor"] == 1.0 and frio.scales[1] == pytest.approx(1.02) and r["tyre_c"] == pytest.approx(30.0)
    caliente, _ = _con_mapa(_mapa(scales=(1.0, 1.0, 1.0)))
    _vuelta(caliente, 1)
    _vuelta(caliente, 2, tyre=55.0 + 25.0)
    assert caliente.scales[1] == pytest.approx(1.02)  # igual de prudente si están más calientes
    # nunca sube más que el ajuste normal
    sin, _ = _con_mapa(_mapa(scales=(1.0, 1.0, 1.0)))
    _vuelta(sin, 1)
    _vuelta(sin, 2, tyre=55.0 - 10.0)  # parcial: (10 − 5) / 15 = 0,33
    assert 1.02 < sin.scales[1] < 1.04


def test_a_session_without_a_map_ignores_the_tyre_temperature_in_the_decisions():
    ad = _adaptador()
    _vuelta(ad, 1)
    r = _vuelta(ad, 2, tyre=20.0)
    assert r["cond_factor"] is None and ad.scales[1] == pytest.approx(1.04) and ad.tyre_by_lap[2] == pytest.approx(20.0)


def test_fixed_map_measures_but_never_changes_a_multiplier():
    ad, _ = _con_mapa(_mapa(), config=LatAdaptConfig(learn=False))
    antes = dict(ad.scales)
    _vuelta(ad, 1)
    r = _vuelta(ad, 2, cte={1: 2.5}, tyre=55.0)
    assert set(r["decisions"].values()) == {"fijo"} and ad.scales == antes and r["bad"] == [1]


def test_clean_tail_needs_three_laps_and_the_last_two_without_a_curve_going_down():
    ad = _adaptador()
    _vuelta(ad, 1)
    _vuelta(ad, 2)
    _vuelta(ad, 3)
    assert not ad.clean_tail()  # solo 2 cerradas
    _vuelta(ad, 4, cte={2: 2.5})  # una curva baja
    assert not ad.clean_tail()
    _vuelta(ad, 5)
    assert not ad.clean_tail()  # la cuarta fue mala
    _vuelta(ad, 6)
    assert ad.clean_tail()


def test_snapshot_round_trips_through_the_file_and_leaves_no_temporary_file(tmp_path):
    ad = _adaptador()
    ad.start(AHORA)
    for lap in range(1, 6):
        _vuelta(ad, lap, tyre=60.0 - lap)
    destino = tmp_path / "mapas" / "seco.json"
    save_map(destino, ad.snapshot({"experiment": "x"}))
    assert [f.name for f in destino.parent.iterdir()] == ["seco.json"]
    datos = load_map(destino)
    assert datos["clean_tail"] is True and datos["base_limit"] == 9.5 and datos["meta"]["experiment"] == "x"
    assert datos["conditions"]["track_c"] == 16 and datos["conditions"]["tyre_ref_c"] == pytest.approx(56.0)  # media de las 3 últimas vueltas cerradas (3: 57, 4: 56, 5: 55)
    assert datos["scales"]["1"] == pytest.approx(ad.scales[1], abs=1e-4)
    otro = _adaptador()
    otro.load_prior(datos)
    arranque = otro.start(AHORA)
    assert arranque is not None and arranque["applied"] is True and otro.scales[1] == pytest.approx(ad.scales[1], abs=1e-3)


def test_load_map_rejects_a_file_that_is_not_a_map(tmp_path):
    malo = tmp_path / "x.json"
    malo.write_text("{\"hola\": 1}", encoding="utf-8")
    with pytest.raises(ValueError):
        load_map(malo)
