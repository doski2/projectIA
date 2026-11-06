"""Gas de salida por curva que se ajusta vuelta a vuelta (`--exit-adapt`, exit_adapt.py) y su efecto en el tope del teacher."""

import math
from pathlib import Path
from typing import Any

import pytest

from exit_adapt import ExitAdaptConfig, ExitAdapter
from lat_adapt import Zone, load_map, save_map
from reference_recorder import ReferenceLine
from teacher_controller import TeacherConfig, TeachingController
from tests.test_exit_circle import RECETA, SUGO
from tests.test_teacher_controller import _base_telem

LARGO = 3500.0
ZONAS = [Zone(1, 200.0, 300.0), Zone(2, 400.0, 500.0), Zone(3, 800.0, 900.0)]
RADIO = 18.0


def _adaptador(**kw) -> ExitAdapter:
    return ExitAdapter(ZONAS, base_limit=RADIO, track_length=LARGO, **kw)


def _vuelta(ad: ExitAdapter, lap: int, razon=None, deriva=None, cte=None, fuera=None, recorta=None, salida=None, gas: float = 0.7) -> Any:
    """Alimenta una vuelta entera (un tick cada 5 m; dentro de cada curva, todos de salida). Los dicts van por id de curva: `razon` (traseras / delanteras), `deriva` en grados,
    `cte`, `fuera`, `recorta` (si el tope recortaba el gas; por defecto sí) y `salida` (si hay fase de salida; por defecto sí). Devuelve el resumen del primer tick de la vuelta siguiente."""
    razon, deriva, cte, fuera, recorta, salida = razon or {}, deriva or {}, cte or {}, fuera or {}, recorta or {}, salida or {}
    for d in range(0, int(LARGO), 5):
        zona = next((z for z in ZONAS if z.s0 <= d <= z.s1), None)
        zid = zona.id if zona else 0
        beta = math.radians(deriva.get(zid, 0.0))
        ad.observe(lap, float(d), cte.get(zid, 0.3), 20.0 * math.sin(beta), -20.0 * math.cos(beta), bool(fuera.get(zid, False)), tyre_c=None,
                   exit_phase=bool(zona) and salida.get(zid, True), cap_bound=recorta.get(zid, True), throttle=gas, rps_front=80.0, rps_rear=80.0 * razon.get(zid, 0.97))
    return ad.observe(lap + 1, 0.0, 0.0, 0.0, -20.0, False)


def test_a_clean_exit_where_the_cap_binds_goes_up_and_the_cap_of_the_circle_is_the_limit():
    ad = _adaptador()
    r = _vuelta(ad, 2)
    assert r["decisions"] == {"1": "sube", "2": "sube", "3": "sube"} and ad.scales[1] == pytest.approx(1.04)
    for lap in range(3, 12):
        _vuelta(ad, lap)
    assert ad.scales[2] == pytest.approx(1.3)  # tope del multiplicador
    assert ad.limits()[2] == pytest.approx(RADIO * 1.3, abs=0.01)  # el radio resultante, en las unidades de --exit-circle


def test_rear_spin_or_a_slide_or_a_wide_exit_or_a_wheel_off_goes_down_and_freezes_two_laps():
    for malo in ({"razon": {1: 1.02}}, {"deriva": {1: 6.0}}, {"cte": {1: 2.3}}, {"fuera": {1: True}}):
        ad = _adaptador()
        r = _vuelta(ad, 2, **malo)
        assert r["decisions"]["1"] == "baja" and ad.scales[1] == pytest.approx(0.92) and r["bad"] == [1]
        assert r["decisions"]["2"] == "sube"  # las demás curvas no se tocan
        assert _vuelta(ad, 3)["decisions"]["1"] == "congelada"
        assert _vuelta(ad, 4)["decisions"]["1"] == "congelada"
        assert _vuelta(ad, 5)["decisions"]["1"] == "sube"


def test_it_does_not_climb_when_the_cap_barely_cuts_the_gas_or_the_margin_is_small():
    ad = _adaptador()
    r = _vuelta(ad, 2, recorta={1: False}, razon={2: 0.995}, cte={3: 1.8})
    assert r["decisions"] == {"1": "igual", "2": "igual", "3": "igual"}  # sin recorte, sin margen en la razón y con |CTE| entre 1,6 y 2,0 m
    assert all(v == 1.0 for v in ad.scales.values())


def test_a_curve_without_exit_ticks_is_not_judged_and_ticks_outside_the_exit_phase_do_not_count():
    ad = _adaptador()
    r = _vuelta(ad, 2, salida={2: False}, deriva={2: 9.0})  # la deriva de C2 ocurre fuera de la fase de salida (entrada o frenada): no se mide
    assert r["decisions"]["2"] == "sin datos" and r["bad"] == [] and ad.scales[2] == 1.0
    assert r["metrics"]["2"]["exit_ticks"] == 0 and r["metrics"]["1"]["exit_ticks"] > 0


def test_spin_is_only_measured_with_gas_and_a_moving_car():
    ad = _adaptador()
    r = _vuelta(ad, 2, razon={1: 1.1}, gas=0.2)  # con el gas por debajo de 0,3 la razón no cuenta
    assert r["decisions"]["1"] == "sube" and r["metrics"]["1"]["spin_max"] == 0.0
    ad2 = _adaptador()
    for d in range(0, int(LARGO), 5):
        ad2.observe(2, float(d), 0.3, 0.0, -20.0, False, exit_phase=True, cap_bound=True, throttle=0.8, rps_front=2.0, rps_rear=3.0)  # casi parado
    assert ad2.observe(3, 0.0, 0.0, 0.0, -20.0, False)["metrics"]["1"]["spin_max"] == 0.0


def test_fixed_map_measures_and_logs_but_changes_nothing_and_the_first_lap_does_not_count():
    ad = _adaptador(config=ExitAdaptConfig(learn=False))
    assert _vuelta(ad, 1) is None  # la vuelta 1 lleva la salida parada
    r = _vuelta(ad, 2, razon={1: 1.05})
    assert set(r["decisions"].values()) == {"fijo"} and all(v == 1.0 for v in ad.scales.values())
    assert r["metrics"]["1"]["spin_max"] == pytest.approx(1.05, abs=0.001)  # se mide y se registra aunque no cambie nada


def test_scales_per_metre_and_the_saved_map_keep_the_circle_and_cut_the_margin_with_other_conditions(tmp_path: Path):
    ad = _adaptador()
    for lap in range(2, 6):
        _vuelta(ad, lap)
    per_m = ad.scales_per_m(int(LARGO))
    assert len(per_m) == int(LARGO) and per_m[250] == ad.scales[1] and per_m[1500] == 1.0
    ad.start({"rain": 0, "track_c": 21, "ambient_c": 14, "tyre_start_c": 84.0, "compound": "Lisos"})
    ruta = tmp_path / "mapa_salida.json"
    save_map(ruta, ad.snapshot({"experiment": "x"}))
    datos = load_map(ruta)
    assert datos["base_limit"] == RADIO and datos["scales"]["1"] == pytest.approx(ad.scales[1], abs=1e-3)
    mismo = _adaptador()
    mismo.load_prior(load_map(ruta))
    assert mismo.start({"rain": 0, "track_c": 21, "ambient_c": 14, "tyre_start_c": 84.0, "compound": "Lisos"})["applied"] and mismo.scales[1] == pytest.approx(ad.scales[1], abs=1e-3)
    frio = _adaptador()
    frio.load_prior(load_map(ruta))
    frio.start({"rain": 0, "track_c": 9, "ambient_c": 5, "tyre_start_c": 84.0, "compound": "Lisos"})
    assert 1.0 < frio.scales[1] < ad.scales[1]  # con otra pista el margen sobre 1,0 se recorta
    mayor = ExitAdapter(ZONAS, base_limit=22.0, track_length=LARGO)  # otro --exit-circle: el mapa conserva el radio absoluto de cada curva
    mayor.load_prior(load_map(ruta))
    mayor.start({"rain": 0, "track_c": 21, "ambient_c": 14, "tyre_start_c": 84.0, "compound": "Lisos"})
    assert mayor.scales[1] * 22.0 == pytest.approx(ad.scales[1] * RADIO, rel=0.001)
    menor = ExitAdapter(ZONAS, base_limit=14.6, track_length=LARGO)
    menor.load_prior(load_map(ruta))
    menor.start({"rain": 0, "track_c": 21, "ambient_c": 14, "tyre_start_c": 84.0, "compound": "Lisos"})
    assert menor.scales[1] == pytest.approx(1.3)  # y lo que pasa del tope de multiplicador se queda en el tope


def test_the_adapter_needs_its_own_config():
    from lat_adapt import LatAdaptConfig

    with pytest.raises(TypeError):
        ExitAdapter(ZONAS, base_limit=RADIO, track_length=LARGO, config=LatAdaptConfig())


# ── el teacher: radio por metro y señal de «el tope está recortando» ─────────────────────────────────────────────────────────────────────────────────────────
def _teacher(**cfg) -> TeachingController:
    ref = ReferenceLine.load(SUGO)
    t = TeachingController(ref, TeacherConfig(**{**RECETA, "exit_circle": 18.0, **cfg}))
    t._phase = "exit"
    t._exit_target = 30.0
    return t


def _gas(t: TeachingController, lateral: float, d: float = 2440.0, ticks: int = 150):
    telem = _base_telem(speed=18.0)
    telem.local_acceleration = (lateral, 0.0, 0.0)
    gas, motivo = 0.0, ""
    for _ in range(ticks):
        gas, _, motivo = t.compute_pedals(telem, d, 0.0, t.ref.curvature(d + 30.0))
    assert motivo == "accel_exit"
    return gas, t.exit_bound


def test_a_bigger_circle_scale_lets_more_gas_through_and_a_smaller_one_less():
    base, _ = _gas(_teacher(), 11.7)
    t = _teacher()
    t.set_exit_scales([1.3] * int(t.ref.track_length))
    mas, _ = _gas(t, 11.7)
    t2 = _teacher()
    t2.set_exit_scales([0.7] * int(t2.ref.track_length))
    menos, _ = _gas(t2, 11.7)
    assert menos < base < mas
    assert base == pytest.approx(math.sqrt(1 - (11.7 / 18.0) ** 2), abs=0.03)
    t2.set_exit_scales(None)
    assert _gas(t2, 11.7)[0] == pytest.approx(base, abs=0.02)  # None = el mismo radio en toda la vuelta


def test_the_scale_is_read_at_the_current_distance_of_the_lap():
    t = _teacher()
    n = int(t.ref.track_length)
    t.set_exit_scales([0.7 if 2400 <= d <= 2500 else 1.0 for d in range(n)])
    assert t._exit_circle_at(2440.4) == pytest.approx(18.0 * 0.7) and t._exit_circle_at(2200.0) == 18.0
    assert t._exit_circle_at(n + 2440.0) == pytest.approx(18.0 * 0.7)  # da la vuelta con el módulo
    dentro, _ = _gas(t, 11.7, d=2440.0)
    t3 = _teacher()
    t3.set_exit_scales([0.7 if 2300 <= d <= 2380 else 1.0 for d in range(n)])  # la zona reducida queda lejos de donde se mide
    fuera, _ = _gas(t3, 11.7, d=2440.0)
    assert dentro < fuera == pytest.approx(_gas(_teacher(), 11.7, d=2440.0)[0], abs=0.02)


def test_exit_bound_is_true_only_while_the_cap_cuts_the_gas_and_the_phase_is_exposed():
    t = _teacher()
    assert t.exit_phase is True
    _, recorta = _gas(t, 11.7)
    assert recorta is True  # a 11,7 m/s² el tope (0,76) está por debajo de lo que pide el PI
    t2 = _teacher()
    _, recorta2 = _gas(t2, 0.0)
    assert recorta2 is False  # con el coche recto el tope no actúa
    t3 = _teacher(exit_circle=0.0)
    _, recorta3 = _gas(t3, 11.7)
    assert recorta3 is False  # sin --exit-circle no hay tope
    t3._phase = "drive"
    assert t3.exit_phase is False


def test_without_scales_the_teacher_is_exactly_the_one_of_before():
    a, b = _teacher(), _teacher()
    b.set_exit_scales([1.0] * int(b.ref.track_length))
    assert _gas(a, 11.7)[0] == _gas(b, 11.7)[0]
