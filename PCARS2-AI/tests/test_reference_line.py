"""
Tests de la línea de referencia (`reference_recorder.ReferenceLine`).

La referencia de trazado es la base de TODA la función de recompensa y de la
observación del entorno: cross-track error, delta de velocidad, zonas de
frenada, lookahead, etc. Si la referencia no carga o devuelve datos absurdos,
el entrenamiento produce recompensas sin sentido aunque "no falle".

Estos tests no necesitan el juego ni hardware: construyen una referencia
sintética en memoria y validan la geometría y la persistencia.
"""

import math
import os
import glob

import pytest

from reference_recorder import ReferenceLine, ReferencePoint


def _straight_line_ref(length: float = 100.0) -> ReferenceLine:
    """
    Crea una referencia recta a lo largo del eje +X (z=0), 1 punto por metro.
    Velocidad constante 50 m/s, gas a fondo, sin freno.
    """
    points = []
    for d in range(int(length)):
        points.append(
            ReferencePoint(
                lap_distance=float(d),
                position=(float(d), 0.0, 0.0),   # avanza en X, z=0
                speed=50.0,
                throttle=255,
                brake=0,
                steering=0,
                gear=4,
                orientation=(0.0, 0.0, 0.0),
            )
        )
    return ReferenceLine(
        points=points,
        track_length=length,
        track_name="test_straight",
        lap_time=2.0,
        all_laps=None,
    )


# ---------------------------------------------------------------------------
# Lookup y wrap-around
# ---------------------------------------------------------------------------

def test_lookup_exact_key():
    ref = _straight_line_ref()
    p = ref.lookup(10.0)
    assert p is not None
    assert p.lap_distance == 10.0


def test_lookup_wraps_around_track_length():
    ref = _straight_line_ref(length=100.0)
    # 105 m en una pista de 100 m → 5 m
    p = ref.lookup(105.0)
    assert p is not None
    assert p.lap_distance == 5.0


def test_lookup_nearest_when_missing():
    ref = _straight_line_ref()
    # 10.4 no existe como clave entera exacta -> redondea al más cercano (10)
    p = ref.lookup(10.4)
    assert p is not None
    assert p.lap_distance == 10.0


def test_lookup_empty_returns_none():
    ref = ReferenceLine(points=[], track_length=0.0, track_name="empty", lap_time=0.0)
    assert ref.lookup(5.0) is None


# ---------------------------------------------------------------------------
# Cross-track error
# ---------------------------------------------------------------------------

def test_cte_on_track_is_zero():
    ref = _straight_line_ref()
    # Posición exactamente sobre el trazado en d=20 → CTE ~ 0
    cte = ref.cross_track_error((20.0, 0.0, 0.0), 20.0)
    assert cte == pytest.approx(0.0, abs=1e-6)


def test_cte_lateral_offset():
    ref = _straight_line_ref()
    # Desviado 3 m en Z respecto al trazado (que está en z=0)
    cte = ref.cross_track_error((20.0, 0.0, 3.0), 20.0)
    assert cte == pytest.approx(3.0, abs=1e-6)


def test_cte_ignores_altitude_y():
    ref = _straight_line_ref()
    # Diferencia solo en Y (altitud) no debe contar
    cte = ref.cross_track_error((20.0, 99.0, 0.0), 20.0)
    assert cte == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Delta de velocidad
# ---------------------------------------------------------------------------

def test_speed_delta_sign():
    ref = _straight_line_ref()  # referencia a 50 m/s
    assert ref.speed_delta(60.0, 10.0) == pytest.approx(10.0)   # más rápido
    assert ref.speed_delta(40.0, 10.0) == pytest.approx(-10.0)  # más lento
    assert ref.speed_delta(50.0, 10.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Zonas de frenada / throttle / brake de referencia
# ---------------------------------------------------------------------------

def test_braking_zone_detection():
    points = [
        ReferencePoint(0.0, (0.0, 0.0, 0.0), 50.0, 255, 0,   0, 4, (0, 0, 0)),
        ReferencePoint(1.0, (1.0, 0.0, 0.0), 30.0, 0,   200, 0, 3, (0, 0, 0)),
    ]
    ref = ReferenceLine(points, track_length=2.0, track_name="brk", lap_time=1.0)
    assert ref.is_braking_zone(0.0) is False   # brake=0
    assert ref.is_braking_zone(1.0) is True     # brake=200 >= 30


def test_reference_throttle_and_brake_normalized():
    points = [
        ReferencePoint(0.0, (0.0, 0.0, 0.0), 50.0, 255, 0, 0, 4, (0, 0, 0)),
        ReferencePoint(1.0, (1.0, 0.0, 0.0), 50.0, 0, 255, 0, 4, (0, 0, 0)),
    ]
    ref = ReferenceLine(points, track_length=2.0, track_name="n", lap_time=1.0)
    assert ref.reference_throttle(0.0) == pytest.approx(1.0)
    assert ref.reference_brake(0.0) == pytest.approx(0.0)
    assert ref.reference_throttle(1.0) == pytest.approx(0.0)
    assert ref.reference_brake(1.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Heading / curvatura
# ---------------------------------------------------------------------------

def test_heading_vector_straight_line():
    ref = _straight_line_ref()
    hv = ref.heading_vector(10.0)
    assert hv is not None
    dx, dz = hv
    # Recta en +X → vector (1, 0)
    assert dx == pytest.approx(1.0, abs=1e-6)
    assert dz == pytest.approx(0.0, abs=1e-6)


def test_curvature_straight_is_zero():
    ref = _straight_line_ref()
    assert ref.curvature(10.0) == pytest.approx(0.0, abs=1e-6)


def test_speed_lookahead():
    points = [
        ReferencePoint(float(d), (float(d), 0.0, 0.0), float(d), 255, 0, 0, 4, (0, 0, 0))
        for d in range(100)
    ]
    ref = ReferenceLine(points, track_length=100.0, track_name="lk", lap_time=1.0)
    # speed = lap_distance en esta referencia → lookahead 50 m desde d=10 → ~60
    assert ref.speed_lookahead(10.0, 50.0) == pytest.approx(60.0, abs=1.0)


# ---------------------------------------------------------------------------
# Persistencia: round-trip save/load
# ---------------------------------------------------------------------------

def test_save_load_round_trip(tmp_path):
    ref = _straight_line_ref(length=50.0)
    out = os.path.join(str(tmp_path), "ref.json")
    ref.save(out)
    assert os.path.isfile(out)

    loaded = ReferenceLine.load(out)
    assert loaded.track_length == pytest.approx(ref.track_length)
    assert len(loaded.points) == len(ref.points)
    # La geometría se conserva tras el round-trip
    assert loaded.cross_track_error((20.0, 0.0, 2.0), 20.0) == pytest.approx(2.0, abs=1e-3)
    assert loaded.speed_delta(55.0, 20.0) == pytest.approx(5.0, abs=1e-3)


# ---------------------------------------------------------------------------
# Validación de las referencias reales en disco (las que usa el entrenamiento)
# ---------------------------------------------------------------------------

_REFS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src", "refs")
)
_REAL_REFS = glob.glob(os.path.join(_REFS_DIR, "*.json"))


@pytest.mark.skipif(not _REAL_REFS, reason="No hay referencias .json en src/refs")
@pytest.mark.parametrize("ref_path", _REAL_REFS, ids=lambda p: os.path.basename(p))
def test_real_reference_is_trainable(ref_path):
    """
    Cada referencia en src/refs debe cargar y exponer datos coherentes:
    el entorno se negaría a entrenar correctamente con una referencia vacía
    o con longitud de pista 0.
    """
    ref = ReferenceLine.load(ref_path)
    assert len(ref.points) > 20, "referencia con muy pocos puntos"
    assert ref.track_length > 0, "track_length debe ser > 0"
    # lookup debe devolver algo en mitad de la vuelta; CTE sobre el trazado ~0
    mid = ref.track_length / 2.0
    p = ref.lookup(mid)
    assert p is not None
    cte = ref.cross_track_error(p.position, p.lap_distance)
    assert cte == pytest.approx(0.0, abs=1.0)
