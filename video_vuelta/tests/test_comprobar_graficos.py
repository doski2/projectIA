"""Tests de `comprobar_graficos.py` con XML sintéticos."""

import json

from video_vuelta.src import comprobar_graficos as cg

XML = """<?xml version="1.0"?>
<Reflection>
    <class name="GraphicConfigData" base="BPersistent"><prop name="Build" type="U32" /></class>
    <data class="GraphicConfigData" id="0x423D7F40">
        <prop name="Name" data="" />
        <prop name="Build" data="1108" />
        <prop name="Version" version="2" />
        <prop name="Mode" adapter="{adapter}" width="1920" height="{alto}" refresh_num="60" refresh_dem="1" />
        <prop name="Windowed" windowed="0" />
        <prop name="TextureFilter" texturefilter="5" />
        <prop name="TrackDetailLevel" trackdetaillevel="{pista}" />
        <prop name="MotionblurLevel" motionblurLevel="0" />
    </data>
</Reflection>
"""


def _xml(tmp_path, nombre="g.xml", adapter=0, alto=1080, pista=3):
    ruta = tmp_path / nombre
    ruta.write_text(XML.format(adapter=adapter, alto=alto, pista=pista), encoding="utf-8")
    return ruta


def test_lee_atributos_en_minusculas_y_sin_ignorados(tmp_path):
    g = cg.leer_graficos(_xml(tmp_path))
    assert g == {
        "width": "1920", "height": "1080", "refresh_num": "60", "refresh_dem": "1",
        "windowed": "0", "texturefilter": "5", "trackdetaillevel": "3", "motionblurlevel": "0",
    }


def test_adapter_no_cuenta(tmp_path):
    a = cg.leer_graficos(_xml(tmp_path, "a.xml", adapter=0))
    b = cg.leer_graficos(_xml(tmp_path, "b.xml", adapter=1))
    assert cg.comparar(a, b) == []


def test_comparar_da_las_diferencias(tmp_path):
    perfil = cg.leer_graficos(_xml(tmp_path, "p.xml"))
    hoy = cg.leer_graficos(_xml(tmp_path, "h.xml", pista=0, alto=1200))
    assert cg.comparar(hoy, perfil) == [("height", "1080", "1200"), ("trackdetaillevel", "3", "0")]


def test_comparar_detecta_ajustes_que_faltan():
    assert cg.comparar({"a": "1"}, {"a": "1", "b": "2"}) == [("b", "2", None)]


def test_guardar_perfil_y_comprobar(tmp_path, capsys):
    xml = _xml(tmp_path)
    perfil = tmp_path / "perfiles" / "graficos.json"
    assert cg.main(["--xml", str(xml), "--perfil", str(perfil), "--guardar-perfil"]) == 0
    assert json.loads(perfil.read_text(encoding="utf-8"))["trackdetaillevel"] == "3"
    assert cg.main(["--xml", str(xml), "--perfil", str(perfil)]) == 0
    cambiado = _xml(tmp_path, "c.xml", pista=0)
    assert cg.main(["--xml", str(cambiado), "--perfil", str(perfil)]) == 1
    assert "trackdetaillevel: perfil 3, XML 0" in capsys.readouterr().out


def test_sin_perfil_falla(tmp_path):
    assert cg.main(["--xml", str(_xml(tmp_path)), "--perfil", str(tmp_path / "no.json")]) == 1


def test_copia_el_xml(tmp_path):
    xml = _xml(tmp_path)
    perfil = tmp_path / "p.json"
    cg.main(["--xml", str(xml), "--perfil", str(perfil), "--guardar-perfil"])
    destino = tmp_path / "manifiesto"
    assert cg.main(["--xml", str(xml), "--perfil", str(perfil), "--copiar-a", str(destino)]) == 0
    assert (destino / "g.xml").read_text(encoding="utf-8") == xml.read_text(encoding="utf-8")
