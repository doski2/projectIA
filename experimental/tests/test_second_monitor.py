"""Tests de `second_monitor.py`: lectura de un `.zLap` (protobuf comprimido) construido a mano y emparejamiento con nuestro log por hora."""

import gzip
import json
import struct
from datetime import datetime, timezone
from pathlib import Path

from experimental.common import second_monitor as sm


# ── mini codificador protobuf para fabricar los datos de prueba ───────────────────────────────────────────────────────────────────────────────────────────────
def _v(n: int) -> bytes:
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def _dbl(f: int, x: float) -> bytes:
    return _v(f << 3 | 1) + struct.pack("<d", x)


def _msg(f: int, body: bytes) -> bytes:
    return _v(f << 3 | 2) + _v(len(body)) + body


def _int(f: int, x: int) -> bytes:
    return _v(f << 3) + _v(x)


def _cant(valor: float) -> bytes:
    """`OptimalQuantity<T>`: campo 1 = valor actual (mensaje de un double), 2 = ideal, 3 = ventana."""
    return _msg(1, _dbl(1, valor)) + _msg(2, _dbl(1, 85.0)) + _msg(3, _dbl(1, 10.0))


def _rueda(rps: float, izq: float, centro: float, dcha: float, capa: float, freno: float) -> bytes:
    return (_dbl(1, rps) + _msg(2, _dbl(1, 0.07)) + _msg(4, _cant(freno)) + _msg(10, _cant(izq)) + _msg(11, _cant(dcha)) + _msg(12, _cant(centro)) + _msg(13, _cant(capa)))


def _fotograma(t: float, dist: float, v_ms: float, gas: float, ruedas) -> bytes:
    coche = _msg(1, b"".join(_msg(i + 1, _rueda(*r)) for i, r in enumerate(ruedas))) + _msg(5, _dbl(1, 1.5) + _dbl(2, 0.1) + _dbl(3, -4.0)) + _msg(8, b"2") + _int(9, 5400)
    jugador = _dbl(9, dist) + _msg(10, coche) + _msg(12, _dbl(1, v_ms)) + _msg(11, _msg(1, _dbl(1, 10.0)) + _msg(2, _dbl(1, 1.0)) + _msg(3, _dbl(1, -20.0)))
    return (_msg(100, _dbl(1, t)) + _msg(2, jugador) + _msg(3, _msg(1, _dbl(1, 14.0)) + _msg(2, _dbl(1, 21.0))) + _msg(4, _dbl(1, 0.0) + _dbl(2, gas) + _dbl(4, -0.3)))


RUEDAS_4 = [(80.0, 55.0, 57.0, 59.0, 58.0, 340.0), (86.0, 57.0, 56.0, 53.0, 56.0, 342.0), (79.0, 47.0, 48.0, 47.0, 49.0, 230.0), (80.0, 46.0, 47.0, 46.0, 48.0, 231.0)]


def _zlap(frames: int = 3) -> bytes:
    cuerpo = _msg(1, _int(1, 2)) + b"".join(_msg(2, _fotograma(0.1 * i, 500.0 + 10 * i, 22.0, 0.25 * i, RUEDAS_4)) for i in range(frames)) + _int(3, 2)
    return gzip.compress(cuerpo)


def test_a_lap_file_gives_its_frames_with_pedals_speed_distance_and_wheel_temperatures(tmp_path: Path):
    f = tmp_path / "doski2-3--abc.zLap"
    f.write_bytes(_zlap())
    frames = sm.leer_vuelta(f)
    assert len(frames) == 3
    fr = frames[1]
    assert fr["t_s"] == 0.1 and fr["dist_m"] == 510.0 and fr["v_ms"] == 22.0
    assert fr["gas"] == 0.25 and fr["volante"] == -0.3 and fr["marcha"] == "2" and fr["rpm"] == 5400
    assert fr["pista_c"] == 21.0 and fr["aire_c"] == 14.0 and fr["acel"] == (1.5, 0.1, -4.0) and fr["pos"] == (10.0, 1.0, -20.0)
    fl, rr = fr["ruedas"]["FL"], fr["ruedas"]["RR"]
    assert (fl["izq_c"], fl["centro_c"], fl["dcha_c"], fl["capa_c"], fl["freno_c"], fl["rps"]) == (55.0, 57.0, 59.0, 58.0, 340.0, 80.0)
    assert rr["izq_c"] == 46.0 and rr["rps"] == 80.0 and fl["susp_m"] == 0.07


def test_an_uncompressed_lap_file_also_reads(tmp_path: Path):
    f = tmp_path / "x.zLap"
    f.write_bytes(gzip.decompress(_zlap(2)))
    assert len(sm.leer_vuelta(f)) == 2


def test_temperature_summary_per_wheel_and_zone_and_distance_window(tmp_path: Path):
    f = tmp_path / "a.zLap"
    f.write_bytes(_zlap(5))
    frames = sm.leer_vuelta(f)
    t = sm.temperaturas_por_rueda(frames)
    assert t["FL"]["izq_c"] == (55.0, 55.0, 55.0) and t["FR"]["dcha_c"][1] == 53.0 and t["RL"]["freno_c"][2] == 230.0
    assert [x["dist_m"] for x in sm.tramo(frames, 510.0, 530.0)] == [510.0, 520.0, 530.0]


def _sesion(raiz: Path, nombre: str, vueltas=(2, 3)) -> Path:
    d = raiz / nombre
    d.mkdir(parents=True)
    for n in vueltas:
        (d / f"doski2-{n}--0e35d776-e3a1-4df9-a8fd-30acefb928b2.zLap").write_bytes(_zlap(2))
    return d


def test_session_of_a_log_is_the_one_that_starts_just_after_the_log_and_laps_are_numbered_from_the_file_name(tmp_path: Path):
    raiz = tmp_path / "Recent"
    antes = _sesion(raiz, "26-11-06-18-00-Sugo-Race-aaaa")
    dentro = _sesion(raiz, "26-11-06-19-29-Sugo-Race-bbbb", vueltas=(2, 3, 4))
    _sesion(raiz, "26-11-06-23-00-Sugo-Race-cccc")
    log = tmp_path / "log.jsonl"
    inicio_local = datetime(2026, 11, 6, 19, 28, 21)
    ts = inicio_local.astimezone(timezone.utc).isoformat()  # el log guarda UTC; la app, hora local de este equipo
    log.write_text(json.dumps({"type": "session", "ts": ts}) + "\n", encoding="utf-8")
    assert sm.sesion_de_log(log, raiz) == dentro != antes
    assert sorted(sm.leer_sesion(dentro)) == [2, 3, 4]
    assert sm.sesiones(raiz)[-1].name.startswith("26-11-06-23-00")
    log.write_text(json.dumps({"type": "session", "ts": datetime(2026, 11, 7, 9, 0).astimezone(timezone.utc).isoformat()}) + "\n", encoding="utf-8")
    assert sm.sesion_de_log(log, raiz) is None  # ninguna sesión de la app empieza en los 20 minutos siguientes


def test_main_prints_the_summary_of_the_latest_session(tmp_path: Path, capsys):
    raiz = tmp_path / "Recent"
    _sesion(raiz, "26-11-06-19-29-Sugo-Race-bbbb")
    assert sm.main(["--raiz", str(raiz), "--desde", "500", "--hasta", "510"]) == 0
    out = capsys.readouterr().out
    assert "vuelta 2" in out and "FL" in out and "500" in out
    assert sm.main(["--raiz", str(tmp_path / "vacia")]) == 1


def _xml_tiempos(d: Path, tiempos) -> None:
    filas = "".join(f'<LapSummaryDto LapNumber="{n}" LapTimeSeconds="{t}" />' for n, t in tiempos)
    (d / "_Session.xml").write_text(f"<SessionInfo><LapsSummary>{filas}</LapsSummary></SessionInfo>", encoding="utf-8")


def test_session_is_matched_by_lap_times_even_when_the_app_started_before_the_log(tmp_path: Path):
    raiz = tmp_path / "Recent"
    antes = _sesion(raiz, "26-11-06-21-12-Sugo-Race-aaaa")  # la app arrancó 5 min antes de lanzar el comando
    despues = _sesion(raiz, "26-11-06-21-18-Sugo-Race-bbbb")  # otra más cerca en el tiempo, pero con otras vueltas
    _xml_tiempos(antes, [(2, 112.006), (3, 112.1)])
    _xml_tiempos(despues, [(2, 130.0)])
    log = tmp_path / "log.jsonl"
    ts = datetime(2026, 11, 6, 21, 17, 43).astimezone(timezone.utc).isoformat()
    filas = [{"type": "session", "ts": ts}, {"type": "lap", "lap_num": 2, "lap_time_s": 112.006}, {"type": "lap", "lap_num": 3, "lap_time_s": 112.12}]
    log.write_text("\n".join(json.dumps(f) for f in filas) + "\n", encoding="utf-8")
    assert sm.tiempos_de_log(log) == [112.006, 112.12] and sm.tiempos_de_sesion(antes) == {2: 112.006, 3: 112.1}
    assert sm.sesion_de_log(log, raiz) == antes
    log.write_text(json.dumps({"type": "session", "ts": ts}) + "\n", encoding="utf-8")  # sin tiempos de vuelta, gana la más cercana
    assert sm.sesion_de_log(log, raiz) == despues
