"""Tests de `sincronia.py` con datos sintéticos: arranque en el log, arranque en el vídeo y desfase conocido."""

import json

import numpy as np
import pytest

from video_vuelta.src import sincronia as sc


def _log(arranque_s=17.0, duracion_s=140.0, hz=100, longitud_m=1000.0):
    """Coche parado hasta `arranque_s`, acelera a 10 m/s y cruza la meta cuando llega a `longitud_m`."""
    t = np.arange(0, duracion_s, 1.0 / hz)
    v_ms = np.clip((t - arranque_s) * 10.0, 0, 10.0)
    s = np.concatenate([[0.0], np.cumsum(v_ms[1:] / hz)])
    vuelta = (s // longitud_m).astype(int) + 1
    return sc.LogVuelta(t, v_ms * 3.6, vuelta, s % longitud_m)


def test_arranque_log():
    log = _log(arranque_s=17.0)
    assert sc.arranque_log(log) == pytest.approx(17.0, abs=0.2)


def test_arranque_log_sin_movimiento():
    log = _log()
    log.velocidad_kmh[:] = 0
    with pytest.raises(ValueError):
        sc.arranque_log(log)


def test_arranque_video_ignora_destellos_cortos():
    ts = np.arange(0, 30, 1 / 60)
    en = np.zeros_like(ts)
    en[100:103] = 5.0  # destello de 3 fotogramas: no es movimiento
    en[int(8.5 * 60):] = 10.0
    assert sc.arranque_video(ts, en) == pytest.approx(8.5, abs=0.05)


def test_arranque_video_nunca_arranca():
    ts = np.arange(0, 5, 1 / 60)
    with pytest.raises(ValueError):
        sc.arranque_video(ts, np.zeros_like(ts))


def test_sincronizar_recupera_el_desfase():
    log = _log(arranque_s=17.0)
    ts = np.arange(0, 120, 1 / 60)
    en = np.where(ts >= 8.0, 10.0, 0.0)  # el vídeo arranca 9 s antes en su reloj
    s = sc.sincronizar(ts, en, log)
    assert s["desfase_s"] == pytest.approx(9.0, abs=0.1)
    assert s["cruce_de_meta_t_video_s"] == pytest.approx(s["cruce_de_meta_t_log_s"] - s["desfase_s"], abs=1e-3)


def test_distancia_a_instante_de_video():
    log = _log(arranque_s=17.0)
    ts = np.arange(0, 120, 1 / 60)
    en = np.where(ts >= 8.0, 10.0, 0.0)
    s = sc.sincronizar(ts, en, log)
    t_v = sc.t_video_de_distancia(s, log, 500.0)
    assert t_v == pytest.approx(sc.instante_de_distancia(log, 500.0) - 9.0, abs=0.1)
    assert 0 < t_v < ts[-1]


def test_distancia_fuera_de_la_vuelta():
    with pytest.raises(ValueError):
        sc.instante_de_distancia(_log(longitud_m=1000.0), 5000.0)


def test_cruce_de_meta_sin_cruce():
    log = _log(duracion_s=20.0, longitud_m=1000.0)
    assert sc.cruce_de_meta(log) is None


def test_leer_log_solo_ticks(tmp_path):
    p = tmp_path / "log.jsonl"
    filas = [{"type": "session", "track": "X"}]
    filas += [{"type": "tick", "t_s": i * 0.1, "speed_kmh": float(i), "lap": 1, "lap_distance": float(i)} for i in range(5)]
    p.write_text("\n".join(json.dumps(f) for f in filas), encoding="utf-8")
    log = sc.leer_log(p)
    assert len(log.t_s) == 5 and log.velocidad_kmh[-1] == 4.0


def test_energia_de_un_video_sintetico(tmp_path):
    cv2 = pytest.importorskip("cv2")
    ruta = tmp_path / "v.avi"
    w, h, fps = 160, 90, 30
    wr = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
    if not wr.isOpened():
        pytest.skip("este OpenCV no escribe MJPG")
    rng = np.random.default_rng(0)
    textura = rng.integers(0, 255, (h, w * 3), dtype=np.uint8)
    for i in range(90):  # 3 s: 1 s quieto y 2 s desplazándose
        desp = 0 if i < 30 else (i - 30) * 3
        trozo = textura[:, desp:desp + w]
        wr.write(cv2.cvtColor(trozo, cv2.COLOR_GRAY2BGR))
    wr.release()
    ts, en = sc.energia_movimiento(ruta)
    assert len(ts) == 90
    assert en[2:30].max() < 1.0  # quieto (el 2.º fotograma MJPG puede traer un pico de compresión; no cuenta: se exigen 10 seguidos)
    assert sc.arranque_video(ts, en) == pytest.approx(1.0, abs=0.15)
