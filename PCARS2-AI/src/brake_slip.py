"""Limitador de frenada por deslizamiento de las ruedas delanteras (V43).

Con el pedal a fondo las ruedas delanteras se bloquean (giran a 0 rad/s mientras las traseras siguen), el coche pierde la dirección y se sale de la línea: a 150 km/h hasta 3,4 m. Un tope fijo de
pedal valdría solo para unas condiciones concretas (el agarre cambia con el reglaje, la temperatura y el neumático), así que el límite sale del propio deslizamiento:

    deslizamiento relativo = 1 − rps_delanteras / rps_traseras      (0 = giran igual; 1 = delanteras paradas)

No necesita la velocidad ni el radio del neumático, y las traseras (que en las frenadas medidas deslizan solo un 4-8 %) hacen de referencia. Si el deslizamiento pasa de `limit`, una escala
multiplicativa del pedal baja en proporción al exceso (acción integral, como un ABS suave) y sube poco a poco al recuperar agarre. Solo protege contra el bloqueo de las delanteras: no ve el de las
traseras (el eje de referencia). Con `limit = 0` está apagado y el pedal pasa tal cual (producción).

Medido con el teacher de A2 (sin bloqueo): deslizamiento delantero absoluto del 10-15 % con pedal 0,6-0,95, es decir ≈ 0,05-0,10 relativo a las traseras, con p95 de hasta 0,25. Un objetivo de
0,20 deja pasar ese rango y corta antes del bloqueo; es un punto de partida a ajustar en el juego.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence

MIN_REAR_RPS = 8.0  # rad/s (≈ 8 km/h con el radio efectivo de 0,274 m): por debajo no hay referencia fiable
MIN_BRAKE = 0.05  # pedal por debajo del cual no hay frenada que limitar y la escala se restablece


@dataclass
class BrakeSlipConfig:
    limit: float = 0.0  # deslizamiento relativo objetivo (0 = apagado)
    # Ganancias ajustadas con la primera sesión real (V45): con 1,5 y 0,02 el pedal hacía dientes de sierra (bajaba hasta 0,17 y tardaba ≈ 0,6 s en volver) y la frenada de 130 a 30 km/h
    # perdía ≈ 17 % de deceleración frente al bloqueo (10,1-10,5 frente a ≈ 12,5 m/s²). En un conjunto de simuladores que reproducen esa sesión, 1,0 y 0,05 recuperan casi todo sin bloqueo.
    down_gain: float = 1.0  # bajada de la escala del pedal por tick y por unidad de exceso de deslizamiento
    up_rate: float = 0.05  # subida de la escala por tick cuando no hay exceso (1,0 en ≈ 0,3 s a 60 Hz)
    min_scale: float = 0.15  # la escala no baja de aquí, para no soltar del todo el pedal
    # Memoria del pedal límite (V49, opt-in): sin ella la escala vuelve siempre a 1,0 y el pedal oscila cada ≈ 0,2 s entre 1,0 y 0,2 (valles de 7-9 m/s²). Con `hold_frac` > 0 se anota el pedal
    # aplicado al pasar del objetivo (`p_lim`) y la escala sube deprisa (`up_rate`) solo hasta `hold_frac` · `p_lim`; desde ahí sube despacio (`hold_rate`), de modo que el pedal se queda cerca del
    # que sostiene el deslizamiento en lugar de pasarse en cada ciclo. En el simulador (V49) sube ≈ 0,5-0,7 m/s² y bloquea menos con poco agarre; en el juego sin probar.
    hold_frac: float = 0.0  # fracción del pedal límite hasta la que se recupera deprisa (0 = sin memoria; típico 0,85)
    hold_rate: float = 0.003  # subida de la escala por tick por encima de esa fracción
    hold_learn: float = 0.5  # peso del último cruce en el pedal límite (media móvil exponencial)


class BrakeSlipLimiter:
    def __init__(self, config: Optional[BrakeSlipConfig] = None):
        self.config = config or BrakeSlipConfig()
        self.scale = 1.0
        self.last_slip: Optional[float] = None
        self.p_lim: Optional[float] = None  # pedal aplicado cuando el deslizamiento pasó del objetivo (solo con `hold_frac` > 0)
        self._over = False  # el tick anterior había exceso

    @property
    def active(self) -> bool:
        return self.config.limit > 0.0

    def reset(self) -> None:
        self.scale = 1.0
        self.last_slip = None
        self.p_lim = None
        self._over = False

    @staticmethod
    def relative_slip(tyre_rps: Sequence[float]) -> Optional[float]:
        """Deslizamiento relativo de las delanteras (FL, FR, RL, RR en `tyre_rps`), o None si las traseras giran demasiado despacio para servir de referencia."""
        front = (abs(tyre_rps[0]) + abs(tyre_rps[1])) / 2.0
        rear = (abs(tyre_rps[2]) + abs(tyre_rps[3])) / 2.0
        if rear < MIN_REAR_RPS:
            return None
        return max(0.0, 1.0 - front / rear)

    def apply(self, brake: float, tyre_rps: Sequence[float]) -> float:
        """Pedal de freno que se aplica: el pedido por la escala actual, que se actualiza con el deslizamiento de este tick."""
        cfg = self.config
        if not self.active:
            return brake
        slip = self.relative_slip(tyre_rps)
        self.last_slip = slip
        if brake < MIN_BRAKE or slip is None:
            if brake < MIN_BRAKE:  # fin de la frenada: el pedal límite era de esa frenada
                self.p_lim = None
                self._over = False
            self.scale = min(1.0, self.scale + cfg.up_rate)
            return brake * self.scale if brake >= MIN_BRAKE else brake
        excess = slip - cfg.limit
        if excess > 0.0:
            if cfg.hold_frac > 0.0 and not self._over:  # primer tick del exceso: el pedal aplicado ahora es un techo
                applied = brake * self.scale
                self.p_lim = applied if self.p_lim is None else (1.0 - cfg.hold_learn) * self.p_lim + cfg.hold_learn * applied
            self._over = True
            self.scale = max(cfg.min_scale, self.scale - cfg.down_gain * excess)
        else:
            self._over = False
            if cfg.hold_frac > 0.0 and self.p_lim is not None:
                ceiling = min(1.0, cfg.hold_frac * self.p_lim / brake)
                if self.scale < ceiling:
                    self.scale = min(ceiling, self.scale + cfg.up_rate)
                else:
                    self.scale = min(1.0, self.scale + cfg.hold_rate)
            else:
                self.scale = min(1.0, self.scale + cfg.up_rate)
        return brake * self.scale

    def diag(self) -> Dict[str, float]:
        """Campos para el log del tick (solo con el limitador encendido)."""
        d = {
            "brake_slip": round(self.last_slip, 3) if self.last_slip is not None else -1.0,
            "brake_scale": round(self.scale, 3),
        }
        if self.config.hold_frac > 0.0:
            d["brake_plim"] = round(self.p_lim, 3) if self.p_lim is not None else -1.0
        return d
