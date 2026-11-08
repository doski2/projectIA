"""Tests de `verificar_limite.py` con un log sintético sobre un mapa recto."""

import json

import numpy as np

from circuito_virtual.src.bordes_logs import LEFT_WHEELS, RIGHT_WHEELS, SEMIVIA_M
from circuito_virtual.src.mapa import Mapa
from video_vuelta.src import verificar_limite as vl


def _mapa_recto(longitud=600.0, paso=2.0):
    s = np.arange(0.0, longitud, paso)
    return Mapa("recto", longitud, s, np.zeros_like(s), np.zeros_like(s), s.copy())


def _log(tmp_path, n_de_t, borde_izq, borde_dcha, desvio_m=0.0):
    """Coche a 20 m/s por el eje de la pista con n(t); el terreno de cada lado sale «fuera» cuando su rueda pasa del borde (más `desvio_m`)."""
    ruta = tmp_path / "log.jsonl"
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "session"}) + "\n")
        for k in range(1500):
            t = k / 60.0
            n = n_de_t(t)
            izq_fuera = (n - SEMIVIA_M) < borde_izq + desvio_m
            dcha_fuera = (n + SEMIVIA_M) > borde_dcha - desvio_m
            terr = [7 if izq_fuera else 0, 7 if dcha_fuera else 0, 7 if izq_fuera else 0, 7 if dcha_fuera else 0]  # 7 = hierba (fuera); el 10, el piano, es superficie legal
            f.write(json.dumps({"type": "tick", "t_s": t, "lap_distance": 20.0 * t, "speed_kmh": 72.0,
                                "vehicle": {"position": [n, 0.0, 20.0 * t], "orientation": [0, 0, 0], "terrain": terr}}) + "\n")
    return ruta


def _bordes(mapa, izq=-5.0, dcha=5.0):
    return Mapa("b", mapa.longitud_m, mapa.s.copy(), mapa.x.copy(), mapa.y.copy(), mapa.z.copy(),
                np.full(mapa.n_puntos, izq), np.full(mapa.n_puntos, dcha), mapa.sup_izq.copy(), mapa.sup_dcha.copy(), {})


def test_cruces_sin_error_cuando_el_limite_es_correcto(tmp_path):
    mapa = _mapa_recto()
    lim = _bordes(mapa)
    ruta = _log(tmp_path, lambda t: 4.6 * np.sin(2 * np.pi * t / 6.0), -5.0, 5.0)  # zigzag que cruza los dos bordes
    d = vl.leer(ruta)
    izq = vl.cruces(d, mapa, LEFT_WHEELS, -1.0, lim.borde_izq)
    dcha = vl.cruces(d, mapa, RIGHT_WHEELS, 1.0, lim.borde_dcha)
    assert len(izq) >= 6 and len(dcha) >= 6
    assert {c["sentido"] for c in izq} == {"saliendo", "entrando"}
    assert abs(np.median([c["error"] for c in izq])) < 0.15 and abs(np.median([c["error"] for c in dcha])) < 0.15


def test_detecta_un_limite_mal_medido(tmp_path):
    mapa = _mapa_recto()
    lim = _bordes(mapa)
    # el juego marca «fuera» 0,3 m antes de lo que dice el vídeo en los dos lados
    ruta = _log(tmp_path, lambda t: 4.6 * np.sin(2 * np.pi * t / 6.0), -5.0, 5.0, desvio_m=0.3)
    d = vl.leer(ruta)
    e_izq = np.median([c["error"] for c in vl.cruces(d, mapa, LEFT_WHEELS, -1.0, lim.borde_izq)])
    e_dcha = np.median([c["error"] for c in vl.cruces(d, mapa, RIGHT_WHEELS, 1.0, lim.borde_dcha)])
    assert 0.2 < e_izq < 0.45 and -0.45 < e_dcha < -0.2  # el límite del vídeo está 0,3 m más afuera que el real


def test_el_rebote_no_cuenta_dos_veces(tmp_path):
    mapa = _mapa_recto()
    lim = _bordes(mapa)
    ruta = _log(tmp_path, lambda t: 4.15 + 0.02 * np.sin(2 * np.pi * t * 12.0) if 2.0 < t < 2.5 else 0.0, -5.0, 5.0)  # roza el borde derecho 0,5 s y oscila
    d = vl.leer(ruta)
    assert len(vl.cruces(d, mapa, RIGHT_WHEELS, 1.0, lim.borde_dcha)) <= 4


def test_main_imprime_resumen(tmp_path, capsys):
    mapa = _mapa_recto()
    ruta_mapa = tmp_path / "mapa.json"
    mapa.guardar(ruta_mapa)
    ruta_b = tmp_path / "bordes.json"
    _bordes(mapa).guardar(ruta_b)
    ruta = _log(tmp_path, lambda t: 4.6 * np.sin(2 * np.pi * t / 6.0), -5.0, 5.0)
    assert vl.main([str(ruta), "--bordes", str(ruta_b), "--mapa", str(ruta_mapa)]) == 0
    salida = capsys.readouterr().out
    assert "== izq" in salida and "== dcha" in salida and "saliendo" in salida
