"""
Tests de las utilidades del dashboard (`monitor.py`).

El monitor lee el CSV de métricas mientras se entrena. Sus utilidades de
parseo (sfloat/sint), tendencia y detección del CSV más reciente deben ser
robustas frente a celdas vacías o valores no numéricos para no romper el
panel en mitad de una sesión larga.
"""

import os

import monitor
from monitor import (
    sfloat,
    sint,
    trend,
    sparkline,
    find_latest_csv,
    read_rows,
    ARROW_UP,
    ARROW_DOWN,
    ARROW_SAME,
)


# ---------------------------------------------------------------------------
# Parseo defensivo
# ---------------------------------------------------------------------------

def test_sfloat_valid_and_invalid():
    assert sfloat("1.5") == 1.5
    assert sfloat(None) == 0.0
    assert sfloat("") == 0.0
    assert sfloat("abc") == 0.0
    assert sfloat("nan") != sfloat("nan") or True  # nan se parsea; no debe lanzar


def test_sint_valid_and_invalid():
    assert sint("3") == 3
    assert sint("3.0") == 3
    assert sint(None) == 0
    assert sint("x") == 0
    assert sint("2048") == 2048


# ---------------------------------------------------------------------------
# Tendencias
# ---------------------------------------------------------------------------

def test_trend_no_previous():
    arrow, _ = trend(10.0, None)
    assert arrow == ARROW_SAME


def test_trend_higher_better():
    up, _ = trend(20.0, 10.0, higher_better=True)
    assert up == ARROW_UP
    down, _ = trend(5.0, 10.0, higher_better=True)
    assert down == ARROW_DOWN


def test_trend_lower_better():
    # Para métricas donde menos es mejor (p.ej. value_loss, std):
    # si el valor baja, la flecha apunta hacia abajo y se colorea de verde.
    arrow, color = trend(5.0, 10.0, higher_better=False)
    assert arrow == ARROW_DOWN
    assert color == "green"
    # si sube, flecha hacia arriba en rojo
    arrow_up, color_up = trend(15.0, 10.0, higher_better=False)
    assert arrow_up == ARROW_UP
    assert color_up == "red"


def test_trend_stable_within_threshold():
    arrow, _ = trend(100.0, 100.0, threshold=0.005)
    assert arrow == ARROW_SAME


# ---------------------------------------------------------------------------
# Sparkline
# ---------------------------------------------------------------------------

def test_sparkline_too_few_values():
    txt = sparkline([1.0])
    assert "─" in txt.plain


def test_sparkline_renders_blocks():
    txt = sparkline([0.0, 1.0, 2.0, 3.0, 4.0], width=5)
    # Debe producir caracteres de bloque, no fallar
    assert len(txt.plain) >= 1


# ---------------------------------------------------------------------------
# Lectura de CSV / detección del más reciente
# ---------------------------------------------------------------------------

def test_read_rows_missing_file_returns_empty(tmp_path):
    assert read_rows(os.path.join(str(tmp_path), "no_existe.csv")) == []


def test_read_rows_parses_header_and_rows(tmp_path):
    csv_path = os.path.join(str(tmp_path), "metricas.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("total_timesteps,ep_rew_mean\n")
        f.write("2048,100.5\n")
        f.write("4096,200.0\n")
    rows = read_rows(csv_path)
    assert len(rows) == 2
    assert rows[0]["total_timesteps"] == "2048"
    assert rows[1]["ep_rew_mean"] == "200.0"


def test_find_latest_csv_none_when_empty(tmp_path):
    assert find_latest_csv(str(tmp_path)) is None


def test_find_latest_csv_picks_most_recent(tmp_path):
    import time
    a_dir = os.path.join(str(tmp_path), "comboA")
    b_dir = os.path.join(str(tmp_path), "comboB")
    os.makedirs(a_dir)
    os.makedirs(b_dir)
    a = os.path.join(a_dir, "metricas.csv")
    b = os.path.join(b_dir, "metricas.csv")
    with open(a, "w") as f:
        f.write("x\n")
    time.sleep(0.05)
    with open(b, "w") as f:
        f.write("x\n")
    # b se escribió después → debe ser el más reciente
    assert find_latest_csv(str(tmp_path)) == b
