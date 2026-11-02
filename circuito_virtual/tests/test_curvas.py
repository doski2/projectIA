import json
from pathlib import Path

import numpy as np
import pytest

from circuito_virtual.src import curvas as cv
from circuito_virtual.src.mapa import Mapa

PISTA = Path(__file__).resolve().parents[1] / "pistas" / "sugo_gp"


def _kappa(picos, n=3000):
    """Curvatura sintética: campanas gaussianas (posición m, altura 1/m con signo, ancho m)."""
    s = np.arange(n, dtype=float)
    k = np.zeros(n)
    for pos, alto, ancho in picos:
        k += alto * np.exp(-0.5 * ((s - pos) / ancho) ** 2)
    return k


def test_corners_are_numbered_from_the_finish_line_with_direction_and_radius():
    k = _kappa([(500, -0.02, 20), (900, 0.015, 25), (1900, -0.01, 30)])
    cur = cv.detectar(k, 3000.0)
    assert [c.id for c in cur] == [1, 2, 3]
    assert [c.sentido for c in cur] == ["dcha", "izq", "dcha"]
    assert [round(c.s_apice, -1) for c in cur] == [500, 900, 1900]
    assert cur[0].radio_min_m == pytest.approx(50.0, rel=0.15) and cur[1].radio_min_m == pytest.approx(66.7, rel=0.15)
    assert all(c.s_ini < c.s_apice < c.s_fin for c in cur)


def test_double_apex_and_long_arcs_are_split_or_merged_sensibly():
    doble = cv.detectar(_kappa([(1000, 0.02, 12), (1030, 0.018, 12)]), 3000.0)
    assert len(doble) == 1  # dos picos del mismo sentido a 30 m: una curva
    arco = cv.detectar(_kappa([(1000, 0.01, 40), (1200, 0.011, 40), (1400, 0.01, 40)]), 3000.0)
    assert len(arco) == 3 and arco[0].s_fin <= arco[1].s_ini + 1 and arco[1].s_fin <= arco[2].s_ini + 1  # una derecha larga con tres ápices: sin solapes


def test_opposite_corners_close_together_form_an_ese():
    cur = cv.detectar(_kappa([(500, -0.02, 15), (580, 0.02, 15), (1800, 0.02, 15)]), 3000.0)
    assert cur[0].ese_con == 2 and cur[1].ese_con == 1 and cur[2].ese_con is None


def test_labels_and_next_corner(tmp_path):
    cat = cv.Catalogo(cv.detectar(_kappa([(500, -0.02, 20), (1500, 0.02, 20)]), 3000.0), 3000.0, "x")
    assert cat.etiqueta(500) == "C1" and cat.curva_en(1500).id == 2
    assert cat.etiqueta(1000) == "recta C1→C2" and cat.proxima(1000).id == 2 and cat.proxima(2000).id == 1  # tras la última, la primera (la vuelta se cierra)
    assert cat.proxima(500).id == 1
    cat.guardar(tmp_path / "curvas.json")
    otra = cv.Catalogo.cargar(tmp_path / "curvas.json")
    assert [c.id for c in otra.curvas] == [1, 2] and otra.longitud_m == 3000.0


def test_sugo_catalog_is_stable_and_matches_the_map():
    mapa = Mapa.cargar(PISTA / "mapa.json")
    cat = cv.Catalogo.desde_mapa(mapa)
    assert 12 <= len(cat.curvas) <= 16
    ids = [c.id for c in cat.curvas]
    assert ids == list(range(1, len(ids) + 1)) and [c.s_apice for c in cat.curvas] == sorted(c.s_apice for c in cat.curvas)
    guardado = cv.catalogo_de_pista(PISTA)
    assert guardado is not None and [(c.id, c.sentido, c.s_apice) for c in guardado.curvas] == [(c.id, c.sentido, c.s_apice) for c in cat.curvas]  # curvas.json está al día


def test_catalog_of_a_log_uses_the_track_in_the_header(tmp_path):
    log = tmp_path / "a.jsonl"
    log.write_text(json.dumps({"type": "session", "track": "SUGO_GP"}) + "\n", encoding="utf-8")
    cat = cv.catalogo_de_log(log)
    assert cat is not None and len(cat.curvas) >= 12
    log.write_text(json.dumps({"type": "session", "track": "NO_EXISTE"}) + "\n", encoding="utf-8")
    assert cv.catalogo_de_log(log) is None
