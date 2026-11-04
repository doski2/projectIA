"""Tests de `estadisticas_vueltas.py`: mínimo, media y máximo por vuelta y descarte de vueltas incompletas."""

from experimental.common import estadisticas_vueltas as ev


def _tick(lap, d, t, cte=0.5, v=80.0, gomas=60.0, terreno=(0, 0, 0, 0)):
    return {"type": "tick", "lap": lap, "lap_distance": d, "t_s": t, "speed_kmh": v, "signed_cte": cte, "throttle": 0.5, "brake": 0.0, "steering": -0.2,
            "vehicle": {"local_accel": [3.0, 0.1, -1.0], "local_velocity": [1.0, 0.0, -20.0], "tyre_temp": [gomas] * 4, "brake_temp": [200] * 4,
                        "air_pressure": [150, 150, 140, 140], "terrain": list(terreno)}}


def _vuelta(lap, t0, gomas, cte_pico=2.0, terreno=(0, 0, 0, 0)):
    ticks = [_tick(lap, float(d), t0 + d / 30.0, cte=cte_pico if d == 1000 else 0.5, gomas=gomas, terreno=terreno) for d in range(0, 3500, 10)]
    return ticks


def test_min_mean_max_per_lap_and_the_signs_of_each_magnitude():
    ticks = _vuelta(1, 0.0, 80.0) + _vuelta(2, 120.0, 40.0, cte_pico=3.0)
    est = ev.estadisticas(ticks, [{"t_s": 0.0, "rain": 153, "track_c": 13, "ambient_c": 10}])
    assert sorted(est) == [1, 2]
    assert est[1]["cte"][2] == 2.0 and est[2]["cte"][2] == 3.0 and est[1]["cte"][0] == 0.5
    assert est[1]["gomas"] == (80.0, 80.0, 80.0) and est[2]["gomas"] == (40.0, 40.0, 40.0)  # las gomas se enfrían de una vuelta a otra
    assert est[1]["lateral"][1] == 3.0 and est[1]["longitudinal"][1] == 1.0  # el eje 2 de local_accel va con el signo cambiado
    assert est[1]["presion"][1] == 1.45  # media de [150, 150, 140, 140] centésimas de bar
    assert est[1]["volante"][1] == 0.2 and est[1]["deriva"][1] > 2.8
    assert (est[1]["lluvia"], est[1]["pista_c"], est[1]["ambiente_c"]) == (153, 13, 10)
    assert est[1]["tiempo_s"] > 100 and est[1]["fuera"] == 0


def test_tyre_zone_temperatures_appear_only_in_logs_that_carry_them():
    nuevo = _vuelta(1, 0.0, 60.0)
    for t in nuevo:
        t["vehicle"].update({"tyre_left_c": [80, 82, 0, 0], "tyre_center_c": [70] * 4, "tyre_right_c": [60] * 4})
    est = ev.estadisticas(nuevo)
    assert est[1]["goma_izq"] == (81.0, 81.0, 81.0) and est[1]["goma_centro"][1] == 70.0 and est[1]["goma_dcha"][1] == 60.0  # los 0 no cuentan
    assert "goma_capa" not in est[1]  # sin ese campo en el log, la magnitud no sale
    assert "-" in ev.tabla(est).splitlines()[-2]  # y la tabla pone «-»


def test_laps_that_do_not_cover_the_circuit_are_dropped_and_wheels_off_are_counted():
    parcial = [_tick(3, float(d), 300.0 + d / 30.0) for d in range(0, 1000, 10)]
    fuera = _vuelta(2, 120.0, 40.0, terreno=(7, 0, 0, 0))
    est = ev.estadisticas(_vuelta(1, 0.0, 80.0) + fuera + parcial)
    assert sorted(est) == [1, 2] and est[2]["fuera"] == len(fuera)
    assert "V1*" in ev.tabla(est) and "mín / media / máx" in ev.tabla(est)
    assert ev.tabla({}) == "(sin vueltas completas)"
