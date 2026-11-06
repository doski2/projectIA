import json
import re
from types import SimpleNamespace

from experimental.common import informe_zoom


def _ticks(vueltas=3, con_cte=True):
    out = []
    for lap in range(1, vueltas + 1):
        for i in range(2000):
            t = {"lap": lap, "lap_distance": i * 0.5, "speed_kmh": 100 + lap + (i % 50) * 0.1}
            if con_cte:
                t.update({"signed_cte": 0.1 * lap, "steering": 0.05, "throttle": 0.8, "brake": 0.0})
            out.append(t)
    return out


def _datos(*args, **kwargs):
    datos = informe_zoom.datos_zoom(*args, **kwargs)
    assert datos is not None
    return datos


def _cat():
    curvas = [SimpleNamespace(id=1, s_ini=100.0, s_fin=200.0, s_apice=150.0, sentido="izq"),
              SimpleNamespace(id=2, s_ini=900.0, s_fin=50.0, s_apice=980.0, sentido="der")]  # cruza la meta
    return SimpleNamespace(curvas=curvas, longitud_m=1000.0)


def test_datos_reducidos_a_un_punto_cada_paso():
    datos = _datos(_ticks(), _cat(), paso_m=1.5)
    assert [v["n"] for v in datos["vueltas"]] == [1, 2, 3]
    primera = datos["vueltas"][0]
    assert len(primera["d"]) < 2000 / 2  # 1000 m de vuelta a 1,5 m
    assert all(b > a for a, b in zip(primera["d"], primera["d"][1:]))
    assert [p["k"] for p in datos["paneles"]] == ["v", "dv", "cte", "vol", "ped"]
    assert datos["curvas"][1]["a"] > datos["curvas"][1]["b"]
    assert primera["ped"][0] == 0.8


def test_sin_cte_solo_velocidad_y_delta():
    datos = _datos(_ticks(con_cte=False))
    assert [p["k"] for p in datos["paneles"]] == ["v", "dv"]
    assert datos["curvas"] == []


def test_una_vuelta_no_tiene_delta():
    assert [p["k"] for p in _datos(_ticks(1))["paneles"]] == ["v", "cte", "vol", "ped"]


def test_ignora_ticks_sin_vuelta_y_distancia_que_retrocede():
    ticks = _ticks(2) + [{"speed_kmh": 5.0}, {"lap": 2, "lap_distance": 3.0, "speed_kmh": 1.0}]
    datos = _datos(ticks)
    assert datos["vueltas"][1]["d"][-1] == 999.0  # el tick que retrocede a 3 m no entra


def test_html_trae_datos_validos_y_no_cierra_el_script():
    html = informe_zoom.zoom_html(_ticks(), _cat())
    assert html.count("</script>") == 1 and "__DATOS__" not in html
    encontrado = re.search(r"var D=(\{.*?\});\nvar COL", html, re.S)
    assert encontrado is not None
    blob = encontrado.group(1)
    assert len(json.loads(blob)["vueltas"]) == 3
    for clave in ("cv_", "zcurva", "zref", "wheel"):
        assert clave in html


def test_sin_ticks_utiles_no_hay_seccion():
    assert informe_zoom.zoom_html([]) == ""
    assert informe_zoom.zoom_html([{"lap": 1, "lap_distance": 1.0, "speed_kmh": 1.0}]) == ""
