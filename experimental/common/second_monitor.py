"""Lector de las vueltas que graba Second Monitor (la app del segundo monitor) y cruce con nuestro log.

Second Monitor guarda cada vuelta cerrada en `Documents\\SecondMonitor\\Telemetry\\Recent\\<aa-mm-dd-hh-mm>-<pista>-<sesión>-<guid>\\`: un `_Session.xml` y un `.zLap` por vuelta
(gzip de un protobuf, clase `LapTelemetryDto` de la app: 1 resumen, 2 fotogramas, 3 versión). Este módulo lee solo lo que necesitamos, con los números de campo de la app
(código abierto, MIT, gitlab.com/winzarten/SecondMonitor), y no la ejecuta.

Lo que aporta frente a nuestro log (UDP): las temperaturas izquierda / centro / derecha de cada goma (con resolución de 1 °C; el UDP las da a 0) y la temperatura de la capa
interior. Slip y carga por rueda salen a 0 en PCars 2 y no se leen. La vuelta 1 con la salida parada no se graba.

Uso:
    python experimental/common/second_monitor.py                      # la última sesión de la app
    python experimental/common/second_monitor.py --log PCARS2-AI/logs/learning/<ts>_sugo_gp_l1_linea.jsonl   # la sesión de la app que corresponde a ese log
    python experimental/common/second_monitor.py --desde 480 --hasta 540   # además, cada vuelta entre esas distancias (m)
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import struct
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple
from xml.etree import ElementTree

RUEDAS = ("FL", "FR", "RL", "RR")  # el orden de `Wheels` en la app: FrontLeft, FrontRight, RearLeft, RearRight
RAIZ_POR_DEFECTO = Path.home() / "Documents" / "SecondMonitor" / "Telemetry" / "Recent"
SUFIJO_VUELTA = ".zLap"

Campo = Tuple[int, int, Any]  # número de campo, tipo de cable, valor


# ── protobuf a pelo ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _varint(b: bytes, i: int) -> Tuple[int, int]:
    r = s = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7F) << s
        if not x & 0x80:
            return r, i
        s += 7


def campos(b: bytes) -> Iterator[Campo]:
    """Recorre un mensaje protobuf: (campo, tipo de cable, valor). El tipo 1 se devuelve como double, el 5 como float, el 2 como bytes."""
    i = 0
    while i < len(b):
        k, i = _varint(b, i)
        f, w = k >> 3, k & 7
        if w == 0:
            v, i = _varint(b, i)
        elif w == 1:
            v = struct.unpack_from("<d", b, i)[0]
            i += 8
        elif w == 5:
            v = struct.unpack_from("<f", b, i)[0]
            i += 4
        elif w == 2:
            n, i = _varint(b, i)
            v = b[i:i + n]
            i += n
        else:
            raise ValueError(f"tipo de cable {w} no soportado")
        yield f, w, v


def _num(b: bytes, campo: int = 1, defecto: float = 0.0) -> float:
    """Primer double del campo `campo` de un mensaje (las magnitudes con unidad de la app son mensajes de un solo campo: Velocity, Distance, Temperature…)."""
    for f, w, v in campos(b):
        if f == campo and w == 1:
            return float(v)
    return defecto


def _cantidad(b: bytes) -> float:
    """`OptimalQuantity<T>`: el campo 1 es el valor actual, que a su vez es un mensaje de un solo double."""
    for f, w, v in campos(b):
        if f == 1 and w == 2:
            return _num(v)
    return 0.0


# ── lectura de un fotograma ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _rueda(b: bytes) -> Dict[str, float]:
    r: Dict[str, float] = {}
    for f, w, v in campos(b):
        if f == 1 and w == 1:
            r["rps"] = float(v)
        elif f == 2:
            r["susp_m"] = _num(v)
        elif f == 3:
            r["altura_m"] = _num(v)
        elif f == 4:
            r["freno_c"] = _cantidad(v)
        elif f == 5:
            r["presion_kpa"] = _cantidad(v)
        elif f == 7:
            r["desgaste"] = _num(v)
        elif f == 10:
            r["izq_c"] = _cantidad(v)
        elif f == 11:
            r["dcha_c"] = _cantidad(v)
        elif f == 12:
            r["centro_c"] = _cantidad(v)
        elif f == 13:
            r["capa_c"] = _cantidad(v)
    return r


def _coche(b: bytes, s: Dict[str, Any]) -> None:
    for f, w, v in campos(b):
        if f == 1:
            ruedas = [_rueda(x) for ff, ww, x in campos(v) if 1 <= ff <= 4 and ww == 2]
            s["ruedas"] = dict(zip(RUEDAS, ruedas))
        elif f == 5:
            s["acel"] = tuple(_num(v, k) for k in (1, 2, 3))
        elif f == 8 and w == 2:
            s["marcha"] = v.decode("utf-8", "replace")
        elif f == 9 and w == 0:
            s["rpm"] = int(v)


def _jugador(b: bytes, s: Dict[str, Any]) -> None:
    for f, w, v in campos(b):
        if f == 9 and w == 1:
            s["dist_m"] = float(v)
        elif f == 10:
            _coche(v, s)
        elif f == 11:
            xyz = [_num(x) for ff, ww, x in sorted((c for c in campos(v) if c[1] == 2), key=lambda c: c[0])]
            if len(xyz) == 3:
                s["pos"] = tuple(xyz)
        elif f == 12:
            s["v_ms"] = _num(v)


def fotograma(b: bytes) -> Dict[str, Any]:
    """Un `TimedTelemetrySnapshot`: tiempo de vuelta, distancia, velocidad, pedales, volante, ruedas y clima."""
    s: Dict[str, Any] = {}
    for f, w, v in campos(b):
        if f == 100:  # el tiempo de vuelta va en el mensaje de la clase hija
            s["t_s"] = _num(v)
        elif f == 2:
            _jugador(v, s)
        elif f == 3:
            for ff, ww, x in campos(v):
                if ff == 1:
                    s["aire_c"] = _num(x)
                elif ff == 2:
                    s["pista_c"] = _num(x)
        elif f == 4:
            for ff, ww, x in campos(v):
                if ww == 1 and ff in (1, 2, 4):
                    s[{1: "freno", 2: "gas", 4: "volante"}[ff]] = float(x)
    return s


def leer_vuelta(ruta: Path) -> List[Dict[str, Any]]:
    """Fotogramas de un `.zLap` (≈ 42 por segundo). Admite el archivo ya descomprimido."""
    datos = Path(ruta).read_bytes()
    if datos[:2] == b"\x1f\x8b":
        datos = gzip.decompress(datos)
    return [fotograma(v) for f, w, v in campos(datos) if f == 2 and w == 2]


# ── sesiones ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def inicio_de(carpeta: Path) -> Optional[datetime]:
    """Hora local de inicio de una sesión, del nombre de su carpeta (`aa-mm-dd-hh-mm-…`)."""
    m = re.match(r"(\d\d)-(\d\d)-(\d\d)-(\d\d)-(\d\d)-", carpeta.name)
    if not m:
        return None
    aa, mm, dd, hh, mi = (int(x) for x in m.groups())
    return datetime(2000 + aa, mm, dd, hh, mi)


def sesiones(raiz: Path = RAIZ_POR_DEFECTO) -> List[Path]:
    """Carpetas de sesión, de la más antigua a la más reciente."""
    if not raiz.is_dir():
        return []
    con_hora = [(inicio_de(p), p) for p in raiz.iterdir() if p.is_dir()]
    return [p for h, p in sorted((x for x in con_hora if x[0] is not None), key=lambda x: x[0])]  # type: ignore[type-var]


def tiempos_de_sesion(carpeta: Path) -> Dict[int, float]:
    """{vuelta: tiempo en s} del `_Session.xml` de una sesión de la app."""
    try:
        raiz = ElementTree.parse(Path(carpeta) / "_Session.xml").getroot()
    except (OSError, ElementTree.ParseError):
        return {}
    out: Dict[int, float] = {}
    for e in raiz.iter("LapSummaryDto"):
        try:
            out[int(e.get("LapNumber", ""))] = float(e.get("LapTimeSeconds", ""))
        except ValueError:
            continue
    return out


def tiempos_de_log(log: Path) -> List[float]:
    """Tiempos de las vueltas cerradas de nuestro log (registros `lap`)."""
    out: List[float] = []
    with open(log, encoding="utf-8") as fh:
        for linea in fh:
            if '"type": "lap"' not in linea:
                continue
            d = json.loads(linea)
            if d.get("type") == "lap" and isinstance(d.get("lap_time_s"), (int, float)):
                out.append(float(d["lap_time_s"]))
            for x in d.get("laps", []) if isinstance(d.get("laps"), list) else []:
                if isinstance(x.get("lap_time_s"), (int, float)):
                    out.append(float(x["lap_time_s"]))
    return out


def sesion_de_log(log: Path, raiz: Path = RAIZ_POR_DEFECTO, antes_min: float = 30.0, despues_min: float = 20.0, tol_s: float = 0.15) -> Optional[Path]:
    """La sesión de la app que corresponde a nuestro log.

    Candidatas: las que empiezan entre `antes_min` minutos antes y `despues_min` después del arranque del log (`session.ts`, UTC; la app arranca su sesión al entrar en la pista,
    que puede ser antes de lanzar el comando). Entre ellas gana la que más tiempos de vuelta comparte con el log (diferencia ≤ `tol_s`); sin coincidencias, la que empieza más cerca.
    """
    with open(log, encoding="utf-8") as fh:
        ts = json.loads(fh.readline()).get("ts")
    if not ts:
        return None
    inicio_log = datetime.fromisoformat(ts).astimezone().replace(tzinfo=None)  # a hora local de este equipo, sin zona
    propios = tiempos_de_log(log)
    mejor: Optional[Tuple[int, float, Path]] = None  # (coincidencias, -distancia en minutos, carpeta)
    for p in sesiones(raiz):
        h = inicio_de(p)
        assert h is not None
        d = (h - inicio_log).total_seconds() / 60.0
        if not -antes_min <= d <= despues_min:
            continue
        ajenos = list(tiempos_de_sesion(p).values())
        coincide = sum(1 for t in ajenos if any(abs(t - u) <= tol_s for u in propios))
        clave = (coincide, -abs(d))
        if mejor is None or clave > mejor[:2]:
            mejor = (coincide, -abs(d), p)
    return mejor[2] if mejor else None


def leer_sesion(carpeta: Path) -> Dict[int, List[Dict[str, Any]]]:
    """{número de vuelta: fotogramas}. El número sale del nombre del archivo (`<piloto>-<vuelta>--<guid>.zLap`)."""
    out: Dict[int, List[Dict[str, Any]]] = {}
    for f in sorted(Path(carpeta).glob("*" + SUFIJO_VUELTA)):
        m = re.match(r".+?-(\d+)--", f.name)
        if m:
            out[int(m.group(1))] = leer_vuelta(f)
    return out


# ── resúmenes ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _media(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def temperaturas_por_rueda(frames: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Tuple[float, float, float]]]:
    """Por rueda y zona (izq, centro, dcha, capa, freno): (mínimo, media, máximo) de la vuelta. «izq» y «dcha» son las del propio neumático, no las del coche."""
    out: Dict[str, Dict[str, Tuple[float, float, float]]] = {}
    for w in RUEDAS:
        out[w] = {}
        for z in ("izq_c", "centro_c", "dcha_c", "capa_c", "freno_c"):
            xs = [fr["ruedas"][w][z] for fr in frames if w in fr.get("ruedas", {}) and z in fr["ruedas"][w]]
            if xs:
                out[w][z] = (min(xs), _media(xs), max(xs))
    return out


def tramo(frames: Sequence[Dict[str, Any]], desde_m: float, hasta_m: float) -> List[Dict[str, Any]]:
    """Fotogramas con la distancia de vuelta entre `desde_m` y `hasta_m`."""
    return [f for f in frames if desde_m <= f.get("dist_m", -1.0) <= hasta_m]


def _imprimir_resumen(carpeta: Path, vueltas: Dict[int, List[Dict[str, Any]]]) -> None:
    print(f"Sesión de Second Monitor: {carpeta.name}")
    for n, frames in sorted(vueltas.items()):
        t = max((f.get("t_s", 0.0) for f in frames), default=0.0)
        pista = _media([f["pista_c"] for f in frames if "pista_c" in f])
        print(f"\nvuelta {n}: {len(frames)} fotogramas, {t:.2f} s, pista {pista:.0f} °C")
        print(f"  {'':3} {'izq':>6} {'centro':>7} {'dcha':>6} {'capa':>6} {'freno':>6}   (media por vuelta, °C)")
        for w, zonas in temperaturas_por_rueda(frames).items():
            fila = " ".join(f"{zonas[z][1]:6.1f}" if z in zonas else f"{'-':>6}" for z in ("izq_c", "centro_c", "dcha_c", "capa_c", "freno_c"))
            print(f"  {w:3} {fila}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--log", type=Path, help="nuestro log: busca la sesión de la app que le corresponde (si no, la última)")
    ap.add_argument("--raiz", type=Path, default=RAIZ_POR_DEFECTO, help="carpeta «Recent» de Second Monitor")
    ap.add_argument("--desde", type=float, help="distancia de vuelta inicial (m) para el detalle por vuelta")
    ap.add_argument("--hasta", type=float, help="distancia de vuelta final (m)")
    a = ap.parse_args(argv)
    carpeta = sesion_de_log(a.log, a.raiz) if a.log else (sesiones(a.raiz) or [None])[-1]
    if carpeta is None:
        print("No hay ninguna sesión de Second Monitor que corresponda.", file=sys.stderr)
        return 1
    vueltas = leer_sesion(carpeta)
    _imprimir_resumen(carpeta, vueltas)
    if a.desde is not None and a.hasta is not None:
        for n, frames in sorted(vueltas.items()):
            fs = tramo(frames, a.desde, a.hasta)
            if not fs:
                continue
            print(f"\nvuelta {n}, {a.desde:.0f}-{a.hasta:.0f} m (cada 4 fotogramas): dist  v km/h  gas freno volante | RPS FL FR RL RR")
            for f in fs[::4]:
                r = f.get("ruedas", {})
                print(f"  {f.get('dist_m', 0):7.1f} {f.get('v_ms', 0) * 3.6:6.1f} {f.get('gas', 0):5.2f} {f.get('freno', 0):5.2f} {f.get('volante', 0):6.2f} | "
                      + " ".join(f"{r.get(w, {}).get('rps', 0):6.1f}" for w in RUEDAS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
