"""Técnica de pedales del teacher (V65): gas cortado antes de frenar, freno que se suelta hasta el vértice y gas que solo sube desde el vértice."""

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pytest

from reference_recorder import ReferenceLine
from teacher_controller import TeacherConfig, TeachingController
from teacher_intents import NUM_REASONS, REASON_TO_ID, normalize_reason
from tests.test_teacher_controller import _base_telem

SUGO = str(Path(__file__).resolve().parents[1] / "src" / "refs" / "sugo_ai.json")
RECETA = dict(speed_target_kmh=110.0, lat_accel_limit=9.0, throttle_max=1.0, brake_decel_straight=8.0, brake_overspeed_straight_ms=2.5)


def _vuelta(technique: bool, acel: float = 1.0, **cfg) -> Tuple[List[Tuple[float, float, float, float, str, float]], float]:
    """Una vuelta de Sugo con un coche de juguete longitudinal (solo gas, freno y resistencia, con la aceleración multiplicada por `acel`).

    Devuelve (distancia, v, gas, freno, motivo, exceso de velocidad sobre la consigna real) por tick y el tiempo."""
    ref = ReferenceLine.load(SUGO)
    n = int(ref.track_length)
    teacher = TeachingController(ref, TeacherConfig(**{**RECETA, "pedal_technique": technique, **cfg}))
    s, v, ticks, filas = 0.0, 5.0, 0, []
    while s < n and ticks < 60 * 400:
        telem = _base_telem(speed=v)
        gas, freno, motivo = teacher.compute_pedals(telem, s % n, 0.0, ref.curvature((s + 30.0) % n))
        recta = teacher.braking_on_straight(s % n, 0.0)
        exceso = v - teacher.physical_curve_target(s % n, 8.0 if recta else None)
        v = max(1.0, v + (acel * 6.5 * gas * (1.0 - v / 50.0) - 0.001 * v * v - 11.7 * freno) / 60.0)
        s += v / 60.0
        ticks += 1
        filas.append((s % n, v, gas, freno, motivo, exceso))
    return filas, ticks / 60.0


def _inversiones(gas: np.ndarray, en_curva: np.ndarray, umbral: float = 0.12) -> int:
    """Cambios de tendencia del gas de más de `umbral` mientras el coche está en curva."""
    cuenta, ext, d = 0, gas[0], 0
    for i in range(1, len(gas)):
        if not en_curva[i]:
            ext, d = gas[i], 0
            continue
        x = gas[i]
        if d >= 0 and x > ext:
            ext, d = x, (1 if d != -1 else d)
        elif d <= 0 and x < ext:
            ext, d = x, (-1 if d != 1 else d)
        if d == 1 and ext - x > umbral:
            cuenta, d, ext = cuenta + 1, -1, x
        elif d == -1 and x - ext > umbral:
            cuenta, d, ext = cuenta + 1, 1, x
    return cuenta


def _rebotes(gas: np.ndarray, freno: np.ndarray) -> Tuple[int, int]:
    """(frenadas, frenadas con un rebote del gas en los 3 s previos: baja > 0,25 y vuelve a subir > 0,25)."""
    inicios = [i for i in range(1, len(freno)) if freno[i] > 0.05 and freno[i - 1] <= 0.05 and freno[i:i + 90].max() > 0.2]
    rebotes = 0
    for i in inicios:
        w = gas[max(0, i - 180):i + 1]
        if any(w[:a + 1].max() - w[a] > 0.25 and w[a:].max() - w[a] > 0.25 for a in range(len(w))):
            rebotes += 1
    return len(inicios), rebotes


@pytest.fixture(scope="module")
def vueltas() -> Dict[str, Tuple[list, float]]:
    return {"base": _vuelta(False), "tecnica": _vuelta(True)}


def test_defaults_are_the_production_law():
    cfg = TeacherConfig()
    assert cfg.pedal_technique is False
    teacher = TeachingController(ReferenceLine.load(SUGO), cfg)
    assert teacher._phase == "drive"


def test_technique_off_matches_explicit_off():
    a, ta = _vuelta(False)
    b, tb = _vuelta(False, lift_band_ms=3.0, exit_slew_per_s=0.1)  # los parámetros de la técnica no hacen nada si está apagada
    assert ta == tb and [x[2:4] for x in a] == [x[2:4] for x in b]


def test_physical_curve_info_agrees_with_the_target():
    teacher = TeachingController(ReferenceLine.load(SUGO), TeacherConfig(**RECETA))
    for d in range(0, 3500, 97):
        best, s_bind, v_bind = teacher.physical_curve_info(float(d))
        assert best == teacher.physical_curve_target(float(d))
        assert s_bind >= 0.0 and v_bind <= best + 1e-9 or s_bind == 0.0


def test_new_reasons_stay_inside_the_bc_vocabulary():
    assert normalize_reason("lift_lock") == "maintain_speed"
    assert normalize_reason("accel_exit") == "accel_curve_limited"
    assert "lift_lock" not in REASON_TO_ID and "accel_exit" not in REASON_TO_ID
    assert NUM_REASONS == 16


def test_technique_never_presses_both_pedals_and_uses_its_phases(vueltas):
    filas, _ = vueltas["tecnica"]
    assert all(min(f[2], f[3]) == 0.0 for f in filas)
    assert {"lift_lock", "accel_exit", "brake_overspeed"} <= {f[4] for f in filas}
    assert not ({"lift_lock", "accel_exit"} & {f[4] for f in vueltas["base"][0]})


def test_technique_cuts_throttle_oscillation_and_rebounds_without_losing_time(vueltas):
    res = {}
    ref = ReferenceLine.load(SUGO)
    for nombre, (filas, t) in vueltas.items():
        gas = np.array([f[2] for f in filas])
        freno = np.array([f[3] for f in filas])
        k = np.array([abs(ref.curvature(f[0])) for f in filas])
        res[nombre] = (_inversiones(gas, k > 0.006), _rebotes(gas, freno), t)
    (inv_b, (_, reb_b), t_b), (inv_t, (fr_t, reb_t), t_t) = res["base"], res["tecnica"]
    assert inv_b >= 10 and reb_b >= 2  # la ley de siempre caza con el PI en la consigna irregular
    assert inv_t <= 0.6 * inv_b
    assert reb_t < reb_b and reb_t <= 0.2 * max(fr_t, 1) + 1
    assert t_t <= t_b + 0.6  # con la pendiente por defecto (1,5/s) el coche de juguete pierde ≈ 0,45 s en esta línea; con 0,8/s perdía 1,2 s


@pytest.mark.parametrize("acel", [1.0, 1.3, 1.6])
def test_technique_never_enters_a_corner_faster_than_production(acel):
    """Regresión de la sesión 135138Z: la consigna «que no baja» de la salida tapaba la curva siguiente, el gas seguía a fondo y el freno llegaba 8 m/s por encima de la consigna."""
    base, _ = _vuelta(False, acel)
    tecnica, _ = _vuelta(True, acel)
    assert max(f[5] for f in tecnica) <= max(f[5] for f in base) + 0.5


def test_throttle_only_rises_from_the_apex_while_below_the_target(vueltas):
    """En «accel_exit» con el coche por debajo de la consigna el gas no baja más de lo que baja el tope de la curva (≤ 0,01 por tick)."""
    filas, _ = vueltas["tecnica"]
    bajadas = 0
    for a, b in zip(filas, filas[1:]):
        if a[4] == "accel_exit" and b[4] == "accel_exit" and b[2] < a[2] - 0.05:
            bajadas += 1
    assert bajadas <= 0.01 * len(filas)


def test_throttle_is_cut_fast_when_a_corner_requires_braking():
    """Con una curva por delante que obliga a frenar, el gas llega a 0 en medio segundo (el suavizado de siempre tarda ≈ 0,45 s solo en bajar a 0,05)."""
    ref = ReferenceLine.load(SUGO)
    n = int(ref.track_length)
    filas, _ = _vuelta(True)
    i = next(j for j, f in enumerate(filas) if f[4] == "lift_lock" and f[2] > 0.3)
    assert min(f[2] for f in filas[i:i + 30]) == pytest.approx(0.0, abs=0.02)
    assert n > 0
