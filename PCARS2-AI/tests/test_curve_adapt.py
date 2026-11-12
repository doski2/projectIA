"""Ajuste unificado de las curvas (`curve_adapt.py`): atribución por fase, reglas comunes, canales, memoria del último nivel malo y mapas."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from curve_adapt import CurveAdaptConfig, CurveAdapter, Tick, Zone, drift_deg, load_map, save_map

LARGO = 3500.0
ZONAS = [Zone(1, 200.0, 300.0, 250.0), Zone(2, 400.0, 500.0, 450.0), Zone(3, 800.0, 900.0, 850.0)]
BASES = {"lat": 9.5, "exit": 18.0, "brake": 11.0}
RAZON = 0.942
AHORA = {"rain": 0, "track_c": 16, "ambient_c": 12, "tyre_start_c": 72.0, "compound": "Lisos/Lisos/Lisos/Lisos"}


def _ad(channels=None, **cfg) -> CurveAdapter:
    return CurveAdapter(ZONAS, BASES, LARGO, CurveAdaptConfig(**cfg), channels)


def _tick(lap: int, d: float, phase: str = "drive", cte: float = 0.3, deriva: float = 0.0, terreno=(0, 0, 0, 0), gas: float = 0.1, gear: int = 3,
          patinazo: float = 0.0, recorta: bool = True, sobre: float = -0.8, pedal: float = 0.0, limitador: float = 1.0, tyre: Optional[float] = None) -> Tick:
    beta = math.radians(deriva)
    rear = 80.0 * RAZON * (1.0 + patinazo / 100.0)
    return Tick(lap=lap, s=float(d), signed_cte=cte, local_vx=20.0 * math.sin(beta), local_vz=-20.0 * math.cos(beta), terrain=terreno, tyre_c=tyre,
                phase=phase, exit_bound=recorta, gas=gas, gas_req=gas, brake=pedal, limiter_scale=limitador, over_ms=sobre,
                rps=(80.0, 80.0, -rear, -rear), gear=gear, clutch=0, steering=0.0, speed_ms=30.0)


def _vuelta(ad: CurveAdapter, lap: int, lat: Optional[Dict[int, dict]] = None, salida: Optional[Dict[int, dict]] = None,
            frenada: Optional[Dict[int, dict]] = None, tyre: Optional[float] = None) -> Any:
    """Una vuelta entera, un tick cada 2 m. Cada curva: frenada en los 60 m antes de su inicio, paso por curva hasta el vértice y salida desde el vértice
    hasta 15 m después de su final. `lat`, `salida` y `frenada` = {id de curva: argumentos de `_tick`} para los ticks de esa fase. Devuelve el resumen
    del primer tick de la vuelta siguiente."""
    lat, salida, frenada = lat or {}, salida or {}, frenada or {}
    for d in range(0, int(LARGO), 2):
        t = None
        for z in ZONAS:
            if z.s0 - 60 <= d < z.s0:
                t = _tick(lap, d, "entry", **{"pedal": 0.6, "gear": 2, "gas": 0.0, "tyre": tyre, **frenada.get(z.id, {})})
            elif z.s0 <= d < z.apex:
                t = _tick(lap, d, "drive", **{"gear": 2, "gas": 0.2, "tyre": tyre, **lat.get(z.id, {})})
            elif z.apex <= d <= z.s1 + 15:
                t = _tick(lap, d, "exit", **{"gear": 2, "gas": 0.7, "tyre": tyre, **salida.get(z.id, {})})
        ad.observe(t or _tick(lap, d, tyre=tyre))
    return ad.observe(_tick(lap + 1, 0.0))


def _dec(r: Any, curva: int, ch: str) -> str:
    return r["curvas"][str(curva)][ch]["decision"]


# ── atribución ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_each_tick_goes_to_one_channel_by_phase_and_position():
    ad = _ad()
    assert ad.channel_of(_tick(2, 150.0, "entry")) == (1, "brake")
    assert ad.channel_of(_tick(2, 350.0, "entry")) == (2, "brake")
    assert ad.channel_of(_tick(2, 3400.0, "entry")) == (1, "brake")  # la recta de meta prepara C1
    assert ad.channel_of(_tick(2, 220.0, "drive")) == (1, "lat")
    assert ad.channel_of(_tick(2, 230.0, "exit")) == (1, "lat")  # en salida pero antes del vértice: es paso por curva
    assert ad.channel_of(_tick(2, 270.0, "exit")) == (1, "exit")
    assert ad.channel_of(_tick(2, 314.0, "exit")) == (1, "exit")  # hasta la salida + 15 m
    assert ad.channel_of(_tick(2, 1500.0, "drive")) is None
    solo_lat = _ad(channels=["lat"])
    assert solo_lat.channel_of(_tick(2, 270.0, "exit")) is None and solo_lat.channel_of(_tick(2, 150.0, "entry")) is None


def test_a_slide_in_the_exit_lowers_the_gas_and_not_the_lateral_limit():
    ad = _ad()
    _vuelta(ad, 1)
    _vuelta(ad, 2, salida={1: {"deriva": 6.0}})
    r = _vuelta(ad, 3, salida={1: {"deriva": 6.0}})
    assert _dec(r, 1, "exit") == "baja" and _dec(r, 1, "lat") != "baja"
    assert r["curvas"]["1"]["exit"]["veredicto"] == "mala" and "deriva" in r["curvas"]["1"]["exit"]["motivo"]


def test_drift_deg_matches_the_session_summary_formula():
    assert drift_deg(1.0, -20.0) == pytest.approx(2.862, abs=0.01)
    assert drift_deg(5.0, -3.0) == 0.0


# ── reglas ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_first_lap_does_not_count_and_a_curve_needs_two_clean_laps_then_climbs_one_magnitude_per_lap_by_turns():
    ad = _ad()
    assert _vuelta(ad, 1) is None
    r = _vuelta(ad, 2)
    assert {_dec(r, 1, ch) for ch in ("lat", "exit", "brake")} == {"igual"}  # una sola vuelta limpia
    r = _vuelta(ad, 3)
    assert [_dec(r, 1, ch) for ch in ("lat", "exit", "brake")] == ["sube", "turno", "turno"]
    assert ad.state[1]["lat"].value == pytest.approx(9.5 * 1.04)
    r = _vuelta(ad, 4)
    assert [_dec(r, 1, ch) for ch in ("lat", "exit", "brake")] == ["turno", "sube", "turno"]
    r = _vuelta(ad, 5)
    assert [_dec(r, 1, ch) for ch in ("lat", "exit", "brake")] == ["turno", "turno", "sube"]
    assert ad.state[1]["brake"].value == pytest.approx(11.0 * 1.04)
    r = _vuelta(ad, 6)
    assert _dec(r, 1, "lat") == "sube"


def test_one_bad_lap_is_only_a_warning_and_two_of_the_last_three_go_down_and_freeze():
    ad = _ad(channels=["lat"])
    _vuelta(ad, 1)
    _vuelta(ad, 2)
    r = _vuelta(ad, 3, lat={2: {"cte": 2.5}})
    assert _dec(r, 2, "lat") == "aviso" and ad.state[2]["lat"].value == 9.5
    r = _vuelta(ad, 4)
    assert _dec(r, 2, "lat") == "igual"  # la última limpia, pero la anterior mala: no sube
    r = _vuelta(ad, 5, lat={2: {"cte": 2.5}})  # mala, limpia, mala: 2 de 3
    assert _dec(r, 2, "lat") == "baja" and ad.state[2]["lat"].value == pytest.approx(9.5 * 0.94)
    assert ad.state[2]["lat"].last_bad == pytest.approx(9.5) and ad.state[2]["lat"].frozen == 2
    assert r["bajadas"] == ["C2.lat"]
    assert _dec(_vuelta(ad, 6), 2, "lat") == "congelada"
    assert _dec(_vuelta(ad, 7), 2, "lat") == "congelada"


def test_bad_laps_further_apart_than_the_window_never_go_down():
    ad = _ad(channels=["lat"])
    _vuelta(ad, 1)
    for lap in range(2, 12):
        r = _vuelta(ad, lap, lat={2: {"cte": 2.5}} if lap % 3 == 0 else None)
        assert _dec(r, 2, "lat") != "baja"


def test_grass_or_a_big_slide_go_down_at_once():
    for malo in ({"terreno": (7, 0, 7, 0)}, {"deriva": 8.0}):
        ad = _ad(channels=["lat"])
        _vuelta(ad, 1)
        r = _vuelta(ad, 2, lat={1: malo})
        assert _dec(r, 1, "lat") == "baja" and r["curvas"]["1"]["lat"]["veredicto"] == "grave"


def test_kerbs_are_not_off_track_and_their_spin_does_not_count():
    ad = _ad(channels=["exit"])
    _vuelta(ad, 1)
    r = _vuelta(ad, 2, salida={1: {"terreno": (10, 0, 0, 0), "patinazo": 12.0}, 2: {"terreno": (0, 47, 0, 0)}, 3: {"terreno": (0, 0, 49, 25)}})
    for c in ("1", "2", "3"):
        assert r["curvas"][c]["exit"]["veredicto"] == "limpia" and r["curvas"][c]["exit"]["metricas"]["off"] == 0
    assert r["curvas"]["1"]["exit"]["metricas"]["spin_max_pct"] is None
    r = _vuelta(ad, 3, salida={1: {"patinazo": 12.0}})  # el mismo patinazo sin piano sí cuenta
    assert r["curvas"]["1"]["exit"]["veredicto"] == "mala" and r["curvas"]["1"]["exit"]["metricas"]["spin_max_pct"] == pytest.approx(12.0, abs=0.1)


def test_spin_is_calibrated_with_the_free_rolling_ratio_measured_in_the_session():
    ad = _ad(channels=["exit"])
    _vuelta(ad, 1)
    assert ad.free.n >= 50 and ad.free.value == pytest.approx(RAZON)
    r = _vuelta(ad, 2, salida={1: {"patinazo": 4.0}, 2: {"patinazo": 6.0}, 3: {"patinazo": 7.0}})
    assert [r["curvas"][c]["exit"]["veredicto"] for c in ("1", "2", "3")] == ["limpia", "media", "mala"]
    assert r["razon_libre"] == pytest.approx(RAZON, abs=1e-4)


def test_exit_does_not_count_as_clean_when_the_cap_does_not_cut_the_gas():
    ad = _ad(channels=["exit"])
    _vuelta(ad, 1)
    r = _vuelta(ad, 2, salida={1: {"recorta": False}})
    assert r["curvas"]["1"]["exit"]["veredicto"] == "media" and "tope" in r["curvas"]["1"]["exit"]["motivo"]


def test_braking_rules_are_the_old_ones():
    ad = _ad(channels=["brake"])
    _vuelta(ad, 1)
    r = _vuelta(ad, 2, frenada={1: {"sobre": 1.6}, 2: {"pedal": 0.97}, 3: {"limitador": 0.4}})
    assert [r["curvas"][c]["brake"]["veredicto"] for c in ("1", "2", "3")] == ["mala", "media", "media"]
    r = _vuelta(ad, 3, frenada={1: {"sobre": 0.3, "limitador": 0.25, "pedal": 0.95}})  # el limitador solo no es motivo de frenar menos
    assert r["curvas"]["1"]["brake"]["veredicto"] == "media"
    m = r["curvas"]["1"]["brake"]["metricas"]
    assert m["limiter_min"] == 0.25 and m["pedal_max"] == 0.95 and m["release_over_ms"] == pytest.approx(0.3)


def test_only_the_last_braking_ticks_give_the_release_speed():
    ad = _ad(channels=["brake"])
    _vuelta(ad, 1)
    for d in range(0, int(LARGO), 5):
        ad.observe(_tick(2, d, "entry" if 140 <= d < 200 else "drive", pedal=0.7 if 140 <= d < 200 else 0.0, sobre=4.0 if d < 175 else 0.2))
    r = ad.observe(_tick(3, 0.0))
    assert r is not None
    m = r["curvas"]["1"]["brake"]["metricas"]
    assert m["release_over_ms"] == pytest.approx(0.2) and m["over_max_ms"] == pytest.approx(4.0)


def test_the_climb_approaches_the_last_bad_level_in_halves_stops_at_the_limit_and_reprobes_later():
    ad = _ad(channels=["lat"])
    st = ad.state[1]["lat"]
    st.value, st.last_bad = 10.0, 10.5
    _vuelta(ad, 1)
    _vuelta(ad, 2)
    seq = []
    for lap in range(3, 7):
        r = _vuelta(ad, lap)
        seq.append((_dec(r, 1, "lat"), round(st.value, 4)))
    assert seq == [("sube", 10.25), ("sube", 10.375), ("sube", 10.4375), ("limite", 10.4375)]
    for lap in range(7, 12):
        assert _dec(_vuelta(ad, lap), 1, "lat") == "limite"
    assert st.last_bad is None  # 6 vueltas seguidas limpias en el límite: se olvida y se vuelve a probar
    _vuelta(ad, 12)
    assert st.value == pytest.approx(10.4375 * 1.04)


def test_own_cap_is_reported_as_tope_and_values_stay_inside_the_absolute_bounds():
    ad = _ad(channels=["lat"])
    ad.state[1]["lat"].value = 14.4
    _vuelta(ad, 1)
    _vuelta(ad, 2)
    r = _vuelta(ad, 3)
    assert _dec(r, 1, "lat") == "sube" and ad.state[1]["lat"].value == pytest.approx(14.6)
    assert _dec(_vuelta(ad, 4), 1, "lat") == "tope"
    ad2 = _ad(channels=["lat"])
    _vuelta(ad2, 1)
    for lap in range(2, 40):
        _vuelta(ad2, lap, lat={2: {"terreno": (7, 0, 7, 0)}})
    assert ad2.state[2]["lat"].value == pytest.approx(8.0)


def test_fixed_map_measures_but_never_changes_a_value_and_incomplete_laps_are_ignored():
    ad = _ad(learn=False)
    _vuelta(ad, 1)
    r = _vuelta(ad, 2, lat={1: {"terreno": (7, 0, 7, 0)}})
    assert _dec(r, 1, "lat") == "fijo" and r["curvas"]["1"]["lat"]["veredicto"] == "grave" and ad.state[1]["lat"].value == 9.5
    ad2 = _ad()
    _vuelta(ad2, 1)
    for d in range(0, 1000, 5):
        ad2.observe(_tick(2, d, cte=3.0))
    assert ad2.observe(_tick(3, 0.0)) is None


def test_scales_per_metre_for_the_teacher_are_value_over_base():
    ad = _ad()
    ad.state[2]["lat"].value = 9.5 * 0.9
    ad.state[1]["brake"].value = 11.0 * 1.1
    lat = ad.scales_per_m("lat")
    assert len(lat) == int(LARGO) and lat[450] == pytest.approx(0.9) and lat[514] == pytest.approx(0.9) and lat[520] == 1.0 and lat[100] == 1.0
    brake = ad.scales_per_m("brake")
    assert brake[250] == pytest.approx(1.1) == brake[3400] and brake[450] == 1.0


def test_clean_tail_needs_three_laps_and_no_going_down_in_the_last_two():
    ad = _ad(channels=["lat"])
    _vuelta(ad, 1)
    for lap in (2, 3):
        _vuelta(ad, lap)
    assert not ad.clean_tail()
    _vuelta(ad, 4, lat={2: {"terreno": (7, 0, 7, 0)}})
    assert not ad.clean_tail()
    _vuelta(ad, 5)
    assert not ad.clean_tail()
    _vuelta(ad, 6)
    assert ad.clean_tail()


def test_constructor_checks_channels_and_bases():
    with pytest.raises(ValueError):
        CurveAdapter(ZONAS, BASES, LARGO, channels=["gas"])
    with pytest.raises(ValueError):
        CurveAdapter(ZONAS, {"lat": 9.5}, LARGO, channels=["lat", "exit"])
    assert CurveAdapter(ZONAS, {"lat": 9.5}, LARGO, channels=["lat"]).channels == ("lat",)


# ── mapas y condiciones ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _v1(scales=(1.2, 1.1, 0.9), base=9.5, **cond) -> dict:
    return {"version": 1, "base_limit": base, "scales": {str(i + 1): v for i, v in enumerate(scales)},
            "conditions": {**AHORA, "tyre_ref_c": 45.0, **cond}, "tyre_by_lap": {"2": 55.0, "3": 49.0, "4": 46.0}}


def test_format_1_maps_load_per_channel_as_absolute_values():
    ad = _ad()
    ad.load_prior(_v1(), "lat")
    ad.load_prior(_v1(scales=(1.3, 1.0, 0.85), base=18.0), "exit")
    info = ad.start(AHORA)
    assert info is not None and info["applied"] and info["mismatch"] == 0.0
    assert [ad.state[i]["lat"].value for i in (1, 2, 3)] == pytest.approx([11.4, 10.45, 8.55])
    assert [ad.state[i]["exit"].value for i in (1, 2, 3)] == pytest.approx([23.4, 18.0, 15.3])
    assert ad.state[1]["brake"].value == 11.0  # sin mapa de frenada, la base
    with pytest.raises(ValueError):
        ad.load_prior(_v1())  # un mapa de formato 1 necesita su canal


@pytest.mark.parametrize("delta", [+9.5, -9.5])
def test_other_track_temperature_trims_only_what_is_above_the_base_whether_warmer_or_colder(delta):
    ad = _ad()
    ad.load_prior(_v1(), "lat")
    info = ad.start(dict(AHORA, track_c=16 + delta))
    assert info is not None and info["mismatch_track"] == pytest.approx(0.5)
    assert [ad.state[i]["lat"].value for i in (1, 2, 3)] == pytest.approx([10.45, 9.975, 8.55])


def test_a_map_from_rain_or_another_compound_is_ignored():
    ad = _ad()
    ad.load_prior(_v1(), "lat")
    info = ad.start(dict(AHORA, rain=153))
    assert info is not None and info["applied"] is False and "lluvia" in info["reason"] and ad.state[1]["lat"].value == 9.5
    ad = _ad()
    ad.load_prior(_v1(), "lat")
    info = ad.start(dict(AHORA, compound="Lluvia/Lluvia/Lluvia/Lluvia"))
    assert info is not None and info["applied"] is False and "compuesto" in info["reason"]


def test_with_a_loaded_map_the_climb_slows_down_while_the_tyres_do_not_follow_the_saved_curve():
    def climb(delta):
        ad = _ad(channels=["lat"])
        ad.load_prior(_v1(scales=(1.0, 1.0, 1.0)), "lat")
        ad.start(AHORA)
        _vuelta(ad, 1)
        _vuelta(ad, 2, tyre=55.0 + delta)  # lo guardado: 55 °C en la vuelta 2 y 49 en la 3
        _vuelta(ad, 3, tyre=49.0 + delta)
        return ad.state[1]["lat"].value / 9.5
    assert climb(0.0) == pytest.approx(1.04)
    assert climb(-25.0) == pytest.approx(1.02)  # 25 °C más frías: desajuste total, la mitad de la subida
    assert climb(+25.0) == pytest.approx(1.02)  # igual de prudente si están más calientes


def test_format_2_round_trip_keeps_values_memory_setup_and_ratio(tmp_path: Path):
    reglaje = {"diferencial_deg": 60, "frenos": "55/45", "tc_pct": 10, "abs_pct": 75, "gasolina_l": 12}
    ad = _ad()
    ad.start(AHORA, setup=reglaje)
    ad.state[3]["exit"].value, ad.state[3]["exit"].last_bad = 16.0, 17.0
    for lap in range(1, 6):
        _vuelta(ad, lap, tyre=60.0 - lap)
    destino = tmp_path / "mapas" / "seco.json"
    save_map(destino, ad.snapshot({"experiment": "x"}))
    assert [f.name for f in destino.parent.iterdir()] == ["seco.json"]
    datos = load_map(destino)
    assert datos["version"] == 2 and datos["reglaje"] == reglaje and datos["razon_libre"] == pytest.approx(RAZON, abs=1e-4)
    assert datos["curvas"]["3"]["exit"]["ultimo_malo"] == pytest.approx(17.0) and datos["conditions"]["tyre_ref_c"] == pytest.approx(56.0)
    mismo = _ad()
    mismo.load_prior(datos)
    info = mismo.start(AHORA, setup=reglaje)
    assert info is not None and info["applied"] and info["memoria"] is True
    assert mismo.state[3]["exit"].last_bad == pytest.approx(17.0) and mismo.state[1]["lat"].value == pytest.approx(ad.state[1]["lat"].value, abs=1e-3)
    otro = _ad()
    otro.load_prior(datos)
    info = otro.start(AHORA, setup={**reglaje, "diferencial_deg": 45})
    assert info is not None and info["reglaje_distinto"] and info["memoria"] is False and otro.state[3]["exit"].last_bad is None
    frio = _ad()
    frio.load_prior(datos)
    frio.start(dict(AHORA, track_c=4), setup=reglaje)
    assert frio.state[3]["exit"].last_bad is None  # con otras condiciones la memoria no vale


def test_load_map_rejects_a_file_that_is_not_a_map(tmp_path: Path):
    malo = tmp_path / "x.json"
    malo.write_text("{\"hola\": 1}", encoding="utf-8")
    with pytest.raises(ValueError):
        load_map(malo)


def test_one_wheel_brushing_the_grass_is_only_recorded_and_two_wheels_off_need_a_few_ticks():
    ad = _ad(channels=["lat"])
    _vuelta(ad, 1)
    r = _vuelta(ad, 2, lat={1: {"terreno": (7, 0, 10, 0)}, 2: {"terreno": (7, 0, 8, 0)}})
    assert r["curvas"]["1"]["lat"]["veredicto"] == "limpia" and r["curvas"]["1"]["lat"]["metricas"]["una_rueda_fuera"] > 0
    assert r["curvas"]["2"]["lat"]["veredicto"] == "mala" and "2 ruedas fuera" in r["curvas"]["2"]["lat"]["motivo"]
    ad2 = _ad(channels=["lat"])
    _vuelta(ad2, 1)
    for d in range(0, int(LARGO), 2):  # dos ruedas en la grava solo 2 ticks: no basta
        ad2.observe(_tick(2, d, terreno=(8, 0, 8, 0) if d in (210, 212) else (0, 0, 0, 0)))
    r2 = ad2.observe(_tick(3, 0.0))
    assert r2 is not None and r2["curvas"]["1"]["lat"]["veredicto"] != "mala"
