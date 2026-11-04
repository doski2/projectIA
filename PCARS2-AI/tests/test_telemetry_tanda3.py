"""Tanda 3 del paquete de física (log_schema 4): temperaturas de la goma por capa y por zona, y compuesto de cada rueda."""

import struct
from types import SimpleNamespace

from session_log import compound_diag, vehicle_diag
from telemetry_udp import parse_telemetry


def _paquete() -> bytearray:
    d = bytearray(556)
    d[10] = 0
    return d


def _kelvin(celsius):
    return [int(round(c + 273.15)) for c in celsius]


def test_the_seven_tyre_temperature_arrays_are_read_in_celsius_from_their_offsets():
    d = _paquete()
    for off, grados in ((224, (70, 71, 72, 73)), (232, (60, 61, 62, 63)), (240, (50, 51, 52, 53)), (248, (30, 31, 32, 33)),
                        (256, (80, 81, 82, 83)), (264, (84, 85, 86, 87)), (272, (88, 89, 90, 91))):
        struct.pack_into("4H", d, off, *_kelvin(grados))
    struct.pack_into("4H", d, 216, *_kelvin((76, 76, 76, 76)))  # sTyreTreadTemp, ya se leía y llega en kelvin
    t = parse_telemetry(bytes(d))
    assert t is not None
    assert t.tyre_layer_c == (70, 71, 72, 73) and t.tyre_carcass_c == (60, 61, 62, 63) and t.tyre_rim_c == (50, 51, 52, 53) and t.tyre_air_c == (30, 31, 32, 33)
    assert t.tyre_left_c == (80, 81, 82, 83) and t.tyre_center_c == (84, 85, 86, 87) and t.tyre_right_c == (88, 89, 90, 91)
    assert t.tyre_tread_temp == tuple(_kelvin((76,) * 4))  # el campo de siempre no cambia: sigue en kelvin


def test_values_out_of_range_or_zero_are_not_temperatures_and_come_out_as_zero():
    d = _paquete()
    struct.pack_into("4H", d, 224, 0, 100, 600, 300)  # sin rellenar, demasiado frío, demasiado caliente, 27 °C
    t = parse_telemetry(bytes(d))
    assert t is not None and t.tyre_layer_c == (0, 0, 0, 27)


def test_compound_names_are_read_per_wheel_and_garbage_gives_an_empty_name():
    d = _paquete()
    for i, nombre in enumerate((b"Wet", b"Wet", b"Wet Soft", b"")):
        d[378 + 40 * i: 378 + 40 * i + len(nombre)] = nombre
    d[378 + 40 * 3: 378 + 40 * 3 + 3] = bytes([0xF0, 0x01, 0x02])  # bytes que no son texto
    t = parse_telemetry(bytes(d))
    assert t is not None and t.tyre_compound == ("Wet", "Wet", "Wet Soft", "")
    assert compound_diag(t) == ["Wet", "Wet", "Wet Soft", ""]
    assert compound_diag(SimpleNamespace(tyre_compound=("", "", "", ""))) is None
    assert compound_diag(SimpleNamespace()) is None  # un frame sin el campo (logs y tests antiguos)


def test_the_new_temperatures_go_to_the_vehicle_block_of_the_tick_log():
    d = _paquete()
    struct.pack_into("4H", d, 256, *_kelvin((80, 81, 82, 83)))
    t = parse_telemetry(bytes(d))
    v = vehicle_diag(t)
    assert v["tyre_left_c"] == [80, 81, 82, 83] and v["tyre_center_c"] == [0, 0, 0, 0]
    for clave in ("tyre_layer_c", "tyre_carcass_c", "tyre_rim_c", "tyre_air_c", "tyre_right_c"):
        assert clave in v
