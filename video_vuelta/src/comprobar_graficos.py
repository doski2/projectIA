"""Comprueba que los ajustes gráficos del juego son los acordados para grabar (D2 de docs/DECISIONES.md).

Uso:
    python video_vuelta/src/comprobar_graficos.py                      # compara el XML del juego con el perfil
    python video_vuelta/src/comprobar_graficos.py --guardar-perfil      # fija el XML actual como perfil de referencia
    python video_vuelta/src/comprobar_graficos.py --captura <video.mp4> # además, la captura debe medir lo que dice el perfil
    python video_vuelta/src/comprobar_graficos.py --copiar-a <carpeta>  # deja una copia del XML (para el manifiesto)

El juego solo reescribe `graphicsconfigdx11.xml` al cerrarse: lo que se lee es lo de la última vez que se cerró,
así que hay que cerrar el juego tras cambiar algo en el menú. Se ignora `adapter` (el juego lo reescribe a 0 siempre)
y `Build`. Sale con código 1 si algo no coincide con el perfil.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

XML_JUEGO = Path.home() / "Documents" / "Project CARS 2" / "graphicsconfigdx11.xml"
PERFIL = Path(__file__).resolve().parents[1] / "perfiles" / "graficos.json"
IGNORADOS = {"name", "build", "version"}  # propiedades que no son ajustes (el atributo `adapter` también se ignora)


def leer_graficos(ruta: Path) -> dict[str, str]:
    """Todos los atributos de `<data class="GraphicConfigData">`, con el nombre en minúsculas, salvo los ignorados."""
    raiz = ET.parse(ruta).getroot()
    datos = next((d for d in raiz.iter("data") if d.get("class") == "GraphicConfigData"), None)
    if datos is None:
        raise ValueError(f"{ruta}: no tiene un bloque data class=GraphicConfigData")
    salida: dict[str, str] = {}
    for prop in datos.findall("prop"):
        if (prop.get("name") or "").lower() in IGNORADOS:
            continue
        for clave, valor in prop.attrib.items():
            clave = clave.lower()
            if clave in {"name", "adapter"}:
                continue
            salida[clave] = valor
    return salida


def comparar(actual: dict[str, str], perfil: dict[str, str]) -> list[tuple[str, str | None, str | None]]:
    """(ajuste, valor del perfil, valor actual) de cada ajuste que no coincide o falta en alguno de los dos."""
    return [
        (k, perfil.get(k), actual.get(k))
        for k in sorted(set(actual) | set(perfil))
        if perfil.get(k) != actual.get(k)
    ]


def resolucion_esperada(perfil: dict[str, str]) -> tuple[int, int]:
    return int(perfil["width"]), int(perfil["height"])


def medir_captura(ruta: str) -> tuple[int, int] | None:
    import cv2

    cap = cv2.VideoCapture(ruta, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        return None
    medida = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return medida


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--xml", type=Path, default=XML_JUEGO)
    ap.add_argument("--perfil", type=Path, default=PERFIL)
    ap.add_argument("--guardar-perfil", action="store_true", help="escribe el XML actual como perfil de referencia")
    ap.add_argument("--captura", help="vídeo cuya resolución debe coincidir con el perfil")
    ap.add_argument("--copiar-a", type=Path, help="carpeta donde dejar una copia del XML")
    args = ap.parse_args(argv)

    actual = leer_graficos(args.xml)
    if args.guardar_perfil:
        args.perfil.parent.mkdir(parents=True, exist_ok=True)
        args.perfil.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Perfil guardado en {args.perfil} ({len(actual)} ajustes)")
        return 0
    if not args.perfil.exists():
        print(f"No hay perfil en {args.perfil}: usa --guardar-perfil con el juego ya cerrado y bien configurado")
        return 1
    perfil = json.loads(args.perfil.read_text(encoding="utf-8"))

    if args.copiar_a:
        args.copiar_a.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.xml, args.copiar_a / args.xml.name)

    fallos = 0
    diferencias = comparar(actual, perfil)
    for ajuste, esperado, hoy in diferencias:
        print(f"DISTINTO  {ajuste}: perfil {esperado}, XML {hoy}")
        fallos += 1
    if args.captura:
        medida = medir_captura(args.captura)
        esperada = resolucion_esperada(perfil)
        if medida is None:
            print(f"NO SE ABRE  {args.captura}")
            fallos += 1
        elif medida != esperada:
            print(f"CAPTURA  mide {medida[0]}x{medida[1]}, el perfil dice {esperada[0]}x{esperada[1]}")
            fallos += 1
        else:
            print(f"Captura {medida[0]}x{medida[1]}: bien")
    if fallos:
        return 1
    print(f"Gráficos bien: {len(actual)} ajustes iguales al perfil")
    return 0


if __name__ == "__main__":
    sys.exit(main())
