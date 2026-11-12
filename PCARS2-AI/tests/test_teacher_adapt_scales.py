"""El teacher con los multiplicadores por metro que le pasa el ajuste por curva (`curve_adapt.py`): límite lateral, círculo de gas de salida y deceleración de frenada.

Vienen de `test_lat_adapt.py`, `test_exit_adapt.py` y `test_brake_adapt.py`, retirados con los ajustes antiguos (2026-11-12): lo que comprueban del teacher sigue vigente.
"""

import math
import time
from pathlib import Path

import pytest

from reference_recorder import ReferenceLine
from teacher_controller import TeacherConfig, TeachingController
from tests.test_brake_profile import RECETA
from tests.test_exit_circle import RECETA as RECETA_SALIDA
from tests.test_exit_circle import SUGO as SUGO_SALIDA
from tests.test_teacher_controller import _base_telem

SUGO = str(Path(__file__).resolve().parents[1] / "src" / "refs" / "sugo_ai.json")


# ── límite lateral ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
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


# ── gas de salida ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _teacher_salida(**cfg) -> TeachingController:
    ref = ReferenceLine.load(SUGO_SALIDA)
    t = TeachingController(ref, TeacherConfig(**{**RECETA_SALIDA, "exit_circle": 18.0, **cfg}))
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
    base, _ = _gas(_teacher_salida(), 11.7)
    t = _teacher_salida()
    t.set_exit_scales([1.3] * int(t.ref.track_length))
    mas, _ = _gas(t, 11.7)
    t2 = _teacher_salida()
    t2.set_exit_scales([0.7] * int(t2.ref.track_length))
    menos, _ = _gas(t2, 11.7)
    assert menos < base < mas
    assert base == pytest.approx(math.sqrt(1 - (11.7 / 18.0) ** 2), abs=0.03)
    t2.set_exit_scales(None)
    assert _gas(t2, 11.7)[0] == pytest.approx(base, abs=0.02)  # None = el mismo radio en toda la vuelta


def test_the_scale_is_read_at_the_current_distance_of_the_lap():
    t = _teacher_salida()
    n = int(t.ref.track_length)
    t.set_exit_scales([0.7 if 2400 <= d <= 2500 else 1.0 for d in range(n)])
    assert t._exit_circle_at(2440.4) == pytest.approx(18.0 * 0.7) and t._exit_circle_at(2200.0) == 18.0
    assert t._exit_circle_at(n + 2440.0) == pytest.approx(18.0 * 0.7)  # da la vuelta con el módulo
    dentro, _ = _gas(t, 11.7, d=2440.0)
    t3 = _teacher_salida()
    t3.set_exit_scales([0.7 if 2300 <= d <= 2380 else 1.0 for d in range(n)])  # la zona reducida queda lejos de donde se mide
    fuera, _ = _gas(t3, 11.7, d=2440.0)
    assert dentro < fuera == pytest.approx(_gas(_teacher_salida(), 11.7, d=2440.0)[0], abs=0.02)


def test_exit_bound_is_true_only_while_the_cap_cuts_the_gas_and_the_phase_is_exposed():
    t = _teacher_salida()
    assert t.exit_phase is True and t.phase == "exit"
    _, recorta = _gas(t, 11.7)
    assert recorta is True  # a 11,7 m/s² el tope (0,76) está por debajo de lo que pide el PI
    t2 = _teacher_salida()
    _, recorta2 = _gas(t2, 0.0)
    assert recorta2 is False  # con el coche recto el tope no actúa
    t3 = _teacher_salida(exit_circle=0.0)
    _, recorta3 = _gas(t3, 11.7)
    assert recorta3 is False  # sin --exit-circle no hay tope
    t3._phase = "drive"
    assert t3.exit_phase is False and t3.phase == "drive"


def test_without_exit_scales_the_teacher_is_exactly_the_one_of_before():
    a, b = _teacher_salida(), _teacher_salida()
    b.set_exit_scales([1.0] * int(b.ref.track_length))
    assert _gas(a, 11.7)[0] == _gas(b, 11.7)[0]


# ── frenada ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _teacher_frenada() -> TeachingController:
    return TeachingController(ReferenceLine.load(SUGO), TeacherConfig(**RECETA))


def test_a_lower_deceleration_scale_starts_braking_earlier_and_a_higher_one_later_and_none_changes_nothing():
    t = _teacher_frenada()
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


def test_the_brake_scale_only_changes_the_profile_before_its_own_curve():
    t = _teacher_frenada()
    base = list(t.braking_profile())
    n = len(base)
    t.set_brake_scales([0.6 if 1000 <= d <= 1100 else 1.0 for d in range(n)])
    cambiado = t.braking_profile()
    dif = [d for d in range(n) if abs(cambiado[d] - base[d]) > 1e-9]
    assert dif and all(d <= 1100 or d >= 1100 - 400 for d in dif) and min(dif) < 1100 and all(abs(cambiado[d] - base[d]) < 1e-9 for d in range(1500, 2500))


def test_entry_phase_is_exposed():
    t = _teacher_frenada()
    t._phase = "entry"
    assert t.entry_phase is True and t.phase == "entry"
    t._phase = "exit"
    assert t.entry_phase is False
