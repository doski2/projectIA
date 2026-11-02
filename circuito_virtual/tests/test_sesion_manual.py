"""Tests del grabador pasivo de D1b por conducción manual (`sesion_manual.py`): paquetes sintéticos, sin red ni juego."""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from circuito_virtual.src import bordes_logs as bl
from circuito_virtual.src import mapa as mp
from circuito_virtual.src import sesion_manual as sm

LARGO = 2000
BORDE_IZQ = -2.0
BORDE_DCHA = 2.5


def _mapa_recta():
    """Misma recta sintética que en `test_bordes_logs.py`: eje a lo largo de +x, derecha = −z."""
    pts = [(float(i), 0.0) for i in range(LARGO // 2)] + [(float(LARGO // 2 - i), 50.0) for i in range(LARGO // 2)]
    datos = {"track_name": "recta", "track_length": float(len(pts)), "points": [{"d": float(i), "pos": [x, 0.0, z]} for i, (x, z) in enumerate(pts)]}
    return mp.Mapa.desde_referencia(datos)


def _fisica(x=0.0, z=0.0, terreno=(0, 0, 0, 0), velocidad_ms=16.7, ia=False):
    return SimpleNamespace(
        position=(x, 0.0, z), orientation=(0.0, 0.0, 0.0), speed=velocidad_ms, throttle=128, brake=0, steering=0, gear=2,
        terrain=terreno, tyre_rps=(10.0, 10.0, 10.0, 10.0), tyre_flags=(7, 7, 7, 7), viewed_is_ai=ia,
    )


def _tiempos(s=100.0, vuelta=1):
    return SimpleNamespace(lap_distance=s, current_lap=vuelta, current_time=12.0, current_sector_time=3.0, sector=1)


def _grabador(tmp_path, lado="izq", vueltas=2):
    g = sm.GrabadorManual(tmp_path / "manual" / "x.jsonl", lado, vueltas)
    g.abrir()
    return g


def _ticks(ruta):
    filas = [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]
    return filas[0], filas[1:]


def test_header_and_tick_fields_are_what_the_extractor_reads(tmp_path):
    g = _grabador(tmp_path)
    g.procesar(sm.PACKET_TIMINGS, _tiempos(123.456, 1))
    assert g.procesar(sm.PACKET_CAR_PHYSICS, _fisica(x=5.0, z=-1.0, terreno=(7, 0, 7, 0)))
    g.cerrar()
    cab, ticks = _ticks(g.ruta)
    assert cab["type"] == "session" and cab["log_schema"] >= 2 and cab["origin"] == "manual" and cab["side"] == "izq"
    assert len(ticks) == 1
    t = ticks[0]
    assert t["type"] == "tick" and t["lap"] == 1 and t["lap_distance"] == 123.46
    assert t["speed_kmh"] == pytest.approx(60.12, abs=0.01)
    assert t["vehicle"]["position"] == [5.0, 0.0, -1.0] and t["vehicle"]["terrain"] == [7, 0, 7, 0]


def test_no_tick_until_timings_arrive_and_ai_frames_are_discarded(tmp_path):
    g = _grabador(tmp_path)
    assert not g.procesar(sm.PACKET_CAR_PHYSICS, _fisica())
    g.procesar(sm.PACKET_TIMINGS, _tiempos())
    assert not g.procesar(sm.PACKET_CAR_PHYSICS, _fisica(ia=True))
    assert not g.procesar(sm.PACKET_CAR_PHYSICS, None)
    assert not g.procesar(99, object())
    assert g.procesar(sm.PACKET_CAR_PHYSICS, _fisica())
    g.cerrar()
    assert g.ticks == 1 and g.ticks_ia == 1


def test_it_finishes_after_the_requested_number_of_laps(tmp_path):
    g = _grabador(tmp_path, vueltas=2)
    for vuelta in (5, 5, 6):
        g.procesar(sm.PACKET_TIMINGS, _tiempos(vuelta=vuelta))
        g.procesar(sm.PACKET_CAR_PHYSICS, _fisica())
        assert not g.terminado
    assert g.vueltas_completas == 1
    g.procesar(sm.PACKET_TIMINGS, _tiempos(vuelta=7))
    g.procesar(sm.PACKET_CAR_PHYSICS, _fisica())
    assert g.terminado and g.vueltas_completas == 2
    g.cerrar()


def test_a_lap_counter_that_goes_back_does_not_end_or_undo_the_session(tmp_path):
    g = _grabador(tmp_path, vueltas=2)
    for vuelta in (3, 4, 1):  # reinicio de sesión en el juego
        g.procesar(sm.PACKET_TIMINGS, _tiempos(vuelta=vuelta))
        g.procesar(sm.PACKET_CAR_PHYSICS, _fisica())
    assert g.vueltas_completas == 1 and not g.terminado
    g.cerrar()


def test_summary_counts_wheels_off_on_the_requested_side_only_when_moving(tmp_path):
    g = _grabador(tmp_path, lado="izq")
    g.procesar(sm.PACKET_TIMINGS, _tiempos())
    g.procesar(sm.PACKET_CAR_PHYSICS, _fisica(terreno=(7, 0, 7, 0)))  # las dos izquierdas fuera
    g.procesar(sm.PACKET_CAR_PHYSICS, _fisica(terreno=(7, 0, 0, 0)))  # una
    g.procesar(sm.PACKET_CAR_PHYSICS, _fisica(terreno=(0, 7, 0, 0)))  # del otro lado
    g.procesar(sm.PACKET_CAR_PHYSICS, _fisica(terreno=(7, 0, 7, 0), velocidad_ms=1.0))  # parado: no cuenta
    g.cerrar()
    assert g.resumen_ticks == {"en_marcha": 3, "lado_dos_fuera": 1, "lado_una_fuera": 1, "otro_lado_fuera": 1}
    assert "33 % con las dos ruedas del lado izq fuera" in g.resumen()


def test_invalid_side_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        sm.GrabadorManual(tmp_path / "x.jsonl", "centro")


def test_a_manual_lap_with_the_left_wheels_on_the_grass_gives_a_tight_left_edge(tmp_path):
    """De punta a punta: las ruedas izquierdas van pegadas al borde (n_rueda ≈ BORDE_IZQ) y el log del grabador lo lee `bordes_logs.py`.

    El zigzag es de 1,6 m de periodo para que cada metro de vuelta vea las dos situaciones (rueda dentro y rueda fuera); con una conducción real los cambios son
    más lentos y habrá metros con una sola cota (hace falta un extractor con ventana, pendiente de ver datos reales)."""
    m = _mapa_recta()
    g = _grabador(tmp_path, lado="izq", vueltas=1)
    s_vals = np.arange(100.0, 900.0, 0.25)
    rng = np.random.default_rng(1)
    n_centro = BORDE_IZQ + bl.SEMIVIA_M + 0.05 * np.sin(4.0 * s_vals) + rng.normal(0.0, 0.01, len(s_vals))  # zigzag de ±5 cm sobre el borde
    x, z = m.sn_a_xz(s_vals, n_centro)
    for s, n, xi, zi in zip(s_vals, n_centro, x, z):
        izq_fuera = (n - bl.SEMIVIA_M) < BORDE_IZQ
        terreno = (7, 0, 7, 0) if izq_fuera else (0, 0, 0, 0)
        g.procesar(sm.PACKET_TIMINGS, _tiempos(s, 1))
        g.procesar(sm.PACKET_CAR_PHYSICS, _fisica(float(xi), float(zi), terreno, velocidad_ms=16.7))
    g.cerrar()

    obs = bl.Observaciones.vacia(m)
    assert obs.agregar_log(m, g.ruta) > 0
    borde = obs.bordes()["izq"][150:850]
    assert np.mean(np.isfinite(borde)) > 0.9
    assert np.nanmax(np.abs(borde - BORDE_IZQ)) < 0.1
    hueco = obs.izq_dentro[150:850] - obs.izq_fuera[150:850]
    assert np.nanmedian(np.abs(hueco)) < 0.15
