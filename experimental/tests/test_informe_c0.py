import json
import math

from experimental.common import informe_c0


def _write_log(path, broken=False):
    R, rows = 50.0, [{"type": "session", "log_schema": 2, "origin": "experimental", "experiment": "c0_log",
                      "reference": "no_existe.json"}]
    s = 0.0
    for i in range(3000):
        t = i / 60.0
        v = 15 + 5 * math.sin(0.3 * t)
        a_long = 1.5 * math.cos(0.3 * t)
        s += v / 60.0
        ang = s / R
        yaw = v / R
        veh = {
            "yaw_rate": round(yaw, 4), "lat_accel": round(v * yaw, 3),
            "local_velocity": [0.0, 0.0, 0.0] if broken else [0.0, 0.0, round(v, 3)],
            "local_accel": [round(a_long, 3), 0.01 * i % 1, round(v * yaw, 3)],
            "ang_vel": [0.01 * math.sin(t), 0.02, yaw], "position": [R * math.cos(ang), 0.0, R * math.sin(ang)],
            "orientation": [0.0, ang, 0.0], "ride_height": [0.05 + 0.001 * math.sin(t)] * 4,
            "susp_travel": [0.02 + 0.001 * math.sin(t)] * 4, "tyre_temp": [80 + i // 500] * 4,
            "tyre_tread_temp": [90 + i // 500] * 4, "tyre_wear": [i // 1000] * 4, "fuel_level": 0.9 - i * 1e-5,
            "brake_bias": 60 + i % 2, "aero_damage": i % 3, "engine_damage": i % 5, "raw_throttle": i % 255,
            "raw_brake": i % 7, "clutch": i % 4,
        }
        rows.append({"type": "tick", "tick": i + 1, "t_s": round(t, 4), "lap": 1, "lap_distance": round(s % 314, 1),
                     "speed_kmh": v * 3.6, "safety_override": 100 <= i < 160, "vehicle": veh})
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _status(result):
    return {c["nombre"]: c["estado"] for c in result["checks"]}


def test_report_ok_on_consistent_log(tmp_path, monkeypatch):
    monkeypatch.setattr(informe_c0, "OUT", tmp_path / "out")
    log = tmp_path / "a.jsonl"
    _write_log(log)
    r = informe_c0.build_report(log)
    st = _status(r)
    assert st["|local_velocity| ≈ speed_kmh"] == "ok"
    assert st["local_accel longitudinal ≈ dv/dt"] == "ok"
    assert st["Eje lateral de local_accel (mejor correlación con v · yaw_rate)"] == "ok"
    assert st["Longitud de position (x,z) ≈ lap_distance recorrido"] == "ok"
    assert st["Campo local_velocity"] == "ok"
    assert "fallo" not in st.values()
    assert r["incidents"][0]["tipo"] == "safety_override" and r["incidents"][0]["duracion_ticks"] == 60
    assert (tmp_path / "out" / "informe_a.html").is_file() and (tmp_path / "out" / "informe_a.json").is_file()


def test_report_detects_broken_axis(tmp_path, monkeypatch):
    monkeypatch.setattr(informe_c0, "OUT", tmp_path / "out")
    log = tmp_path / "b.jsonl"
    _write_log(log, broken=True)
    st = _status(informe_c0.build_report(log))
    assert st["|local_velocity| ≈ speed_kmh"] == "fallo"
    assert st["Campo local_velocity"] == "aviso"  # constante a cero


def _ticks_with_timing(pause_at=None):
    rows, pc, game = [], 0.0, 0.0
    for i in range(1200):
        sector = 1 + i // 400
        gap = 1.5 if i == pause_at else 1 / 60
        pc += gap
        game += 0.0 if i == pause_at else 1 / 60
        rows.append({"type": "tick", "tick": i + 1, "t_s": round(pc, 4), "lap": 1, "lap_distance": float(i),
                     "speed_kmh": 40.0, "timing": {"sector": sector, "sector_time_s": round(game % 7, 3),
                                                   "game_time_s": round(game, 3)}})
    return rows


def test_pause_detected_with_game_clock():
    ps = informe_c0.pauses(_ticks_with_timing(pause_at=500))
    assert len(ps) == 1 and ps[0]["pausa_del_juego"] and ps[0]["metodo"] == "reloj del juego"


def test_gap_without_pause_is_flagged_as_other():
    rows = _ticks_with_timing()
    for r in rows[602:]:  # se perdieron datos pero el juego siguió corriendo: ambos relojes saltan
        r["t_s"] += 1.0
        r["timing"]["game_time_s"] += 1.0
    ps = informe_c0.pauses(rows)
    assert len(ps) == 1
    assert ps[0]["pausa_del_juego"] is False


def test_sector_table_ignores_pauses():
    secs = informe_c0.sector_table(_ticks_with_timing(pause_at=500))
    assert [r["sector"] for r in secs] == [1, 2, 3]
    assert secs[1]["tiempo_conduccion_s"] < 400 / 60 + 0.1  # sin los 1,5 s de pausa


def test_pause_by_frozen_state_without_timing():
    rows = [{"type": "tick", "tick": i, "t_s": i / 60, "lap": 1, "lap_distance": 11.0 * i / 60, "speed_kmh": 40.0}
            for i in range(600)]
    for i, r in enumerate(rows[300:], start=300):  # 1,5 s de pausa: el reloj del PC salta y la distancia sigue igual
        r["t_s"] += 1.5
        r["lap_distance"] = 11.0 * (i - 1) / 60
    assert informe_c0.pauses(rows)[0]["pausa_del_juego"] is True


def test_data_gap_with_car_moving_is_not_a_pause():
    rows = [{"type": "tick", "tick": i, "t_s": i / 60, "lap": 1, "lap_distance": 11.0 * i / 60, "speed_kmh": 40.0}
            for i in range(600)]
    for r in rows[300:]:  # el juego siguió: la distancia avanzó lo esperado
        r["t_s"] += 1.5
        r["lap_distance"] += 16.5
    assert informe_c0.pauses(rows)[0]["pausa_del_juego"] is False


def _x4b_ticks(n=300):
    return [{"type": "tick", "tick": i, "t_s": i / 60, "speed_kmh": 40.0,
             "vehicle": {"tyre_flags": [7, 7, 7, 7], "tyre_height": [0.0] * 4, "brake_temp": [200] * 3 + [220 + i % 5],
                         "susp_vel": [0.01 * (i % 3)] * 4, "air_pressure": [150] * 4, "engine_torque": 90.0 + i % 7,
                         "brake_damage": [0] * 4, "susp_damage": [0] * 4, "crash_state": 0, "tick_count": i % 256,
                         "car_flags": 0b10010 if i % 50 == 0 else 0b10}}
            for i in range(n)]


def _run_x4b(ticks, events):
    out = {}
    informe_c0.check_x4b(ticks, events, lambda n, s, d="": out.__setitem__(n, (s, d)))
    return out


def test_x4b_checks_ok_with_plausible_data():
    cond = {"type": "conditions", "ambient_c": 14, "track_c": 18, "rain": 0, "snow": 0, "wind_speed": 3,
            "wind_dir": [0, 0], "raw_hex": "00" * 12}
    st = _run_x4b(_x4b_ticks(), [cond])
    assert all(s == "ok" for s, _ in st.values()), st
    assert "Lluvia durante la prueba" not in st


def test_x4b_flags_rain_and_implausible_values():
    ticks = _x4b_ticks()
    for t in ticks:
        t["vehicle"]["tyre_flags"] = [1, 1, 1, 1]  # ninguna rueda en el suelo
    cond = {"type": "conditions", "ambient_c": 14, "track_c": 18, "rain": 90, "snow": 0, "wind_speed": 3,
            "wind_dir": [0, 0], "raw_hex": "00" * 12}
    st = _run_x4b(ticks, [cond])
    assert st["tyre_flags (bit 2 = rueda en el suelo)"][0] == "aviso"
    assert st["Lluvia durante la prueba"][0] == "aviso"


def test_x4b_skipped_for_logs_without_tanda_2():
    st = _run_x4b([{"type": "tick", "tick": i, "t_s": i / 60, "vehicle": {}} for i in range(50)], [])
    assert st["Paquete 4 (condiciones)"][0] == "omitido"
