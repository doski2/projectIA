import numpy as np

from experimental.common import pedales_sesion as ps


def _tick(i, gas, freno, yaw=0.0, v=100.0):
    return {"type": "tick", "lap": 2, "lap_distance": float(i), "speed_kmh": v, "throttle": float(gas), "brake": float(freno), "vehicle": {"yaw_rate": yaw}}


def test_inversions_count_zigzags_only_while_turning():
    gas = np.array([0.2, 0.8, 0.5, 0.8, 0.5, 0.8] * 10)
    assert ps.inversiones(gas, np.ones(len(gas), bool)) >= 20
    assert ps.inversiones(gas, np.zeros(len(gas), bool)) == 0  # en recta no cuentan
    assert ps.inversiones(np.linspace(0.0, 1.0, 100), np.ones(100, bool)) == 0  # una subida continua no es una inversión


def test_rebound_before_braking_is_detected_and_a_clean_lift_is_not():
    limpio = [_tick(i, 1.0 if i < 200 else 0.0, 0.0 if i < 300 else 0.8) for i in range(500)]
    r = ps.analizar_vuelta(limpio)
    assert r["frenadas"] == 1 and r["con_rebote"] == 0 and r["gas_a_0_al_frenar"] == 1
    rebote = [_tick(i, 1.0 if i < 150 else (0.3 if i < 200 else (0.9 if i < 250 else 0.0)), 0.0 if i < 300 else 0.8) for i in range(500)]
    r = ps.analizar_vuelta(rebote)
    assert r["frenadas"] == 1 and r["con_rebote"] == 1 and r["posiciones_rebote"] == [300]


def _tick_acc(i, gas, freno, lat, dec, v=100.0):
    t = _tick(i, gas, freno, v=v)
    t["vehicle"]["local_accel"] = [lat, 0.0, dec]  # eje 0 lateral, eje 2 longitudinal (positivo al frenar)
    return t


def test_braking_metrics_use_the_real_axes_dead_time_and_energy_while_turning():
    ticks = []
    for i in range(600):
        if i < 200:
            ticks.append(_tick_acc(i, 1.0, 0.0, 0.0, 0.0, v=120.0))
        elif i < 230:  # 0,5 s sin gas ni freno
            ticks.append(_tick_acc(i, 0.0, 0.0, 0.0, 0.0, v=120.0))
        elif i < 330:  # frenada de 100 ticks: la segunda mitad con 8 m/s² laterales
            ticks.append(_tick_acc(i, 0.0, 0.6, 0.0 if i < 280 else 8.0, 9.0, v=120.0 - 0.3 * (i - 230)))
        else:
            ticks.append(_tick_acc(i, 0.5, 0.0, 0.0, 0.0, v=90.0))
    r = ps.analizar_vuelta(ticks)
    assert r["frenadas"] == 1 and r["con_rebote"] == 0
    assert r["muerto_medio_s"] == 0.5
    assert 8.5 <= r["dec_mediana"] <= 9.5 and r["pct_tiempo_dec_10"] == 0.0
    assert 40 <= r["pct_energia_girando"] <= 60  # la mitad de la frenada con 8 m/s² laterales (la energía depende de v²)
    assert r["eventos"][0]["pedal_max"] == 0.6 and r["eventos"][0]["lat_max"] >= 7.0


def test_old_logs_without_local_accel_do_not_break_the_tool():
    ticks = [_tick(i, 1.0 if i < 200 else 0.0, 0.0 if i < 300 else 0.8) for i in range(500)]
    r = ps.analizar_vuelta(ticks)
    assert r["frenadas"] == 1 and "dec_mediana" in r  # sin aceleraciones: ceros, pero no falla


def test_reference_speed_drop_is_measured_on_a_real_reference():
    from pathlib import Path

    ref = Path(ps.REPO) / "PCARS2-AI" / "src" / "refs" / "sugo_ai.json"
    s = ps.salto_consigna(ref)
    assert s["max_caida_kmh_por_m"] > 0.0 and 0 < s["en_m"] <= 3600 and s["puntos_con_caida_mayor_2"] >= 0
    p = ps.salto_consigna(ref, perfil=True)
    assert p["decel_implicita_max"] <= 8.0 + 0.1 < s["decel_implicita_max"]  # el perfil continuo nunca pide más que a_b; la consigna de siempre sí (el salto de 8 a 4 m/s²)
    assert p["max_caida_kmh_por_m"] < s["max_caida_kmh_por_m"]
