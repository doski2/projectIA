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


# ---- umbral de prominencia (V81): el recorte no toca los picos pequeños ----

def test_prominence_threshold_flattens_only_the_peaks_that_drop_enough():
    # dos valles de 20 y dos picos estrechos entre ellos: uno de 1 m/s sobre el valle (10 m de ancho) y otro de 10 m/s (10 m de ancho)
    perfil = [30.0] * 40 + [20.0] + [21.0] * 10 + [20.0] + [30.0] * 30 + [20.0] + [30.0] * 10 + [20.0] + [30.0] * 40
    todo = open_profile_peaks(perfil, 30.0)
    solo_grande = open_profile_peaks(perfil, 30.0, min_drop_ms=3.0)
    assert max(todo[42:51]) == 20.0  # sin umbral se aplanan los dos
    assert all(a == b for a, b in zip(solo_grande[42:51], perfil[42:51]))  # con umbral, el pequeño queda como estaba
    i_grande = 40 + 1 + 10 + 1 + 30 + 1  # primer metro del pico grande
    assert all(v == 20.0 for v in solo_grande[i_grande + 1:i_grande + 9])  # y el grande sigue aplanado


def test_prominence_zero_is_the_plain_opening_and_a_huge_threshold_changes_nothing():
    perfil = [25.0 + 8.0 * ((i * 7919) % 13) / 12.0 for i in range(300)]
    assert open_profile_peaks(perfil, 31.0, 0.0) == open_profile_peaks(perfil, 31.0)
    assert open_profile_peaks(perfil, 31.0, 1e6) == perfil


def test_prominence_threshold_never_raises_the_profile_and_keeps_the_ones_that_were_clipped_by_more():
    perfil = [25.0 + 8.0 * ((i * 7919) % 13) / 12.0 for i in range(300)]
    pleno = open_profile_peaks(perfil, 31.0)
    for umbral in (0.5, 2.0, 5.0):
        parcial = open_profile_peaks(perfil, 31.0, umbral)
        assert all(pleno[i] - 1e-12 <= parcial[i] <= perfil[i] + 1e-12 for i in range(300))  # entre el recorte pleno y el perfil original
        assert all(parcial[i] == perfil[i] or parcial[i] == pleno[i] for i in range(300))  # cada metro o se deja o se recorta del todo


def test_prominence_threshold_works_across_the_start_of_the_lap():
    perfil = [30.0] * 6 + [20.0] * 40 + [30.0] * 6 + [24.0] * 40  # el pico de 12 m pasa por el principio de la vuelta
    assert max(open_profile_peaks(perfil, 20.0, min_drop_ms=5.0)[:6]) == 24.0  # 6 m/s de caída ≥ 5: se aplana
    assert open_profile_peaks(perfil, 20.0, min_drop_ms=8.0)[:6] == [30.0] * 6  # < 8: se queda


def test_prominence_is_off_by_default_and_a_huge_one_gives_the_base_profile():
    assert TeacherConfig().profile_peak_min_kmh == 0.0
    base = _controlador().braking_profile()
    assert _controlador(profile_peak_min_m=60.0, profile_peak_min_kmh=0.0).braking_profile() == _controlador(profile_peak_min_m=60.0).braking_profile()
    assert _controlador(profile_peak_min_m=60.0, profile_peak_min_kmh=1000.0).braking_profile() == base


def test_profile_with_prominence_lies_between_the_base_and_the_full_clipping():
    base = _controlador().braking_profile()
    pleno = _controlador(profile_peak_min_m=60.0).braking_profile()
    parcial = _controlador(profile_peak_min_m=60.0, profile_peak_min_kmh=8.0).braking_profile()
    assert all(p - 1e-9 <= q <= b + 1e-9 for p, q, b in zip(pleno, parcial, base))  # el barrido hacia atrás es monótono
    n_parcial = sum(1 for q, b in zip(parcial, base) if b - q > 0.5)
    n_pleno = sum(1 for p, b in zip(pleno, base) if b - p > 0.5)
    assert 0 < n_parcial < n_pleno  # recorta los picos grandes y deja los pequeños


@pytest.mark.parametrize("acel", [1.0, 1.6])
def test_clipping_with_prominence_keeps_the_gains_and_does_not_enter_corners_faster(vueltas, acel):
    base = vueltas[acel]["base"]
    parcial = _vuelta("perfil", acel, profile_peak_min_m=60.0, profile_peak_min_kmh=8.0)
    assert _metricas(parcial)["exceso_max"] <= max(_metricas(base)["exceso_max"], 0.0) + 0.3
    assert _metricas(parcial)["tiempo"] <= _metricas(base)["tiempo"] + 0.5
    assert _gas_y_freno_seguidos(parcial) < _gas_y_freno_seguidos(base)
    assert _metricas(parcial)["frenadas"] <= _metricas(base)["frenadas"]
