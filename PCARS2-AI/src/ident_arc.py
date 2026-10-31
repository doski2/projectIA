"""
ident_arc.py
A1.3 (`PLAN_A_LIMITES_COCHE.md`): arcos con velocidad creciente para buscar el límite lateral del coche.

En una ventana de la vuelta (en Sugo, de 3200 m a 600 m: la recta de salida y las curvas de radio ≈ 51-55 m) se sustituye la consigna
de velocidad del teacher por la de la pasada y se desactiva su límite de aceleración lateral. El teacher conserva el volante, la línea y su
control de velocidad; aquí no se imponen pedales. Cada vuelta limpia sube a la velocidad siguiente de la lista. La primera pasada que dispara un
criterio de corte da el límite: la consigna baja entonces poco a poco hasta la banda (sin frenar a fondo con el volante girado, que fue lo
que casi trompea el coche en H50) y no se lanzan más pasadas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

MAX_ARC_KMH = 110.0  # por debajo de los 115 de `ident_maneuver.MAX_CAP_KMH`: en 2ª el motor llega al corte de encendido a ≈ 120 (H50)
MIN_ABOVE_BAND_KMH = 5.0
ACTIVATE_WITHIN_M = 150.0  # una pasada solo empieza en el primer tramo de la ventana (la recta); si no, espera a la vuelta siguiente
FREE_LATERAL_MS2 = 60.0  # límite lateral "infinito" mientras dura la pasada
IDLE, ACTIVE, LANDING = "idle", "active", "landing"
TAG_ARC, TAG_LANDING = "ident:arco", "ident:arco_fin"


@dataclass
class ArcDecision:
    target_kmh: Optional[float]  # None = conduce el teacher con su consigna y su límite lateral de siempre
    free_lateral: bool = False
    tag: str = ""  # `drive_source` de los ticks de la pasada
    event: Optional[dict] = None  # inicio o fin de pasada para el log


NO_ARC = ArcDecision(None)


class ArcRamp:
    def __init__(
        self, speeds_kmh: Sequence[float], start_m: float, end_m: float, length_m: float, band_kmh: float,
        cte_limit_m: float = 2.5, heading_limit_rad: float = 0.30, decay_kmh_s: float = 6.0,
    ):
        speeds = [float(v) for v in speeds_kmh]
        if not speeds:
            raise ValueError("hace falta al menos una velocidad (speeds_kmh)")
        if speeds != sorted(speeds):
            raise ValueError("las velocidades deben ir de menor a mayor")
        if max(speeds) > MAX_ARC_KMH:
            raise ValueError(f"{max(speeds):g} km/h supera el máximo permitido ({MAX_ARC_KMH:g}): H50")
        if min(speeds) < band_kmh + MIN_ABOVE_BAND_KMH:
            raise ValueError(f"cada velocidad debe superar la banda ({band_kmh:g}) en {MIN_ABOVE_BAND_KMH:g} km/h o más")
        if not (0 <= start_m < length_m and 0 <= end_m < length_m) or start_m == end_m:
            raise ValueError("ventana no válida")
        if cte_limit_m <= 0 or heading_limit_rad <= 0 or decay_kmh_s <= 0:
            raise ValueError("los umbrales deben ser positivos")
        self.speeds = speeds
        self.start_m = float(start_m)
        self.length_m = float(length_m)
        self.span_m = (end_m - start_m) % length_m
        self.band_kmh = float(band_kmh)
        self.cte_limit_m = cte_limit_m
        self.heading_limit_rad = heading_limit_rad
        self.decay_kmh_s = decay_kmh_s
        self.state = IDLE
        self.k = 0  # pasada en curso o siguiente
        self.finished = False  # no habrá más pasadas (todas hechas o límite encontrado)
        self.limit_reason: Optional[str] = None
        self.limit_speed_kmh: Optional[float] = None
        self.clean_speeds: List[float] = []
        self._v_abort_kmh = 0.0
        self._t_abort = 0.0

    def _offset(self, lap_distance: float) -> float:
        return (lap_distance - self.start_m) % self.length_m

    def _abort_reason(self, cte: float, heading: float, off_surface: bool, allowed: bool) -> Optional[str]:
        if not allowed:
            return "teacher/seguridad tomó el control"
        if off_surface:
            return "rueda fuera del asfalto"
        if abs(cte) > self.cte_limit_m:
            return f"|CTE| {abs(cte):.2f} m > {self.cte_limit_m:g}"
        if abs(heading) > self.heading_limit_rad:
            return f"error de rumbo {abs(heading):.2f} rad > {self.heading_limit_rad:g}"
        return None

    def update(
        self, lap_distance: float, speed_ms: float, cte: float, heading_err: float, off_surface: bool, t_s: float, allowed: bool,
    ) -> ArcDecision:
        off = self._offset(lap_distance)
        inside = off <= self.span_m

        if self.state == IDLE:
            if self.finished or self.k >= len(self.speeds):
                return NO_ARC
            if not (inside and off <= ACTIVATE_WITHIN_M) or self._abort_reason(cte, heading_err, off_surface, allowed):
                return NO_ARC
            self.state = ACTIVE
            target = self.speeds[self.k]
            return ArcDecision(target, True, TAG_ARC, {
                "type": "arc_pass", "phase": "start", "k": self.k, "target_kmh": target,
                "lap_distance": round(lap_distance, 1), "speed_kmh": round(speed_ms * 3.6, 1),
            })

        if self.state == ACTIVE:
            target = self.speeds[self.k]
            if not inside:  # ventana completa sin criterio de corte: pasada limpia
                self.state = IDLE
                self.clean_speeds.append(target)
                self.k += 1
                if self.k >= len(self.speeds):
                    self.finished = True
                return ArcDecision(None, False, "", {
                    "type": "arc_pass", "phase": "end", "k": self.k - 1, "target_kmh": target, "result": "clean",
                })
            reason = self._abort_reason(cte, heading_err, off_surface, allowed)
            if reason:
                self.state = LANDING
                self.finished = True
                self.limit_reason = reason
                self.limit_speed_kmh = target
                self._v_abort_kmh = speed_ms * 3.6
                self._t_abort = t_s
                return ArcDecision(max(self.band_kmh, self._v_abort_kmh), True, TAG_LANDING, {
                    "type": "arc_pass", "phase": "end", "k": self.k, "target_kmh": target, "result": "limit", "reason": reason,
                    "lap_distance": round(lap_distance, 1), "speed_kmh": round(speed_ms * 3.6, 1),
                })
            return ArcDecision(target, True, TAG_ARC)

        # LANDING: la consigna baja despacio hasta la banda; al salir de la ventana vuelve el teacher normal
        if not inside:
            self.state = IDLE
            return NO_ARC
        target = max(self.band_kmh, self._v_abort_kmh - self.decay_kmh_s * (t_s - self._t_abort))
        return ArcDecision(target, True, TAG_LANDING)
