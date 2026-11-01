"""Tests del extractor de bordes desde logs (`bordes_logs.py`, D1a) con una recta sintética de bordes conocidos."""

import json

import numpy as np
import pytest

from circuito_virtual.src import bordes_logs as bl
from circuito_virtual.src import mapa as mp

LARGO = 2000
BORDE_IZQ = -2.0  # n del borde izquierdo del asfalto
BORDE_DCHA = 2.5


def _mapa_recta():
    """Eje recto a lo largo de +x; la derecha es −z. Se hace cerrado con un lazo lejano para que `Mapa` lo acepte (solo se usa el tramo recto)."""
    pts = [(float(i), 0.0) for i in range(LARGO // 2)] + [(float(LARGO // 2 - i), 50.0) for i in range(LARGO // 2)]
    datos = {"track_name": "recta", "track_length": float(len(pts)), "points": [{"d": float(i), "pos": [x, 0.0, z]} for i, (x, z) in enumerate(pts)]}
    return mp.Mapa.desde_referencia(datos)


def _barrido(mapa, n_por_metro, semivia=bl.SEMIVIA_M):
    """Ticks de un coche que va a n = n_por_metro(s) por el tramo recto; las ruedas salen del asfalto más allá de los bordes."""
    s = np.arange(100.0, 900.0, 0.5)
    n = np.array([n_por_metro(v) for v in s])
    x, z = mapa.sn_a_xz(s, n)
    terr = np.zeros((len(s), 4), dtype=int)
    izq_fuera = (n - semivia) < BORDE_IZQ
    dcha_fuera = (n + semivia) > BORDE_DCHA
    terr[izq_fuera, 0] = 7
    terr[izq_fuera, 2] = 7
    terr[dcha_fuera, 1] = 7
    terr[dcha_fuera, 3] = 7
    return s, x, z, terr, np.full(len(s), 15.0)


def test_both_edges_are_found_where_the_car_crosses_them():
    m = _mapa_recta()
    obs = bl.Observaciones.vacia(m)
    # un coche que oscila de lado a lado, cruzando los dos bordes (rueda a rueda)
    s, x, z, terr, v = _barrido(m, lambda s: 2.0 * np.sin(s / 20.0) + 0.3)
    assert obs.agregar(m, s, x, z, terr, v) == len(s)
    b = obs.bordes()
    ok_i, ok_d = np.isfinite(b["izq"]), np.isfinite(b["dcha"])
    assert ok_i.any() and ok_d.any()
    assert np.nanmedian(b["izq"]) == pytest.approx(BORDE_IZQ, abs=0.25)
    assert np.nanmedian(b["dcha"]) == pytest.approx(BORDE_DCHA, abs=0.25)
    assert np.nanmax(np.abs(b["izq"] - BORDE_IZQ)) < 0.6 and np.nanmax(np.abs(b["dcha"] - BORDE_DCHA)) < 0.6


def test_where_the_car_never_left_the_asphalt_there_is_a_lower_bound_but_no_edge():
    m = _mapa_recta()
    obs = bl.Observaciones.vacia(m)
    s, x, z, terr, v = _barrido(m, lambda s: 0.5)  # va por el centro y no toca nada
    obs.agregar(m, s, x, z, terr, v)
    i = obs._bin(np.array([500.0]))[0]
    assert obs.izq_dentro[i] == pytest.approx(0.5 - bl.SEMIVIA_M, abs=0.02)  # el asfalto llega al menos hasta la rueda izquierda
    assert np.isnan(obs.izq_fuera[i]) and np.isnan(obs.bordes()["izq"][i])
    assert obs.cobertura()["borde_izq_medido"] == 0.0 and obs.cobertura()["asfalto_hasta_izq"] > 0.0


def test_slow_ticks_are_ignored():
    m = _mapa_recta()
    obs = bl.Observaciones.vacia(m)
    s, x, z, terr, v = _barrido(m, lambda s: 0.0)
    assert obs.agregar(m, s, x, z, terr, np.full(len(s), 0.5)) == 0 and obs.ticks.sum() == 0


def test_a_mapa_fills_only_the_measured_edges_and_records_the_assumed_half_track():
    m = _mapa_recta()
    obs = bl.Observaciones.vacia(m)
    obs.agregar(m, *_barrido(m, lambda s: 2.0 * np.sin(s / 20.0) + 0.3))
    nuevo = obs.a_mapa(m)
    assert np.isfinite(nuevo.borde_izq).any() and np.isnan(m.borde_izq).all()  # el mapa original no se modifica
    assert nuevo.meta["semivia_m"] == bl.SEMIVIA_M and 0.0 < np.isfinite(nuevo.borde_izq).mean() < 1.0 and 0.0 < np.isfinite(nuevo.borde_dcha).mean() < 1.0


def test_observations_round_trip_through_json_and_merge_more_logs():
    m = _mapa_recta()
    obs = bl.Observaciones.vacia(m)
    obs.agregar(m, *_barrido(m, lambda s: 0.5))
    back = bl.Observaciones.de_dict(json.loads(json.dumps(obs.a_dict())))
    assert np.allclose(back.izq_dentro, obs.izq_dentro, equal_nan=True, atol=1e-3) and (back.ticks == obs.ticks).all()
    back.agregar(m, *_barrido(m, lambda s: 2.0 * np.sin(s / 20.0) + 0.3))
    assert back.cobertura()["borde_izq_medido"] > obs.cobertura()["borde_izq_medido"]


def test_log_reader_skips_old_schema_and_reads_ticks(tmp_path):
    m = _mapa_recta()
    nuevo = tmp_path / "n.jsonl"
    cab = {"type": "session", "log_schema": 2}
    ticks = [{"type": "tick", "lap_distance": 300.0 + i, "speed_kmh": 54.0, "vehicle": {"position": [300.0 + i, 0.0, 1.0], "terrain": [0, 0, 0, 0]}} for i in range(50)]
    nuevo.write_text("\n".join(json.dumps(x) for x in [cab] + ticks), encoding="utf-8")
    viejo = tmp_path / "v.jsonl"
    viejo.write_text(json.dumps({"type": "session", "log_schema": 1}) + "\n" + json.dumps(ticks[0]), encoding="utf-8")
    assert [p.name for p in bl.logs_esquema_2(tmp_path)] == ["n.jsonl"]
    obs = bl.Observaciones.vacia(m)
    assert obs.agregar_log(m, nuevo) == 50 and obs.logs == ["n.jsonl"]


def test_the_html_report_is_generated_with_the_three_figures_and_the_coverage(tmp_path):
    from circuito_virtual.src import informe_mapa

    m = _mapa_recta()
    obs = bl.Observaciones.vacia(m)
    obs.agregar(m, *_barrido(m, lambda s: 2.0 * np.sin(s / 20.0) + 0.3))
    salida = informe_mapa.generar(m, obs, tmp_path / "informes" / "i.html")
    texto = salida.read_text(encoding="utf-8")
    assert "Mapa de recta" in texto and texto.count("data:image/png;base64,") == 3 and "borde izq medido" in texto
    assert informe_mapa.tramos(np.array([False, True, True, True, False]), 5.0, minimo_m=3.0) == [(1.0, 4.0)]


def test_logs_without_position_use_the_signed_cte_plus_the_reference_offset():
    m = _mapa_recta()
    obs = bl.Observaciones.vacia(m)
    s, x, z, terr, v = _barrido(m, lambda s: 2.0 * np.sin(s / 20.0) + 0.3)
    n_real = 2.0 * np.sin(s / 20.0) + 0.3
    n_ref = np.full(m.n_puntos, 0.4)  # la referencia de la sesión va 0,4 m a la derecha del eje del mapa
    assert obs.agregar_cte(m, s, n_real - 0.4, terr, v, n_ref) == len(s)  # el CTE es contra esa referencia
    b = obs.bordes()
    assert np.nanmedian(b["izq"]) == pytest.approx(BORDE_IZQ, abs=0.25) and np.nanmedian(b["dcha"]) == pytest.approx(BORDE_DCHA, abs=0.25)


def test_log_reader_uses_the_cte_when_there_is_no_position_and_a_reference_offset(tmp_path):
    m = _mapa_recta()
    ticks = [{"type": "tick", "lap_distance": 300.0 + i, "speed_kmh": 54.0, "signed_cte": 0.1, "vehicle": {"terrain": [0, 0, 0, 0]}} for i in range(40)]
    ruta = tmp_path / "sinpos.jsonl"
    ruta.write_text("\n".join(json.dumps(x) for x in [{"type": "session", "log_schema": 1, "reference_lap_s": 213.875}] + ticks), encoding="utf-8")
    assert bl.Observaciones.vacia(m).agregar_log(m, ruta) == 0  # sin referencia no se puede usar
    obs = bl.Observaciones.vacia(m)
    assert obs.agregar_log(m, ruta, np.zeros(m.n_puntos)) == 40
    assert [p.name for p in bl.logs_con_terreno(tmp_path)] == ["sinpos.jsonl"]
    otra = tmp_path / "otra_ref.jsonl"
    otra.write_text(json.dumps({"type": "session", "reference_lap_s": 97.746}) + "\n" + json.dumps(ticks[0]), encoding="utf-8")
    assert "otra_ref.jsonl" not in [p.name for p in bl.logs_con_terreno(tmp_path)]  # otra línea de referencia


def test_actualizar_anade_solo_los_logs_nuevos_y_amplia_el_asfalto_comprobado(tmp_path):
    m = _mapa_recta()
    carpeta = tmp_path / "learning"
    carpeta.mkdir()
    cab = {"type": "session", "log_schema": 2}

    def log(nombre, n):
        ticks = [{"type": "tick", "lap_distance": 300.0 + i, "speed_kmh": 54.0, "vehicle": {"position": [300.0 + i, 0.0, -n], "terrain": [0, 0, 0, 0]}} for i in range(50)]
        (carpeta / nombre).write_text("\n".join(json.dumps(x) for x in [cab] + ticks), encoding="utf-8")

    log("a.jsonl", 0.0)
    obs = bl.Observaciones.vacia(m)
    assert bl.actualizar(obs, m, [carpeta]) == ["a.jsonl"]
    centro = np.nanmax(obs.dcha_dentro[300:350])
    log("b.jsonl", 1.5)  # esta sesión pasó 1,5 m más a la derecha por el asfalto
    assert bl.actualizar(obs, m, [carpeta]) == ["b.jsonl"]  # a.jsonl ya estaba
    assert obs.logs == ["a.jsonl", "b.jsonl"]
    assert np.nanmax(obs.dcha_dentro[300:350]) == pytest.approx(centro + 1.5, abs=0.05)
    assert bl.actualizar(obs, m, [carpeta]) == []  # idempotente
