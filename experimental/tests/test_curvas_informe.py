import json

import numpy as np

from circuito_virtual.src import curvas as cv
from experimental.common import informe_c0 as ic
from experimental.common import pedales_sesion as ps
from experimental.common import resumen_sesion as rs


def _catalogo():
    k = np.zeros(3600)
    s = np.arange(3600.0)
    for pos, alto in ((500, -0.02), (1500, 0.02)):
        k += alto * np.exp(-0.5 * ((s - pos) / 20.0) ** 2)
    return cv.Catalogo(cv.detectar(k, 3600.0), 3600.0, "x")


def _ticks(cte_vuelta4=0.4):
    out = []
    for lap in (1, 2, 3, 4):
        for i in range(0, 3560, 5):
            malo = lap == 4 and 480 <= i <= 560
            out.append({"type": "tick", "lap": lap, "lap_distance": float(i), "speed_kmh": 80.0 if 450 <= i <= 560 else 120.0, "signed_cte": cte_vuelta4 if malo else 0.2,
                        "brake": 0.5 if 440 <= i <= 480 else 0.0, "throttle": 0.0, "steering": 0.0, "heading_err": 0.0, "gear": 2, "t_s": lap * 1000 + i / 30.0,
                        "vehicle": {"local_accel": [9.0 if 480 <= i <= 560 else 1.0, 0.0, 3.0], "local_velocity": [0.0, 0.0, -30.0], "yaw_rate": 0.0, "terrain": [0, 0, 0, 0],
                                    "tyre_rps": [10.0] * 4}})
    return out


def test_curve_table_reports_each_corner_and_lap_and_flags_the_bad_lap():
    cat = _catalogo()
    filas = ic.tabla_curvas(_ticks(2.5), cat)
    assert [f["curva"] for f in filas] == ["C1", "C2"]
    c1 = filas[0]["vueltas"]
    assert set(c1) == {1, 2, 3, 4}
    assert c1[1]["cte_max"] == 0.2 and c1[4]["cte_max"] == 2.5
    assert c1[1]["v_min"] == 80.0 and c1[1]["lat_max"] == 9.0 and c1[1]["freno_max"] == 0.5
    html = ic.curvas_html(filas)
    assert "C1" in html and "f9d6d6" in html and html.count("f9d6d6") == 1  # solo la celda mala (vuelta 4 de C1) en rojo
    assert ic.tabla_curvas(_ticks(), None) == [] and ic.curvas_html([]) == ""


def test_summary_lists_the_out_of_criterion_stretches_of_all_laps_with_the_corner_number(tmp_path, capsys, monkeypatch):
    cat = _catalogo()
    monkeypatch.setattr(rs, "_catalogo", lambda ruta: cat)
    log = tmp_path / "log.jsonl"
    log.write_text("\n".join(json.dumps(x) for x in [{"type": "session", "log_schema": 3, "track": "X"}] + _ticks(2.5)) + "\n", encoding="utf-8")
    assert rs.main([str(log), "--previsto", "100.0"]) == 0  # --vueltas 2 por defecto, pero el desvío de la vuelta 4 también se localiza
    salida = capsys.readouterr().out
    assert "vuelta 4" in salida and "[C1]" in salida


def test_braking_events_carry_the_number_of_the_corner_being_braked_for():
    cat = _catalogo()
    r = ps.analizar_vuelta([t for t in _ticks() if t["lap"] == 2], cat)
    assert r["frenadas"] == 1 and r["eventos"][0]["curva"] == "C1"
