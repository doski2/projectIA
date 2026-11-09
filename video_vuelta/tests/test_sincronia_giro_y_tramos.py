"""Tests de `sincronia_giro.py` (desfase por correlación del giro) y `tramos_dudosos.py` (agrupación de cruces), con datos sintéticos."""
import numpy as np

from video_vuelta.src import sincronia_giro as sg
from video_vuelta.src import tramos_dudosos as td


def test_correlation_finds_the_known_offset_even_with_a_sign_flip():
    t_log = np.arange(0, 120, 0.02)
    giro_log = 0.4 * np.sin(2 * np.pi * t_log / 11.0) + 0.2 * np.sin(2 * np.pi * t_log / 4.3)
    tv = np.arange(20, 100, 1 / 30)
    desfase = 8.55
    giro_video = -np.interp(tv + desfase, t_log, giro_log)  # el vídeo puede dar el signo contrario
    r = sg.mejor_desfase(tv, giro_video, t_log, giro_log)
    assert abs(r["desfase_s"] - desfase) <= 0.05 and abs(r["correlacion"]) > 0.95


def test_correlation_is_low_on_a_straight_without_turning():
    t_log = np.arange(0, 60, 0.02)
    rng = np.random.default_rng(1)
    giro_log = rng.normal(0, 0.01, len(t_log))
    tv = np.arange(10, 50, 1 / 30)
    giro_video = rng.normal(0, 0.01, len(tv))
    assert abs(sg.mejor_desfase(tv, giro_video, t_log, giro_log)["correlacion"]) < 0.5


def test_group_crossings_by_distance_and_threshold():
    cruces = [{"s": 100.0, "error": 0.2}, {"s": 300.0, "error": 1.0}, {"s": 310.0, "error": -0.8}, {"s": 500.0, "error": 0.6}, {"s": 355.0, "error": 0.1}]
    g = td.agrupar(cruces, 0.5)
    assert [[c["s"] for c in grupo] for grupo in g] == [[300.0, 310.0], [500.0]]


def test_terrain_sequence_collapses_repeats_and_curve_lookup():
    assert td.secuencia([0, 0, 7, 7, 0, 10]) == "0→7→0→10"
    curvas = [{"id": 3, "s_ini": 500, "s_fin": 600}]
    assert td.curva_de(520, curvas) == "C3" and td.curva_de(700, curvas) == "recta" and td.curva_de(490, curvas) == "C3"
