"""Recorte de picos cortos de la consigna de velocidad (V79, F13): el coche no acelera en un tramo corto entre dos curvas para frenar enseguida."""

from pathlib import Path
from typing import Dict, List

import pytest

from reference_recorder import ReferenceLine
from teacher_controller import TeacherConfig, TeachingController, open_profile_peaks
from tests.test_brake_profile import RECETA, _metricas, _vuelta

SUGO = str(Path(__file__).resolve().parents[1] / "src" / "refs" / "sugo_ai.json")


def _controlador(**cfg) -> TeachingController:
    return TeachingController(ReferenceLine.load(SUGO), TeacherConfig(**{**RECETA, "pedal_technique": True, "brake_profile": True, **cfg}))


def test_a_peak_narrower_than_the_window_is_flattened_and_a_wide_one_is_kept():
    perfil = [30.0] * 40 + [20.0] + [30.0] * 10 + [20.0] + [30.0] * 80  # pico de 10 m entre dos valles de 1 m, y un tramo ancho de 80 m
    abierto = open_profile_peaks(perfil, 30.0)
    assert all(v == 20.0 for v in abierto[40:52])  # el pico estrecho se aplana al valle de alrededor
    assert abierto[39] == 30.0 and abierto[52] == 30.0  # los flancos de fuera no cambian
    assert abierto[100] == 30.0 and abierto[60] == 30.0  # el tramo ancho no cambia


def test_opening_never_raises_the_profile_and_keeps_its_minimum():
    perfil = [25.0 + 8.0 * ((i * 7919) % 13) / 12.0 for i in range(300)]
    for ancho in (4.0, 10.0, 31.0, 120.0):
        abierto = open_profile_peaks(perfil, ancho)
        assert len(abierto) == len(perfil)
        assert all(a <= p + 1e-12 for a, p in zip(abierto, perfil))
        assert min(abierto) == pytest.approx(min(perfil))


def test_zero_or_negative_width_returns_an_untouched_copy():
    perfil = [30.0, 20.0, 30.0, 25.0]
    for ancho in (0.0, -5.0, 1.0):
        copia = open_profile_peaks(perfil, ancho)
        assert copia == perfil and copia is not perfil


def test_opening_is_circular_a_peak_across_the_start_of_the_lap_is_flattened_too():
    perfil = [30.0] * 4 + [20.0] * 40 + [30.0] * 4  # un único pico de 8 m que pasa por el principio de la vuelta
    abierto = open_profile_peaks(perfil, 20.0)
    assert max(abierto) == 20.0


def test_off_by_default_changes_nothing():
    assert TeacherConfig().profile_peak_min_m == 0.0
    base = _controlador().braking_profile()
    assert base == _controlador(profile_peak_min_m=0.0).braking_profile()


def test_profile_with_the_option_is_never_above_the_normal_one_and_is_lowered_somewhere():
    base = _controlador().braking_profile()
    recortado = _controlador(profile_peak_min_m=60.0).braking_profile()
    assert len(base) == len(recortado)
    assert all(r <= b + 1e-9 for r, b in zip(recortado, base))
    assert sum(1 for r, b in zip(recortado, base) if b - r > 0.5) > 50  # hay picos cortos que recortar en Sugo


def _gas_y_freno_seguidos(res: Dict[str, object]) -> int:
    """Veces que el gas está a fondo (≥ 0,8) y en menos de 1,5 s hay freno (> 0,1): el gas, freno y gas que se quiere evitar."""
    filas: List[tuple] = res["filas"]  # type: ignore[assignment]
    eventos, ult = 0, -1000
    for i, f in enumerate(filas):
        if f[2] >= 0.8 and any(g[3] > 0.1 for g in filas[i + 1:i + 91]) and i - ult > 120:
            eventos += 1
            ult = i
    return eventos


@pytest.fixture(scope="module")
def vueltas() -> Dict[float, Dict[str, Dict[str, object]]]:
    """Vuelta con el coche de juguete sin y con el recorte, a ×1,0 y ×1,6 de aceleración (regla de los cambios de pedales: probar varias aceleraciones)."""
    return {acel: {"base": _vuelta("perfil", acel), "recorte": _vuelta("perfil", acel, profile_peak_min_m=60.0)} for acel in (1.0, 1.6)}


@pytest.mark.parametrize("acel", [1.0, 1.6])
def test_clipping_does_not_enter_any_corner_faster_than_the_braking_capacity(vueltas, acel):
    base, recorte = _metricas(vueltas[acel]["base"]), _metricas(vueltas[acel]["recorte"])
    assert recorte["exceso_max"] <= max(base["exceso_max"], 0.0) + 0.3  # la velocidad de llegada a cada curva no sube


@pytest.mark.parametrize("acel", [1.0, 1.6])
def test_clipping_costs_little_lap_time_and_removes_gas_then_brake(vueltas, acel):
    base, recorte = vueltas[acel]["base"], vueltas[acel]["recorte"]
    assert _metricas(recorte)["tiempo"] <= _metricas(base)["tiempo"] + 0.5  # con 60 m el coste es de décimas
    assert _gas_y_freno_seguidos(recorte) < _gas_y_freno_seguidos(base)
    assert _metricas(recorte)["frenadas"] <= _metricas(base)["frenadas"]
