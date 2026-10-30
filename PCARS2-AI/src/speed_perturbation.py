"""
speed_perturbation.py
Perturbación de velocidad para probar la recuperación (P24): cada `period_m` metros el coche rueda sin gas ni freno
hasta perder `drop_kmh`, y se suelta. El teacher sigue etiquetando con la consigna intacta (`accel_straight`), así que el
buffer recibe filas de recuperación y quien conduce (el BC) demuestra si sabe volver a la velocidad sin esperar a equivocarse.
"""

from __future__ import annotations

from typing import Optional

IDLE, COASTING, RECOVERING = "idle", "coasting", "recovering"
LAP_WRAP_DROP_M = 500.0
# Sin esto un coche que no pierde velocidad (cuesta abajo) rodaría para siempre o uno que no se recupera lo haría sin parar.
MAX_COAST_S = 10.0
MAX_RECOVER_S = 30.0
RECOVERED_MARGIN_MS = 0.14  # ≈ 0,5 km/h bajo la consigna


class SpeedPerturber:
    def __init__(self, period_m: float, drop_kmh: float = 4.5, start_m: float = 100.0):
        if period_m <= 0 or drop_kmh <= 0:
            raise ValueError("period_m y drop_kmh deben ser positivos")
        self.period_m = period_m
        self.drop_ms = drop_kmh / 3.6
        self.start_m = start_m
        self.state = IDLE
        self.count = 0  # perturbaciones lanzadas en la sesión
        self._t0 = 0.0
        self._prev_d: Optional[float] = None
        self._next_mark = max(period_m, start_m)

    def update(self, lap_distance: float, speed_ms: float, target_ms: float, t_s: float, allowed: bool) -> bool:
        """True si en este tick hay que rodar sin pedales. `allowed` False (arranque, seguridad, ajuste) corta la perturbación."""
        if self._prev_d is not None and lap_distance < self._prev_d - LAP_WRAP_DROP_M:
            self._next_mark = max(self.period_m, self.start_m)  # vuelta nueva: los puntos se repiten igual
        self._prev_d = lap_distance

        if not allowed:
            if self.state == COASTING:
                self.state = RECOVERING
                self._t0 = t_s
            return False

        if self.state == IDLE:
            if lap_distance >= self._next_mark and speed_ms >= target_ms - RECOVERED_MARGIN_MS:
                self.state = COASTING
                self._t0 = t_s
                self.count += 1
                self._next_mark = (int(lap_distance // self.period_m) + 1) * self.period_m
            elif lap_distance >= self._next_mark + self.period_m:
                self._next_mark = (int(lap_distance // self.period_m) + 1) * self.period_m  # no se pudo (curva, lento): salta
        if self.state == COASTING:
            if speed_ms <= target_ms - self.drop_ms or t_s - self._t0 > MAX_COAST_S:
                self.state = RECOVERING
                self._t0 = t_s
                return False
            return True
        if self.state == RECOVERING:
            if speed_ms >= target_ms - RECOVERED_MARGIN_MS or t_s - self._t0 > MAX_RECOVER_S:
                self.state = IDLE
        return False
