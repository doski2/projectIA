"""Tope del gas en la salida de curva por el círculo de adherencia (V72, F3)."""

from pathlib import Path

import pytest

from reference_recorder import ReferenceLine
from teacher_controller import TeacherConfig, TeachingController, exit_gas_cap
from tests.test_teacher_controller import _base_telem

SUGO = str(Path(__file__).resolve().parents[1] / "src" / "refs" / "sugo_ai.json")
RECETA = dict(speed_target_kmh=110.0, lat_accel_limit=9.0, throttle_max=1.0, brake_decel_straight=8.0, brake_overspeed_straight_ms=2.5, pedal_technique=True)


def _gas_en_la_salida(lateral: float, ticks: int = 150, **cfg) -> float:
    """Gas tras `ticks` ticks en la fase de salida de una curva con el coche por debajo de la consigna y `lateral` m/s² medidos."""
    ref = ReferenceLine.load(SUGO)
    teacher = TeachingController(ref, TeacherConfig(**{**RECETA, **cfg}))
    teacher._phase = "exit"
    teacher._exit_target = 30.0
    telem = _base_telem(speed=18.0)
    telem.local_acceleration = (lateral, 0.0, 0.0)
    gas, motivo = 0.0, ""
    for _ in range(ticks):
        gas, _, motivo = teacher.compute_pedals(telem, 2440.0, 0.0, ref.curvature(2470.0))
    assert motivo == "accel_exit"
    return gas


def test_cap_function_follows_the_friction_circle():
    assert exit_gas_cap(0.0, 14.6, 1.0, 0.3) == 1.0
    assert exit_gas_cap(11.7, 14.6, 1.0, 0.3) == pytest.approx(0.60, abs=0.01)  # la sesión 170252Z salía a 0,93-1,00 con este lateral
    assert exit_gas_cap(14.6, 14.6, 1.0, 0.3) == 0.3 and exit_gas_cap(20.0, 14.6, 1.0, 0.3) == 0.3  # nunca por debajo del gas que mantiene la velocidad
    assert exit_gas_cap(-11.7, 14.6, 1.0, 0.3) == exit_gas_cap(11.7, 14.6, 1.0, 0.3)  # el sentido del giro no importa
    assert exit_gas_cap(11.7, 0.0, 0.85, 0.3) == 0.85  # círculo 0 = sin tope
    caps = [exit_gas_cap(x, 14.6, 1.0, 0.3) for x in (0, 3, 6, 9, 12, 14)]
    assert all(b <= a for a, b in zip(caps, caps[1:]))


def test_exit_throttle_is_held_back_while_the_car_still_turns_and_released_when_it_straightens():
    sin_tope = _gas_en_la_salida(11.7)
    con_tope = _gas_en_la_salida(11.7, exit_circle=14.6)
    recto = _gas_en_la_salida(0.0, exit_circle=14.6)
    assert sin_tope > 0.9  # sin la opción el gas llega a fondo mientras el coche aún gira
    assert con_tope == pytest.approx(0.60, abs=0.03)
    assert recto > 0.9  # con el volante recto el tope no actúa


def test_exit_circle_off_by_default_changes_nothing():
    assert TeacherConfig().exit_circle == 0.0
    assert _gas_en_la_salida(11.7) == _gas_en_la_salida(11.7, exit_circle=0.0) == _gas_en_la_salida(0.0)


def test_cap_follows_the_lateral_acceleration_as_it_falls_through_the_exit():
    ref = ReferenceLine.load(SUGO)
    teacher = TeachingController(ref, TeacherConfig(**{**RECETA, "exit_circle": 14.6}))
    teacher._phase = "exit"
    teacher._exit_target = 30.0
    telem = _base_telem(speed=18.0)
    historia = []
    for lat in [12.0] * 60 + [8.0] * 60 + [3.0] * 80:
        telem.local_acceleration = (lat, 0.0, 0.0)
        historia.append(teacher.compute_pedals(telem, 2440.0, 0.0, ref.curvature(2470.0))[0])
    assert historia[59] <= 0.62 and 0.78 <= historia[119] <= 0.86 and historia[-1] > 0.95  # sube a medida que el coche se endereza
