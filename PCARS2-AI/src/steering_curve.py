"""
steering_curve.py
Curva de respuesta del volante de PCARS2 con el mando virtual (medida, no teórica).

El juego no aplica el volante que enviamos: con zona muerta 0 y sensibilidad 50, una orden de
0,25 produce ~0,10 y una de 0,55 ~0,47 (`vehicle.game_steer` frente a `steering`, retardo de 3
ticks compensado). Es una curva estática: sale igual en 18 sesiones (639 250 ticks a más de
25 km/h). `compensate_steering` envía la orden inversa para que lo aplicado ≈ lo pedido.

Si cambia la configuración del mando o el coche, hay que volver a medirla
(ver docs/CONFIGURACION_JUEGO.md).
"""

from __future__ import annotations

import numpy as np

# (orden enviada |x|, volante aplicado por el juego). Medias por tramos de 0,05.
STEERING_RESPONSE = (
    (0.000, 0.000),
    (0.075, 0.007),
    (0.125, 0.028),
    (0.175, 0.058),
    (0.225, 0.096),
    (0.275, 0.140),
    (0.325, 0.193),
    (0.375, 0.251),
    (0.425, 0.317),
    (0.475, 0.388),
    (0.525, 0.468),
    (0.575, 0.546),
    (0.625, 0.618),
    (0.675, 0.700),
    (0.725, 0.780),
    (0.775, 0.848),
    (0.825, 0.917),
    (0.875, 0.976),
    (0.925, 0.990),
    (0.975, 0.996),
    (1.000, 1.000),
)

_SENT = np.array([p[0] for p in STEERING_RESPONSE])
_APPLIED = np.array([p[1] for p in STEERING_RESPONSE])


def applied_steering(sent: float) -> float:
    """Volante que aplica el juego (con signo) para una orden enviada."""
    return float(np.sign(sent) * np.interp(abs(sent), _SENT, _APPLIED))


def compensate_steering(desired: float) -> float:
    """Orden a enviar (con signo) para que el juego aplique `desired`."""
    d = max(-1.0, min(1.0, float(desired)))
    return float(np.sign(d) * np.interp(abs(d), _APPLIED, _SENT))
