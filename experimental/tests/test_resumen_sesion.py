"""Tests de `common/resumen_sesion.py` (V34): criterio de V19, cambios de marcha y vueltas sobre ticks sintéticos."""

import json

import numpy as np
import pytest

from experimental.common import resumen_sesion as rs


def _res(**curvas):
    return {"rectas": {"volante_rms": 0.01, "inversiones_100m": 0.2, "cte_rms": 0.1},
            "curvas": {"tasa": 0.1, "cte_max": 1.0, "deriva_max": 2.0, **curvas}}


def test_el_criterio_de_v19_marca_cada_linea_y_el_limite_es_inclusivo():
    filas = rs.evaluar(_res())
    assert len(filas) == 6 and all(f[4] for f in filas)
    malo = {f[1]: f[4] for f in rs.evaluar(_res(cte_max=2.27))}
    assert malo["cte_max"] is False and malo["deriva_max"] is True
    assert all(f[4] for f in rs.evaluar(_res(cte_max=1.8, deriva_max=4.0, tasa=0.2)))  # justo en el límite cumple


def test_el_criterio_sin_datos_de_un_ambito_no_cumple():
    filas = rs.evaluar({"rectas": None, "curvas": _res()["curvas"]})
    assert [f[4] for f in filas[:3]] == [False, False, False] and all(f[2] is None for f in filas[:3])


def _tick(t, gear, v, lap=1, d=0.0, brake=0.0):
    return {"type": "tick", "t_s": t, "gear": gear, "speed_kmh": v, "lap": lap, "lap_distance": d, "brake": brake, "throttle": 0.0,
            "signed_cte": 0.1, "steering": 0.0, "vehicle": {"local_velocity": [0.0, 0.0, -v / 3.6], "local_accel": [0.0, 0.0, 0.0], "yaw_rate": 0.0,
                                           "tyre_rps": [10.0, 10.0, 9.5, 9.5], "terrain": [0, 0, 0, 0], "car_flags": 2}}


def test_los_cambios_separan_subidas_y_bajadas_con_su_punto_muerto():
    ticks = []
    t = 7.0
    secuencia = [(2, 100)] * 10 + [(0, 100)] * 10 + [(3, 100)] * 20 + [(3, 90)] * 10 + [(0, 88)] * 12 + [(2, 86)] * 20
    for i, (g, v) in enumerate(secuencia):
        ticks.append(_tick(t + i / 60.0, g, v, d=float(i)))
    c = rs.cambios(ticks, [1])
    assert c["sube"]["n"] == 1 and c["baja"]["n"] == 1
    assert c["sube"]["neutro_s"] == pytest.approx(10 / 60.0, abs=0.02) and c["baja"]["neutro_s"] == pytest.approx(12 / 60.0, abs=0.02)


def test_las_vueltas_completas_dan_su_tiempo_y_las_incompletas_se_ignoran():
    ticks = []
    for lap, largo in ((1, 3560), (2, 3560), (3, 500)):
        for i in range(0, largo, 5):
            tk = _tick(float(i), 2, 90.0, lap=lap, d=float(i))
            tk["timing"] = {"game_time_s": 120.0 + lap}
            ticks.append(tk)
    out = rs.vueltas(ticks)
    assert [v["vuelta"] for v in out] == [1, 2] and out[1]["tiempo_s"] == pytest.approx(122.0)


def test_el_terreno_cuenta_los_ticks_con_ruedas_fuera():
    ticks = [_tick(i / 60.0, 2, 90.0) for i in range(30)]
    for t in ticks[:5]:
        t["vehicle"]["terrain"] = [7, 0, 7, 0]
    for t in ticks[5:8]:
        t["vehicle"]["terrain"] = [0, 0, 0, 7]
    r = rs.terreno(ticks)
    assert r == {"ticks": 30, "alguna_rueda_fuera": 8, "dos_o_mas": 5}


def test_el_resumen_completo_corre_sobre_un_log_escrito_en_disco(tmp_path, capsys):
    ticks = []
    for lap in (1, 2):
        for i in range(0, 3560, 5):
            tk = _tick(lap * 1000 + i / 30.0, 2, 90.0, lap=lap, d=float(i), brake=0.3 if 1000 < i < 1100 else 0.0)
            tk["timing"] = {"game_time_s": 100.0 + lap}
            ticks.append(tk)
    log = tmp_path / "log.jsonl"
    log.write_text(chr(10).join(json.dumps(x) for x in [{"type": "session", "log_schema": 2}] + ticks) + chr(10), encoding="utf-8")
    assert rs.main([str(log), "--previsto", "100.0"]) == 0
    out = capsys.readouterr().out
    assert "Criterio de volante" in out and "Vueltas" in out and "Terreno" in out
