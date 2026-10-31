"""
ident_maneuver.py
Maniobras de identificación del coche (A1, `PLAN_A_LIMITES_COCHE.md`): en las rectas largas de la pista el coche acelera a
fondo (`acel`) o rueda sin pedales (`rodar`), y el resto del tiempo conduce el teacher (volante y velocidad de siempre).
Sirve para medir `a_acel(v, marcha)` y la resistencia al avance sin conducir a mano. `acelrodar` hace las dos en una
pasada: gas a fondo hasta el techo y, al llegar, sin pedales hasta el suelo o el final de la zona útil. `frenar` mide el
freno (A1.2): para cada velocidad de entrada de una lista acelera a fondo hasta ella y frena a fondo (con el ABS del juego)
hasta el suelo, y repite con la siguiente, todo en la misma recta.

Una maniobra por recta y por pasada. Seguridad: solo arranca con el coche en la línea, termina al llegar al techo/suelo de
velocidad, al salir de la zona útil (que deja `end_margin_m` antes de la curva para que el teacher frene), al alejarse de la
línea o si algo del bucle (safety, fine-tune, marcha atrás) la corta. Quien la usa pone `allowed` en falso en esos casos.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

KIND_ACCEL, KIND_COAST, KIND_BOTH, KIND_BRAKE = "acel", "rodar", "acelrodar", "frenar"
KINDS = (KIND_ACCEL, KIND_COAST, KIND_BOTH, KIND_BRAKE)
PHASE_BRAKE = "frenar"
MIN_ENTRY_ABOVE_FLOOR_KMH = 15.0  # una frenada que empieza a menos de esto sobre el suelo no mide nada
IDLE, ACTIVE = "idle", "active"

# Techo de velocidad permitido. El `AutoShifter` de producción no sube de 2ª (`TEACHING_MAX_GEAR`) y la 2ª llega al corte de
# encendido a ≈ 120 km/h; ahí el coche y el cambio entran en un bucle (RB, LB, punto muerto, gas a trompicones) que excita el
# yaw: H50, casi un trompo a 130 km/h. No se sube de aquí hasta que haya cambio de 3ª y 4ª probado.
MAX_CAP_KMH = 115.0
MAX_CTE_M = 1.0  # más lejos de la línea que esto: no arranca y, si está en marcha, se corta
MAX_NEUTRAL_S = 0.6  # un cambio de marcha pasa ≈ 0,2 s por punto muerto; más que esto no es un cambio y se corta
MAX_ACTIVE_S = 40.0  # tope de una maniobra: una secuencia de cuatro frenadas con sus aceleraciones dura ≈ 30 s
COAST_MIN_ABOVE_KMH = 5.0  # `rodar` solo arranca si hay al menos esto sobre el suelo
ACCEL_MIN_BELOW_KMH = 2.0  # `acel` solo arranca si queda al menos esto hasta el techo


def find_straights(
    curvature_at: Callable[[float], float], length_m: float, min_len_m: float = 300.0,
    radius_m: float = 400.0, smooth_m: int = 40,
) -> List[Tuple[float, float]]:
    """Rectas de la pista como (inicio, fin) en metros de vuelta; `fin` puede pasar de `length_m` si cruzan la meta.

    Una recta es un tramo con |curvatura media en `smooth_m`| < 1/`radius_m`; la media con signo evita que el ruido de
    la curvatura (resolución de 1 m) parta una recta en trozos.
    """
    n = int(length_m)
    if n <= 0:
        return []
    curv = [curvature_at(float(d)) for d in range(n)]
    half = smooth_m // 2
    thr = 1.0 / radius_m
    ok = [abs(sum(curv[(d + i) % n] for i in range(-half, half))) / (2 * half) < thr for d in range(n)]
    if all(ok):
        return [(0.0, float(n))]
    first_bad = ok.index(False)  # se empieza justo en una curva para no partir en dos la recta que cruza la meta
    segs: List[Tuple[float, float]] = []
    start: Optional[int] = None
    for j in range(n):
        u = first_bad + j
        if ok[u % n]:
            if start is None:
                start = u
        elif start is not None:
            segs.append((float(start % n), float(u - start)))
            start = None
    if start is not None:
        segs.append((float(start % n), float(first_bad + n - start)))
    return sorted((s, s + span) for s, span in segs if span >= min_len_m)


def select_straights(straights: List[Tuple[float, float]], spec: str) -> List[Tuple[float, float]]:
    """Rectas elegidas por posición en la lista (`"1"`, `"0,1"`); vacío = todas. Error si el índice no existe."""
    if not spec.strip():
        return list(straights)
    picked = []
    for part in spec.split(","):
        part = part.strip()
        if not part.isdigit() or int(part) >= len(straights):
            raise ValueError(f"recta {part!r} no válida: hay {len(straights)} (índices 0 a {len(straights) - 1})")
        picked.append(straights[int(part)])
    return picked


class IdentManeuver:
    """Decide en cada tick si se impone gas/freno (`acel`: gas 1; `rodar`: sin pedales) o conduce el teacher."""

    def __init__(
        self, kind: str, straights: List[Tuple[float, float]], length_m: float, cap_kmh: float = 0.0,
        floor_kmh: float = 30.0, start_margin_m: float = 20.0, end_margin_m: float = 150.0,
        caps_kmh: Optional[Sequence[float]] = None,
    ):
        if kind not in KINDS:
            raise ValueError(f"maniobra desconocida {kind!r}; las válidas son {KINDS}")
        if kind in (KIND_ACCEL, KIND_BOTH) and cap_kmh <= 0:
            raise ValueError(f"`{kind}` necesita un techo de velocidad (cap_kmh > 0)")
        if cap_kmh > MAX_CAP_KMH:
            raise ValueError(f"techo de {cap_kmh:g} km/h por encima del máximo permitido ({MAX_CAP_KMH:g}): el cambio automático "
                             "solo llega a 2ª y a ≈ 120 km/h se descontrola (H50)")
        if kind in (KIND_COAST, KIND_BOTH, KIND_BRAKE) and floor_kmh <= 0:
            raise ValueError(f"`{kind}` necesita un suelo de velocidad (floor_kmh > 0)")
        self.caps_ms: List[float] = []
        if kind == KIND_BRAKE:
            caps = [float(c) for c in (caps_kmh or [])]
            if not caps:
                raise ValueError("`frenar` necesita al menos una velocidad de entrada (caps_kmh)")
            if caps != sorted(caps):
                raise ValueError("las velocidades de entrada de `frenar` deben ir de menor a mayor")
            if min(caps) < floor_kmh + MIN_ENTRY_ABOVE_FLOOR_KMH:
                raise ValueError(f"cada velocidad de entrada debe superar el suelo ({floor_kmh:g}) en {MIN_ENTRY_ABOVE_FLOOR_KMH:g} km/h o más")
            if max(caps) > MAX_CAP_KMH:
                raise ValueError(f"entrada de {max(caps):g} km/h por encima del máximo permitido ({MAX_CAP_KMH:g}): H50")
            self.caps_ms = [c / 3.6 for c in caps]
        self.kind = kind
        self.length_m = float(length_m)
        self.cap_ms = cap_kmh / 3.6
        self.floor_ms = floor_kmh / 3.6
        self.start_margin_m = start_margin_m
        self.end_margin_m = end_margin_m
        self.windows = [(s, e - s) for s, e in straights if e - s > start_margin_m + end_margin_m]
        self.state = IDLE
        self.count = 0  # maniobras lanzadas en la sesión
        self._idx = -1
        self._t0 = 0.0
        self._phase = KIND_ACCEL if kind != KIND_COAST else KIND_COAST  # fase en curso; `acelrodar` pasa de acel a rodar
        self._k = 0  # `frenar`: frenada en curso (índice en la lista de velocidades de entrada)
        self._done: set = set()
        self._neutral_t0: Optional[float] = None  # desde cuándo está en punto muerto (cambio de marcha en curso)

    @property
    def active(self) -> bool:
        return self.state == ACTIVE

    @property
    def drive_source(self) -> str:
        """`ident:acel` o `ident:rodar` según la fase, o `ident:cambio` mientras cambia de marcha: así el análisis separa
        cada tramo y deja fuera los ticks del cambio."""
        return "ident:cambio" if self._neutral_t0 is not None and self.state == ACTIVE else f"ident:{self._phase}"

    def _offset(self, idx: int, lap_distance: float) -> float:
        return (lap_distance - self.windows[idx][0]) % self.length_m

    def _action(self) -> Tuple[float, float]:
        if self._phase == PHASE_BRAKE:
            return (0.0, 1.0)
        return (1.0, 0.0) if self._phase == KIND_ACCEL else (0.0, 0.0)

    def update(
        self, lap_distance: float, speed_ms: float, cte: float, t_s: float, allowed: bool, neutral: bool = False,
    ) -> Optional[Tuple[float, float]]:
        """(gas, freno) a imponer en este tick, o None si conduce el teacher.

        `neutral`: el coche está en punto muerto (marcha 0). Una maniobra en curso lo aguanta hasta `MAX_NEUTRAL_S` soltando
        los pedales, como en un cambio de marcha; una que no ha empezado no arranca. `allowed` debe seguir siendo falso en
        marcha atrás o con el bucle en fine-tune, safety, etc."""
        for i, (_, span) in enumerate(self.windows):
            if self._offset(i, lap_distance) > span:  # fuera de la recta entera: la siguiente pasada vuelve a valer
                self._done.discard(i)

        if self.state == ACTIVE:
            span = self.windows[self._idx][1]
            off = self._offset(self._idx, lap_distance)
            if self._phase == KIND_ACCEL and self.kind == KIND_BOTH and speed_ms >= self.cap_ms:
                self._phase = KIND_COAST  # techo alcanzado: se suelta todo y se mide cómo pierde velocidad
            if self.kind == KIND_BRAKE:
                if self._phase == KIND_ACCEL and speed_ms >= self.caps_ms[self._k]:
                    self._phase = PHASE_BRAKE  # velocidad de entrada alcanzada: a frenar a fondo
                elif self._phase == PHASE_BRAKE and speed_ms <= self.floor_ms:
                    self._k += 1
                    self._phase = KIND_ACCEL  # siguiente frenada (si no hay más, `reached` cierra la pasada)
                reached = self._k >= len(self.caps_ms)
            else:
                reached = speed_ms >= self.cap_ms if self._phase == KIND_ACCEL else speed_ms <= self.floor_ms
            if neutral:
                if self._neutral_t0 is None:
                    self._neutral_t0 = t_s
            else:
                self._neutral_t0 = None
            stuck_neutral = self._neutral_t0 is not None and t_s - self._neutral_t0 > MAX_NEUTRAL_S
            if (not allowed or stuck_neutral or abs(cte) > MAX_CTE_M or off > span - self.end_margin_m or reached
                    or t_s - self._t0 > MAX_ACTIVE_S):
                self.state = IDLE
                self._neutral_t0 = None
                self._done.add(self._idx)
                return None
            if neutral:  # cambio de marcha: se suelta el gas, pero no el freno de una frenada en curso
                return (0.0, 1.0) if self._phase == PHASE_BRAKE else (0.0, 0.0)
            return self._action()

        if not allowed or neutral or abs(cte) > MAX_CTE_M:
            return None
        for i, (_, span) in enumerate(self.windows):
            off = self._offset(i, lap_distance)
            if i in self._done or not (self.start_margin_m <= off <= span - self.end_margin_m):
                continue
            if self.kind == KIND_BRAKE:
                ready = speed_ms * 3.6 > self.floor_ms * 3.6 + COAST_MIN_ABOVE_KMH
            else:
                ready = (speed_ms * 3.6 < self.cap_ms * 3.6 - ACCEL_MIN_BELOW_KMH if self.kind != KIND_COAST
                         else speed_ms * 3.6 > self.floor_ms * 3.6 + COAST_MIN_ABOVE_KMH)
            if ready:
                self.state, self._idx, self._t0 = ACTIVE, i, t_s
                self._phase = KIND_COAST if self.kind == KIND_COAST else KIND_ACCEL
                self._k = 0
                if self.kind == KIND_BRAKE and speed_ms >= self.caps_ms[0]:
                    self._phase = PHASE_BRAKE  # ya entra por encima de la primera velocidad: se frena desde la que lleva
                self.count += 1
                return self._action()
        return None
