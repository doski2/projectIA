"""Tests del ajuste del solver a las vueltas de la IA (`ajuste_ia.py`) con vueltas sintéticas de parámetros conocidos."""

import json
import math

import numpy as np
import pytest

from circuito_virtual.src import ajuste_ia as ai
from circuito_virtual.src import perfil_velocidad as pv

RECTA = 600
RADIO = 60.0


def _oval():
    """Óvalo cerrado, un punto por metro: rectas de 600 m y semicírculos de 60 m a la izquierda."""
    pts = [(float(s), 0.0) for s in range(RECTA)]
    n_arc = int(math.pi * RADIO)
    pts += [(RECTA + RADIO * math.cos(a), RADIO + RADIO * math.sin(a)) for a in (-math.pi / 2 + math.pi * i / n_arc for i in range(n_arc))]
    pts += [(float(RECTA - s), 2 * RADIO) for s in range(RECTA)]
    pts += [(RADIO * math.cos(a) + 0.0, RADIO + RADIO * math.sin(a)) for a in (math.pi / 2 + math.pi * i / n_arc for i in range(n_arc))]
    return np.array(pts)


COCHE = pv.CarParams([(40.0, 4.0), (200.0, 2.5)], [(40.0, 8.0), (200.0, 10.0)], mu=6.0, k=0.004, v_known_kmh=170.0)


def _archivo(tmp_path, n_vueltas=4):
    pts = _oval()
    x, z = pts[:, 0], pts[:, 1]
    track = pv.Track.from_arrays(x, z, np.zeros(len(x)), float(len(x)))
    prof = pv.solve(track, COCHE)
    v = prof.v_ms
    a = v * np.gradient(v)
    kappa_firmada = np.gradient(np.unwrap(np.arctan2(np.gradient(z), np.gradient(x))))
    vueltas = []
    for i in range(n_vueltas):
        vueltas.append({"vuelta": i + 1, "tiempo_s": float(prof.time_s) + 0.05 * i, "d": [float(k) for k in range(len(x))],
                        "x": x.round(2).tolist(), "y": [0.0] * len(x), "z": z.round(2).tolist(), "v_ms": v.round(3).tolist(),
                        "freno": [150 if q < -3.0 else 0 for q in a], "marcha": [3] * len(x), "rpm": [6000] * len(x),
                        "a_lat": [0.0] * len(x), "a_long": [0.0] * len(x), "yaw": (kappa_firmada * v).round(4).tolist()})
    ruta = tmp_path / "ia.json"
    ruta.write_text(json.dumps({"pista": "oval", "longitud_m": float(len(x)), "vueltas": vueltas}), encoding="utf-8")
    return ruta, prof


def test_loader_computes_lateral_from_yaw_and_longitudinal_from_speed(tmp_path):
    ruta, prof = _archivo(tmp_path)
    v = ai.cargar(ruta)[0]
    n = len(v["v_ms"])
    curva = slice(RECTA + 20, RECTA + 160)
    assert np.mean(v["a_lat"][curva]) == pytest.approx(np.mean(v["v_ms"][curva] ** 2 / RADIO), rel=0.1)  # |v · guiñada| = v²/R
    assert np.max(v["a_long"]) > 1.0 and np.min(v["a_long"]) < -3.0 and n > 1500  # acelera y frena


def test_fit_recovers_the_car_within_a_reasonable_margin(tmp_path):
    ruta, prof = _archivo(tmp_path)
    vueltas = ai.cargar(ruta)
    coche = ai.ajustar(vueltas)
    assert all(a >= 0.0 for _, a in coche.accel) and 2.5 < coche.accel[0][1] < 4.6 and len(coche.brake) >= 2
    assert 5.0 < coche.mu + coche.k * 22.0 ** 2 < 14.0  # el límite lateral ajustado es del orden de 8 m/s² a 80 km/h


def test_pace_factor_calibration_matches_the_target_lap_time(tmp_path):
    ruta, prof = _archivo(tmp_path)
    vueltas = ai.cargar(ruta)
    track = ai.linea_mediana(vueltas, float(len(vueltas[0]["x"])))
    coche = ai.ajustar(vueltas)
    objetivo = pv.solve(track, ai.escalar(coche, 0.8)).time_s
    f = ai.calibrar_ritmo(coche, track, objetivo)
    assert f == pytest.approx(0.8, abs=0.01)
    assert pv.solve(track, ai.escalar(coche, f)).time_s == pytest.approx(objetivo, rel=0.002)


def test_scaled_car_scales_acceleration_braking_and_lateral_limit():
    c = ai.escalar(COCHE, 0.5)
    assert c.accel[0][1] == pytest.approx(2.0) and c.brake[1][1] == pytest.approx(5.0) and c.mu == pytest.approx(3.0) and c.k == pytest.approx(0.002)


def test_full_analysis_runs_and_reports_the_held_out_laps(tmp_path):
    ruta, _ = _archivo(tmp_path, n_vueltas=5)
    r = ai.analizar(ruta, n_ajuste=3)
    assert r["n_ajuste"] == 3 and r["n_prueba"] == 2 and len(r["calibrado"]["prueba"]) == 2
    assert abs(r["calibrado"]["prueba"][0]["error_tiempo_pct"]) < 3.0 and r["calibrado"]["prueba"][0]["correlacion_v"] > 0.8


def test_the_committed_ai_laps_give_the_real_pace_result():
    if not ai.IA.is_file():
        pytest.skip("archivo de la IA no generado")
    r = ai.analizar()
    assert r["calibrado"]["prueba"] and abs(np.mean([x["error_tiempo_pct"] for x in r["calibrado"]["prueba"]])) < 3.0  # criterio de A2
    assert 0.5 < r["factor_ritmo"] < 0.9 and np.mean([x["correlacion_v"] for x in r["calibrado"]["prueba"]]) > 0.9
