"""Frenada de entrada con perfil continuo (V68, F1): consigna sin saltos con el presupuesto del círculo de adherencia y freno por avance sin margen."""

import math
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pytest

from reference_recorder import ReferenceLine
from teacher_controller import PEDAL_DECEL_TABLE, TeacherConfig, TeachingController, pedal_for_decel
from tests.test_teacher_controller import _base_telem

SUGO = str(Path(__file__).resolve().parents[1] / "src" / "refs" / "sugo_ai.json")
RECETA = dict(speed_target_kmh=110.0, lat_accel_limit=9.0, throttle_max=1.0, brake_decel_straight=8.0, brake_overspeed_straight_ms=2.5)
PEDALES = [p for _, p in PEDAL_DECEL_TABLE]
DECELS = [d for d, _ in PEDAL_DECEL_TABLE]
CAPACIDAD = 11.65  # m/s² con el pedal 0,85 (V55)


def _teacher(**cfg) -> TeachingController:
    return TeachingController(ReferenceLine.load(SUGO), TeacherConfig(**{**RECETA, **cfg}))


def _vuelta(modo: str, acel: float = 1.0, **cfg) -> Dict[str, object]:
    """Una vuelta de Sugo con un coche de juguete longitudinal cuya deceleración sale de la tabla pedal ↔ deceleración medida (`modo`: base, tecnica o perfil)."""
    extra = {"base": {}, "tecnica": {"pedal_technique": True}, "perfil": {"pedal_technique": True, "brake_profile": True}}[modo]
    ref = ReferenceLine.load(SUGO)
    n = int(ref.track_length)
    teacher = TeachingController(ref, TeacherConfig(**{**RECETA, **extra, **cfg}))
    s, v, ticks, filas = 0.0, 5.0, 0, []
    while s < n and ticks < 60 * 400:
        gas, freno, motivo = teacher.compute_pedals(_base_telem(speed=v), s % n, 0.0, ref.curvature((s + 30.0) % n))
        dec = float(np.interp(freno, PEDALES, DECELS))
        kappa = abs(ref.curvature(s % n))
        # exceso sobre lo que permitiría la capacidad real de frenada hasta cada límite lateral de la curva (en 150 m)
        limites = teacher._vlim_cache.get(9.0) or teacher._lateral_speed_limits()
        factible = min(math.sqrt(limites[int(s + d) % n] ** 2 + 2.0 * CAPACIDAD * d) for d in range(0, 150, 5))
        filas.append((s % n, v, gas, freno, motivo, v - factible, v * v * kappa, dec))
        v = max(1.0, v + (acel * 6.5 * gas * (1.0 - v / 50.0) - 0.001 * v * v - dec) / 60.0)
        s += v / 60.0
        ticks += 1
    return {"filas": filas, "tiempo": ticks / 60.0}


def _metricas(res: Dict[str, object]) -> Dict[str, float]:
    filas: List[Tuple] = res["filas"]  # type: ignore[assignment]
    gas = np.array([f[2] for f in filas])
    freno = np.array([f[3] for f in filas])
    lat = np.array([f[6] for f in filas])
    dec = np.array([f[7] for f in filas])
    v = np.array([f[1] for f in filas])
    inicios = [i for i in range(1, len(freno)) if freno[i] > 0.05 and freno[i - 1] <= 0.05 and freno[i:i + 90].max() > 0.2]
    muertos = []
    for i in inicios:
        j = i - 1
        while j > 0 and gas[j] <= 0.05 and freno[j] <= 0.05:
            j -= 1
        muertos.append((i - 1 - j) / 60.0)
    e = np.maximum(v[:-1] ** 2 - v[1:] ** 2, 0.0) * (freno[:-1] > 0.03)
    return {
        "tiempo": float(res["tiempo"]),  # type: ignore[arg-type]
        "exceso_max": float(max(f[5] for f in filas)),
        "muerto_medio": float(np.mean(muertos)) if muertos else 0.0,
        "dec_max": float(dec.max()),
        "pct_energia_girando": 100.0 * float(e[lat[:-1] > 4.0].sum() / max(e.sum(), 1e-9)),
        "frenadas": float(len(inicios)),
    }


@pytest.fixture(scope="module")
def vueltas() -> Dict[str, Dict[str, float]]:
    return {m: _metricas(_vuelta(m)) for m in ("base", "tecnica", "perfil")}


def test_defaults_keep_the_production_law():
    cfg = TeacherConfig()
    assert cfg.brake_profile is False and cfg.brake_circle == 14.6
    a = _vuelta("tecnica")
    b = _vuelta("tecnica", brake_circle=12.0, brake_ff_ahead_m=20.0)  # los parámetros del perfil no hacen nada si está apagado
    assert [f[2:4] for f in a["filas"]] == [f[2:4] for f in b["filas"]]  # type: ignore[index]


def test_pedal_for_decel_is_monotonic_and_matches_the_measured_table():
    xs = np.linspace(0.0, 14.0, 80)
    ps = [pedal_for_decel(float(x)) for x in xs]
    assert all(b >= a for a, b in zip(ps, ps[1:])) and ps[0] == 0.0 and ps[-1] == 1.0
    assert pedal_for_decel(8.6) == pytest.approx(0.475) and pedal_for_decel(11.65) == pytest.approx(0.85)


@pytest.mark.parametrize("a_b", [8.0, 10.0])
def test_profile_never_asks_for_more_than_the_available_deceleration(a_b):
    """Ningún tramo del perfil exige más deceleración que a_b (el de hoy llega a ≈ 140 m/s² en el salto de 8 a 4)."""
    t = _teacher(brake_decel_straight=a_b, pedal_technique=True, brake_profile=True)
    prof = t.braking_profile()
    n = len(prof)
    implicita = [(prof[i] ** 2 - prof[(i + 1) % n] ** 2) / 2.0 for i in range(n)]
    assert max(implicita) <= a_b + 1e-6
    vieja = _teacher(brake_decel_straight=a_b)
    objetivo = [vieja.physical_curve_target(float(d), a_b if abs(vieja.ref.curvature(float(d))) < 0.004 else None) for d in range(n)]
    salto = max((objetivo[i] ** 2 - objetivo[(i + 1) % n] ** 2) / 2.0 for i in range(n))
    assert salto > 3.0 * a_b  # la consigna actual sí da un salto


def test_profile_uses_less_braking_where_there_is_more_cornering():
    t = _teacher(brake_decel_straight=10.0, pedal_technique=True, brake_profile=True)
    prof = t.braking_profile()
    kappa = t._smoothed_kappa()
    n = len(prof)
    a_long = {i: (prof[i] ** 2 - prof[(i + 1) % n] ** 2) / 2.0 for i in range(n)}
    con_giro = [a for i, a in a_long.items() if a > 0.1 and prof[(i + 1) % n] ** 2 * kappa[i] > 8.0]
    en_recta = [a for i, a in a_long.items() if a > 0.1 and prof[(i + 1) % n] ** 2 * kappa[i] < 1.0]
    assert con_giro and en_recta and max(con_giro) < 0.85 * max(en_recta)


def test_profile_info_points_at_a_local_minimum_of_the_profile():
    t = _teacher(pedal_technique=True, brake_profile=True)
    prof = t.braking_profile()
    n = len(prof)
    encontrados = 0
    for s in range(0, n, 7):
        best, s_bind, v_bind = t.profile_info(float(s))
        k = (s + int(s_bind)) % n
        assert prof[k] == pytest.approx(v_bind)
        if s_bind < t.config.curve_lookahead_m:
            assert prof[k] <= prof[(k + 1) % n] + 1e-9  # deja de bajar ahí (si no, la bajada sigue más allá del horizonte)
        if s_bind >= 5.0 and v_bind < best - 3.0:
            encontrados += 1
            assert prof[(k - 1) % n] >= prof[k] - 1e-9  # y venía bajando: es una curva que viene
    assert encontrados > 10  # Sugo tiene muchas curvas por delante de una frenada


def test_profile_offset_raises_the_corner_speed_by_the_configured_margin():
    sin = _teacher(pedal_technique=True, brake_profile=True, brake_profile_offset_ms=0.0).braking_profile()
    con = _teacher(pedal_technique=True, brake_profile=True).braking_profile()
    assert TeacherConfig().brake_profile_offset_ms == 1.0
    assert min(con) == pytest.approx(min(sin) + 1.0, abs=0.2) and all(c >= s - 1e-9 for c, s in zip(con, sin))


def test_profile_mode_never_enters_a_corner_faster_than_the_real_braking_capacity():
    for acel in (1.0, 1.3, 1.6):
        base, perfil = _metricas(_vuelta("base", acel)), _metricas(_vuelta("perfil", acel))
        assert perfil["exceso_max"] <= base["exceso_max"] + 0.5, (acel, base, perfil)  # no más que la producción sobre lo que se podría frenar a capacidad


def test_profile_mode_brakes_without_dead_time_and_harder_than_production(vueltas):
    p, b = vueltas["perfil"], vueltas["base"]
    assert p["muerto_medio"] <= 0.15
    assert p["tiempo"] <= b["tiempo"] + 0.5  # no pierde tiempo con el juguete
    assert p["pct_energia_girando"] <= b["pct_energia_girando"] + 1.0  # el juguete estima el lateral con v² · κ de la línea
    fuerte = _metricas(_vuelta("perfil", brake_decel_straight=10.0))
    assert fuerte["dec_max"] > b["dec_max"] + 1.0  # con a_b = 10 el pedal llega más alto que en producción


def test_smaller_circle_moves_braking_out_of_the_corner():
    """El radio del círculo es el mando entre trail braking completo (14,6) y «terminar de frenar antes de girar» (≈ 10)."""
    completo = _metricas(_vuelta("perfil", brake_decel_straight=10.0, brake_circle=14.6))
    recto = _metricas(_vuelta("perfil", brake_decel_straight=10.0, brake_circle=10.0))
    assert recto["pct_energia_girando"] < completo["pct_energia_girando"] - 5.0
    assert recto["tiempo"] <= completo["tiempo"] + 0.6


def test_profile_mode_never_presses_both_pedals(vueltas):
    filas = _vuelta("perfil")["filas"]
    assert all(min(f[2], f[3]) == 0.0 for f in filas)  # type: ignore[index]
    assert {"lift_lock", "brake_overspeed", "accel_exit"} <= {f[4] for f in filas}  # type: ignore[index]
