"""Tests del mapa de bordes corregido (`mapa_corregido.py`): cotas de las ruedas, reglas del piano y propagación, con datos sintéticos."""
import numpy as np

from video_vuelta.src import mapa_corregido as mc

N = 200
L = 200.0


def _tick(bin_, afuera, terr):
    return bin_, afuera, terr


def _cotas(filas, **kw):
    """filas: [(metro, afuera de las dos ruedas, terreno de las dos ruedas)]."""
    bins = np.array([f[0] for f in filas])
    afuera = np.array([[f[1], f[1]] for f in filas], dtype=float)
    terr = np.array([[f[2], f[2]] for f in filas])
    return mc.cotas_de_lado(bins, afuera, terr, N, L, "izq", **kw)


def test_legal_to_grass_crossing_gives_a_tight_bracket_and_midpoint():
    dentro, fuera = _cotas([(50, 4.0, 0), (50, 4.4, 0), (50, 4.6, 7)])
    assert dentro[50] == 4.4 and fuera[50] == 4.6
    lim, sigma, fuente = mc.combinar(np.full(N, 9.0), dentro, fuera)
    assert fuente[50] == mc.FUENTE_HORQUILLA and abs(lim[50] - 4.5) < 1e-9 and sigma[50] < 0.25


def test_asphalt_behind_the_first_illegal_surface_does_not_count():
    # hierba a 5 m y, más allá, asfalto de la entrada a boxes a 9 m: el límite no puede irse a 9
    dentro, fuera = _cotas([(10, 4.5, 0), (10, 5.0, 7), (10, 9.0, 0)])
    assert fuera[10] == 5.0 and dentro[10] == 4.5


def test_flat_piano_is_legal_and_the_rough_band_is_outside_when_both_are_seen():
    # dos partes: 48 hasta 5,0 y 10 desde 5,2 → el límite es el borde del plano
    dentro, fuera = _cotas([(30, 4.0, 0), (30, 5.0, 48), (31, 5.2, 10), (31, 6.0, 7)])
    assert dentro[30] == 5.0 and fuera[31] == 5.2


def test_rumble_strip_alone_is_legal_in_full():
    dentro, fuera = _cotas([(30, 4.0, 0), (30, 5.5, 10), (30, 6.2, 7)])
    assert dentro[30] == 5.5 and fuera[30] == 6.2


def test_48_is_not_a_piano_in_the_excluded_zone():
    dentro, fuera = _cotas([(100, 4.0, 0), (100, 4.6, 48), (100, 5.0, 0)], sin_48=[(95.0, 105.0)])
    assert fuera[100] == 4.6 and dentro[100] == 4.0


def test_line_priority_zone_ignores_the_wheel_bounds():
    dentro, fuera = _cotas([(120, 4.0, 0), (120, 6.5, 0), (120, 7.0, 7)], linea_manda=[(115.0, 125.0)])
    assert np.isnan(dentro[120]) and np.isnan(fuera[120])


def test_combine_clips_the_video_to_the_bounds_that_matter_and_ignores_the_ones_that_do_not():
    video = np.full(N, 6.0)
    dentro = np.full(N, np.nan)
    fuera = np.full(N, np.nan)
    dentro[10] = 7.0           # el piano llega más afuera que el vídeo: manda
    fuera[20] = 5.0            # una rueda en hierba por dentro del vídeo: manda
    dentro[30] = 2.0           # rueda legal muy por dentro: no dice nada
    fuera[40] = 9.0            # hierba lejos: no dice nada
    lim, _, fuente = mc.combinar(video, dentro, fuera)
    assert lim[10] == 7.0 and fuente[10] == mc.FUENTE_DENTRO
    assert lim[20] == 5.0 and fuente[20] == mc.FUENTE_FUERA
    assert lim[30] == 6.0 and fuente[30] == mc.FUENTE_VIDEO and lim[40] == 6.0 and fuente[40] == mc.FUENTE_VIDEO


def test_small_bound_changes_are_noise_and_do_not_move_the_video():
    video = np.full(N, 6.0)
    dentro = np.full(N, np.nan)
    dentro[10] = 6.05
    lim, _, fuente = mc.combinar(video, dentro, np.full(N, np.nan))
    assert lim[10] == 6.0 and fuente[10] == mc.FUENTE_VIDEO


def test_propagation_interpolates_between_anchors_and_fades_next_to_a_single_one():
    delta = np.full(N, np.nan)
    ancla = np.zeros(N, dtype=bool)
    delta[10], delta[30] = 1.0, -1.0
    ancla[10] = ancla[30] = True
    p = mc.propagar(delta, ancla)
    assert abs(p[20] - 0.0) < 1e-9 and 0.0 < p[15] < 1.0           # interpolada entre las dos
    delta2 = np.full(N, np.nan)
    ancla2 = np.zeros(N, dtype=bool)
    delta2[100], ancla2[100] = 1.2, True
    q = mc.propagar(delta2, ancla2)
    assert q[100 + mc.PLENO_M] == 1.2 and 0.0 < q[100 + mc.ALCANCE_M - 3] < 1.2 and np.isnan(q[100 + mc.ALCANCE_M + 5])


def test_cross_validation_beats_the_video_when_the_error_is_a_systematic_offset():
    video = np.full(N, 6.0)
    dentro = np.full(N, np.nan)
    fuera = np.full(N, np.nan)
    for m in range(20, 60, 2):          # el vídeo se pasa 1 m en esta zona; las ruedas lo ven en cada dos metros
        dentro[m], fuera[m] = 4.95, 5.05
    v = mc.validacion_cruzada(video, dentro, fuera)
    assert v["error_corregido_mediano"] < 0.2 < v["error_video_mediano"]


def test_illegal_wheel_on_the_far_side_of_the_track_does_not_mark_this_edge():
    # el coche en la hierba del otro lado: la rueda «derecha» ilegal está a −9 m hacia fuera
    dentro, fuera = _cotas([(60, 4.0, 0), (60, -9.0, 7), (60, 5.0, 7)])
    assert fuera[60] == 5.0


def test_rules_file_is_read_and_a_missing_one_means_no_exceptions(tmp_path):
    f = tmp_path / "reglas_limite.json"
    f.write_text('{"sin_48": {"dcha": [[10, 20]]}, "linea_manda": {"izq": [[30.5, 40]]}}', encoding="utf-8")
    r = mc.cargar_reglas(f)
    assert r["sin_48"] == {"izq": [], "dcha": [(10.0, 20.0)]} and r["linea_manda"] == {"izq": [(30.5, 40.0)], "dcha": []}
    vacio = mc.cargar_reglas(tmp_path / "no_existe.json")
    assert vacio["sin_48"] == {"izq": [], "dcha": []} and vacio["linea_manda"] == {"izq": [], "dcha": []}
