"""
Tests del mapeo de acción del agente (`controller.decode_action`).

`decode_action` traduce la acción continua del PPO (3 valores en [-1, 1])
en (throttle, brake, steering). Un error aquí invierte pedales o el volante
y arruina el entrenamiento de forma silenciosa, así que conviene fijar el
contrato con tests.

El import de `controller` arrastra `vgamepad`; si no estuviera disponible,
se omite todo el módulo en lugar de fallar.
"""

import pytest

vg = pytest.importorskip("vgamepad")  # noqa: F841

from controller import decode_action


def test_full_throttle_no_brake():
    throttle, brake, steering = decode_action([1.0, -1.0, 0.0])
    assert throttle == pytest.approx(1.0)
    assert brake == pytest.approx(0.0)
    assert steering == pytest.approx(0.0)


def test_full_brake_no_throttle():
    throttle, brake, steering = decode_action([-1.0, 1.0, 0.0])
    assert throttle == pytest.approx(0.0)
    assert brake == pytest.approx(1.0)


def test_neutral_action_is_half_pedals():
    # 0.0 en [-1,1] → 0.5 tras mapear a [0,1]
    throttle, brake, steering = decode_action([0.0, 0.0, 0.0])
    assert throttle == pytest.approx(0.5)
    assert brake == pytest.approx(0.5)
    assert steering == pytest.approx(0.0)


def test_steering_sign_preserved():
    assert decode_action([0.0, 0.0, -1.0])[2] == pytest.approx(-1.0)  # izquierda
    assert decode_action([0.0, 0.0, 1.0])[2] == pytest.approx(1.0)    # derecha


def test_out_of_range_is_clipped():
    throttle, brake, steering = decode_action([5.0, -9.0, 42.0])
    assert throttle == pytest.approx(1.0)   # clip a 1
    assert brake == pytest.approx(0.0)      # clip a -1 → (−1+1)/2 = 0
    assert steering == pytest.approx(1.0)   # clip a 1


def test_outputs_within_valid_ranges():
    import random
    for _ in range(100):
        a = [random.uniform(-3, 3) for _ in range(3)]
        throttle, brake, steering = decode_action(a)
        assert 0.0 <= throttle <= 1.0
        assert 0.0 <= brake <= 1.0
        assert -1.0 <= steering <= 1.0
