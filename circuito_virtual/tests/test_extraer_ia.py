"""Tests de la extracción de las vueltas de la IA a ritmo real (`extraer_ia.py`)."""

import json

from circuito_virtual.src import extraer_ia as ei


def _vuelta(num, tiempo, n=3600):
    pts = [{"d": float(i), "pos": [float(i), 5.0, 1.0], "spd": 30.0, "thr": 255, "brk": 0, "gear": 3, "rpm": 6000, "lacc": [1.0, 0.0, -2.0]} for i in range(n)]
    return {"lap_num": num, "lap_time": tiempo, "points": pts}


def test_only_complete_fast_laps_are_kept_and_columns_are_compact():
    datos = {"track_name": "SUGO_GP\x00", "track_length": 3567.01,
             "all_laps": [_vuelta(1, 97.7), _vuelta(2, 97.9), _vuelta(3, 105.4), _vuelta(4, 97.8, n=2700)]}
    out = ei.extraer(datos)
    assert out["pista"] == "SUGO_GP" and [v["vuelta"] for v in out["vueltas"]] == [1, 2]  # la lenta y la incompleta se descartan
    v = out["vueltas"][0]
    assert len(v["x"]) == len(v["v_ms"]) == len(v["a_lat"]) == 3600 and v["a_lat"][0] == 1.0 and v["a_long"][0] == -2.0
    assert "gas" not in v and "thr" not in v  # el gas de la IA vale siempre 255
    assert len(json.dumps(out)) < 3_000_000


def test_the_committed_file_has_the_14_real_pace_laps():
    import pytest

    if not ei.SALIDA.is_file():
        pytest.skip("archivo no generado")
    datos = json.loads(ei.SALIDA.read_text(encoding="utf-8"))
    tiempos = [v["tiempo_s"] for v in datos["vueltas"]]
    assert len(tiempos) == 14 and min(tiempos) == 97.746 and max(tiempos) < 98.5
