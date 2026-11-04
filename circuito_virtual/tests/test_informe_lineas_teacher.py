"""Tests de `informe_lineas_teacher.py`: indicadores de un log A2.0 sintético y selección de sesiones."""

import json
from pathlib import Path

import pytest

from circuito_virtual.src import informe_lineas_teacher as il


def _log(ruta: Path, experimento: str, banda: float, cte: float, terreno=(1, 1, 1, 1), lluvia: int = 0) -> Path:
    cab = {"type": "session", "reference": r"C:\x\sugo_optima_a1mu9c12.json", "speed_band_kmh": banda, "experiment": experimento, "git": "abc1234"}
    lineas = [json.dumps(cab), json.dumps({"type": "conditions", "t_s": 1.0, "rain": lluvia})]
    t = 0.0
    for vuelta in (1, 2, 3):
        for d in range(0, 3560, 10):
            lineas.append(json.dumps({"type": "tick", "lap": vuelta, "lap_distance": float(d), "t_s": t, "signed_cte": cte if 400 <= d <= 600 else 0.1,
                                      "speed_kmh": 100.0, "vehicle": {"terrain": list(terreno)}}))
            t += 0.3
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return ruta


def test_resumen_sesion_saca_vuelta_cte_por_zona_y_ticks_fuera(tmp_path):
    from pcars2_surface import RACING_TERRAIN_IDS

    fuera = next(i for i in range(200) if i not in RACING_TERRAIN_IDS)
    dentro = next(iter(RACING_TERRAIN_IDS))
    r = il.resumen_sesion(_log(tmp_path / "20260101T000000Z_sugo_gp_l1_linea.jsonl", "a2_x", 125.0, -2.0, terreno=(dentro, fuera, dentro, dentro)))
    assert r["linea"] == "sugo_optima_a1mu9c12" and r["banda"] == 125.0 and r["vueltas"] == 2
    assert r["cte_max"] == pytest.approx(2.0) and r["zonas"]["S 400-600 m"] == pytest.approx(2.0) and r["zonas"]["2680-2870 m"] == pytest.approx(0.1)
    assert r["vuelta_s"] == pytest.approx(3559 / 10 * 0.3 - 0.0, abs=0.5)
    assert r["fuera"] == 3 * 356  # una rueda fuera en todos los ticks, también en la vuelta de salida
    assert il.resumen_sesion(_log(tmp_path / "b_sugo_gp_l1_linea.jsonl", "a2_x", 125.0, 0.2))["fuera"] == 0


def test_sesiones_solo_toma_a2_y_la_banda_pedida(tmp_path):
    _log(tmp_path / "20260101T000001Z_sugo_gp_l1_linea.jsonl", "a2_x", 125.0, 0.3)
    _log(tmp_path / "20260101T000002Z_sugo_gp_l1_linea.jsonl", "a1_frenar_x", 125.0, 0.3)
    _log(tmp_path / "20260101T000003Z_sugo_gp_l1_linea.jsonl", "a2_lenta", 80.0, 0.3)
    s = il.sesiones(100.0, tmp_path)
    assert [x["experimento"] for x in s] == ["a2_x"]
    assert len(il.sesiones(70.0, tmp_path)) == 2


def test_seco_y_mojado_no_se_mezclan(tmp_path):
    _log(tmp_path / "20260101T000001Z_sugo_gp_l1_linea.jsonl", "a2_seco", 125.0, 0.3)
    _log(tmp_path / "20260101T000002Z_sugo_gp_l1_linea.jsonl", "a2_mojado_x", 100.0, 0.3, lluvia=153)
    assert [x["experimento"] for x in il.sesiones(0.0, tmp_path)] == ["a2_seco"]
    m = il.sesiones(0.0, tmp_path, mojado=True)
    assert [x["experimento"] for x in m] == ["a2_mojado_x"] and m[0]["mojado"] and m[0]["lluvia"] == 153
