"""Tests de `pasillo_a_observaciones.py`: del mapa corregido a las observaciones que lee `linea_optima.py`."""
import numpy as np
import pytest

from circuito_virtual.src.bordes_logs import Observaciones
from circuito_virtual.src.linea_optima import pasillo_centro
from circuito_virtual.src.mapa import Mapa
from video_vuelta.src import pasillo_a_observaciones as po

N = 100


def _base():
    izq = np.full(N, -3.0)
    dcha = np.full(N, 4.0)
    return Observaciones(N, float(N), izq, izq.copy(), dcha, dcha.copy(), np.ones(N, dtype=int), ["base"], 0.85)


def _datos(**kw):
    d = {"borde_izq": [-5.0] * N, "borde_dcha": [6.0] * N, "sigma_izq": [0.1] * N, "sigma_dcha": [0.6] * N}
    d.update(kw)
    return d


def test_corrected_limits_become_measured_borders():
    obs = po.desde_mapa_corregido(_datos(), _base())
    assert np.allclose(obs.izq_dentro, -5.0) and np.allclose(obs.izq_fuera, -5.0) and np.allclose(obs.dcha_dentro, 6.0)
    b = obs.bordes()
    assert np.allclose(b["izq"], -5.0) and np.allclose(b["dcha"], 6.0)


def test_missing_metres_keep_what_the_base_had():
    d = _datos()
    d["borde_izq"][10] = None
    d["borde_dcha"][20] = None
    obs = po.desde_mapa_corregido(d, _base())
    assert obs.izq_dentro[10] == -3.0 and obs.dcha_dentro[20] == 4.0 and obs.izq_dentro[11] == -5.0


def test_prudente_pulls_in_only_the_uncertain_metres():
    obs = po.desde_mapa_corregido(_datos(), _base(), prudente_m=0.3)
    assert np.allclose(obs.izq_dentro, -5.0)            # σ 0,1: se queda
    assert np.allclose(obs.dcha_dentro, 5.7)            # σ 0,6: 0,3 m más cerca


def test_size_mismatch_is_rejected():
    with pytest.raises(ValueError):
        po.desde_mapa_corregido({"borde_izq": [0.0] * 5, "borde_dcha": [0.0] * 5}, _base())


def test_pasillo_centro_uses_the_corrected_border_with_semivia_and_margin():
    obs = po.desde_mapa_corregido(_datos(), _base())
    mapa = Mapa.desde_referencia({"track_name": "x", "track_length": float(N), "points": [{"d": float(i), "pos": [float(i), 0.0, 0.0]} for i in range(N)]})
    lo, hi = pasillo_centro(mapa, obs, 0.6, incluir_eje=False)
    assert np.allclose(lo[:3], -5.0 + 0.85 + 0.6) and np.allclose(hi[:3], 6.0 - 0.85 - 0.6)
