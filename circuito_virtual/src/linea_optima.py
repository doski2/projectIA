"""D2 (`circuito_virtual/docs/PLAN.md`): línea de menor tiempo de vuelta con el solver de perfil de velocidad, dentro del pasillo comprobado de la pista.

La línea es un desplazamiento lateral `n(s)` respecto al eje del mapa (`mapa.py`, n positivo a la derecha), una B-spline cúbica con un punto de control cada
`PASO_NUDOS_M` metros (B-spline cúbica periódica: C2, la curvatura no da saltos que el teacher no pueda seguir, y local). El tiempo de una `n(s)` se calcula así:

1. posición `(x, z) = eje(s) + n · derecha`; la línea desplazada tiene otra longitud (más corta por dentro), así que se **remuestrea a un punto por metro de arco**
   antes de pasarla a `perfil_velocidad.Track.from_arrays` (curvatura suavizada como la del teacher y pendiente del eje);
2. `perfil_velocidad.solve` con el coche pedido → tiempo de vuelta.

El optimizador es un descenso por coordenadas sobre los puntos de control (sin SciPy: no está en el entorno), con paso decreciente de 1 m a 5 cm. Un movimiento solo se acepta si
la `n(s)` resultante cabe en el pasillo en **todos** los metros, no solo en el nudo.

**El pasillo** (`pasillo_centro`) es lo que el mapa sabe de la anchura (`bordes_logs.Observaciones`): el borde medido si lo hay y, si no, hasta dónde se comprobó que llega
el asfalto, siempre en posición de rueda; el centro del coche queda a la semivía (0,85 m, sin calibrar hasta D1b) más un margen del borde. El eje (n = 0) siempre
cabe: es la línea suavizada, que el coche ya recorrió en el juego (G1b, V14). Donde no hay bordes medidos el pasillo es estrecho y la línea óptima sale conservadora.

**La línea que se escribe** tiene el mismo formato que `sugo_smooth.json` (`escribir_linea`): un punto por metro de `s` (el `d` es la distancia de vuelta del juego,
que es lo que busca el teacher), con `pos` y el rumbo `ori[1]` nuevos. El resto de campos (velocidad de referencia de 60 km/h, pedales, marcha) se queda como en la
suavizada, porque el modo físico del teacher usa solo la geometría.

Uso:
    python circuito_virtual/src/linea_optima.py [--ritmos 0.697 0.85 1.0] [--paso-nudos 20] [--margen 0.3] [--salida-dir circuito_virtual/pistas/sugo_gp]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "PCARS2-AI" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from circuito_virtual.src import ajuste_ia  # noqa: E402
from circuito_virtual.src import perfil_velocidad as pv  # noqa: E402
from circuito_virtual.src.bordes_logs import Observaciones  # noqa: E402
from circuito_virtual.src.mapa import Mapa  # noqa: E402

PISTA = REPO / "circuito_virtual" / "pistas" / "sugo_gp"
PASO_NUDOS_M = 20.0  # con 30 m sale un 2 %, con 20 m un 3,5 % y con 15 m un 5,3 % (ritmo de la IA): 20 m es una línea más fácil de seguir para la primera prueba en el juego
MARGEN_M = 0.3
PASO_INICIAL_M = 1.0
PASO_FINAL_M = 0.05
MEJORA_MIN_S = 1e-4  # una pasada que gana menos que esto reduce el paso a la mitad
TOLERANCIA_M = 1e-9
RITMOS = (0.697, 0.85, 1.0)  # la IA (V13), un punto intermedio y la envolvente completa


# ---- pasillo -----------------------------------------------------------------------------------------------------------------
def bordes_rueda(obs: Observaciones) -> Tuple[np.ndarray, np.ndarray]:
    """(izquierdo, derecho) de la **rueda** en cada punto del mapa: el borde medido o, si no, la cota «asfalto hasta». NaN donde no hay ninguno."""
    b = obs.bordes()
    return np.where(np.isfinite(b["izq"]), b["izq"], obs.izq_dentro), np.where(np.isfinite(b["dcha"]), b["dcha"], obs.dcha_dentro)


def pasillo_centro(mapa: Mapa, obs: Observaciones, margen_m: float = MARGEN_M, incluir_eje: bool = True) -> Tuple[np.ndarray, np.ndarray]:
    """(n mínima, n máxima) permitidas para el **centro** del coche en cada punto del mapa.

    Rueda: el borde medido, o si no la cota «asfalto hasta» (hasta ahí se comprobó que llega). Centro: esa cota a la semivía y al margen del borde.

    `incluir_eje=True` (como siempre): el eje (n = 0) siempre cabe, aunque el pasillo comprobado sea más estrecho que el coche más el margen; ahí la rueda queda a menos de `margen_m`
    del borde (V35: 759-771 m, ≈ 0,2 m). `incluir_eje=False` (pasillo estricto): el margen se respeta en todas partes; si el pasillo es más estrecho que el coche más el doble del margen
    (cota izquierda > derecha) queda en el punto medio, y donde falta una de las dos cotas el lado desconocido se queda en el eje."""
    rueda_izq, rueda_dcha = bordes_rueda(obs)
    lo = np.nan_to_num(rueda_izq, nan=0.0) + obs.semivia_m + margen_m
    hi = np.nan_to_num(rueda_dcha, nan=0.0) - obs.semivia_m - margen_m
    if incluir_eje:
        return np.minimum(lo, 0.0), np.maximum(hi, 0.0)
    lo = np.where(np.isfinite(rueda_izq), lo, np.minimum(lo, 0.0))
    hi = np.where(np.isfinite(rueda_dcha), hi, np.maximum(hi, 0.0))
    estrecho = lo > hi
    medio = (lo + hi) / 2.0
    return np.where(estrecho, medio, lo), np.where(estrecho, medio, hi)


def holgura_rueda(obs: Observaciones, n: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Distancia (m) de la rueda izquierda y de la derecha de un coche que va por `n` a su borde (medido o comprobado). Negativa = la rueda ya está fuera; NaN sin dato."""
    rueda_izq, rueda_dcha = bordes_rueda(obs)
    return n - obs.semivia_m - rueda_izq, rueda_dcha - (n + obs.semivia_m)


# ---- línea como B-spline ------------------------------------------------------------------------------------------------------
def base_spline(longitud_m: float, s: np.ndarray, paso_nudos_m: float = PASO_NUDOS_M) -> Tuple[np.ndarray, np.ndarray]:
    """Matriz `B` (puntos × puntos de control) tal que `n = B @ c` es la B-spline cúbica periódica de nudos equiespaciados; y la `s` de cada punto de control.

    Es C2 (la curvatura de la línea es continua) y **local**: cada punto del mapa depende solo de 4 puntos de control (4 × `paso_nudos_m` de soporte) y con pesos no
    negativos que suman 1, de modo que `n` nunca sale del rango de esos 4. Una spline interpolante tendría soporte global y cualquier cambio rozaría un tramo estrecho
    del pasillo al otro lado de la pista."""
    k = max(int(round(longitud_m / paso_nudos_m)), 4)
    h = longitud_m / k
    pos = np.mod(np.asarray(s, dtype=float), longitud_m) / h
    i = np.minimum(np.floor(pos).astype(int), k - 1)
    u = pos - i
    pesos = (((1 - u) ** 3) / 6, (3 * u ** 3 - 6 * u ** 2 + 4) / 6, (-3 * u ** 3 + 3 * u ** 2 + 3 * u + 1) / 6, (u ** 3) / 6)
    b = np.zeros((len(pos), k))
    p = np.arange(len(pos))
    for desfase, w in zip((-1, 0, 1, 2), pesos):
        b[p, (i + desfase) % k] += w
    return b, np.arange(k) * h


# ---- geometría y tiempo --------------------------------------------------------------------------------------------------------
def geometria(mapa: Mapa, n: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Posición (x, z) de la línea desplazada `n` en cada punto del eje."""
    return mapa.sn_a_xz(mapa.s, n)


def track_de_n(mapa: Mapa, n: np.ndarray, kappa_half_m: int = pv.KAPPA_HALF_M) -> Tuple[pv.Track, np.ndarray]:
    """`Track` (un punto por metro **de arco** de la línea) y la distancia de arco de cada punto del mapa sobre esa línea."""
    x, z = geometria(mapa, n)
    xc, zc, yc = (np.append(a, a[0]) for a in (x, z, mapa.y))
    cum = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(xc), np.diff(zc)))])
    largo = float(cum[-1])
    n_pts = int(round(largo))
    u = np.arange(n_pts) * (largo / n_pts)
    track = pv.Track.from_arrays(np.interp(u, cum, xc), np.interp(u, cum, zc), np.interp(u, cum, yc), largo, kappa_half_m)
    return track, cum[:-1]


def tiempo_vuelta(mapa: Mapa, n: np.ndarray, coche: pv.CarParams, kappa_half_m: int = pv.KAPPA_HALF_M) -> float:
    return pv.solve(track_de_n(mapa, n, kappa_half_m)[0], coche).time_s


def perfil_en_s(mapa: Mapa, n: np.ndarray, coche: pv.CarParams) -> Tuple[np.ndarray, pv.Profile, pv.Track]:
    """Velocidad (m/s) del solver en cada punto del mapa, el perfil completo y la pista de la línea."""
    track, u_mapa = track_de_n(mapa, n)
    prof = pv.solve(track, coche)
    u = np.arange(track.n) * (track.length_m / track.n)
    return np.interp(u_mapa, u, prof.v_ms), prof, track


# ---- cota local de curvatura (V62) -----------------------------------------------------------------------------------------------
VENTANA_CURV_M = 100  # ventana (m) en la que se compara la variación de curvatura de la línea con la de la suavizada
UMBRAL_KAPPA_FIRMADA = 1e-3  # 1/m: por debajo la línea es casi recta y su signo de κ es ruido, no un cambio de giro
PISO_DK_REL = 0.25  # el límite local de |Δκ| nunca baja de esta fracción del máximo de la suavizada (una recta no tiene límite 0)


def kappa_firmada(mapa: Mapa, n: np.ndarray, paso_m: int = 3) -> np.ndarray:
    """κ con signo de la línea `n` en cada punto del mapa **como la calcula el teacher** (`ReferenceLine.curvature`): el cambio de rumbo entre `paso_m` metros antes y después, dividido
    por `2 · paso_m`. Con el suavizado de `Track` (que usa el solver) los serpenteos de 40-60 m quedaban amortiguados y la cota dejaba pasar lo que el seguidor sí ve (V62).
    El signo sigue la convención del rumbo de `_rumbo` (la de las referencias)."""
    x, z = geometria(mapa, n)
    rumbo = _rumbo(x, z)
    d = np.roll(rumbo, -paso_m) - np.roll(rumbo, paso_m)
    d = (d + np.pi) % (2 * np.pi) - np.pi
    return d / (2.0 * paso_m)


def _max_movil(a: np.ndarray, ventana: int = VENTANA_CURV_M) -> np.ndarray:
    h = ventana // 2
    return np.lib.stride_tricks.sliding_window_view(np.concatenate([a[-h:], a, a[:h]]), 2 * h + 1).max(axis=1)


def _suma_movil(a: np.ndarray, ventana: int = VENTANA_CURV_M) -> np.ndarray:
    h = ventana // 2
    return np.lib.stride_tricks.sliding_window_view(np.concatenate([a[-h:], a, a[:h]]), 2 * h + 1).sum(axis=1)


def _cambios_de_signo(k: np.ndarray) -> np.ndarray:
    """1 en el último punto significativo antes de cada cambio de signo de κ (se ignoran los tramos casi rectos); 0 en el resto."""
    idx = np.flatnonzero(np.abs(k) > UMBRAL_KAPPA_FIRMADA)
    out = np.zeros(len(k))
    if len(idx) >= 2:
        signos = np.sign(k[idx])
        out[idx[signos != np.roll(signos, -1)]] = 1.0
    return out


def perfil_curvatura(mapa: Mapa, n: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """(máximo móvil de |Δκ| entre metros contiguos, nº móvil de cambios de signo de κ) en ventanas de `VENTANA_CURV_M` m, un valor por punto del mapa."""
    k = kappa_firmada(mapa, n)
    return _max_movil(np.abs(np.diff(np.append(k, k[0])))), _suma_movil(_cambios_de_signo(k))


@dataclass
class CotaCurvatura:
    dk_max: np.ndarray  # límite local de |Δκ| por metro
    cambios_max: np.ndarray  # límite local de cambios de signo de κ en la ventana


def cota_curvatura(mapa: Mapa, n_ref: np.ndarray, n_ini: np.ndarray, rel: float) -> CotaCurvatura:
    """Cota local respecto a la línea `n_ref` (la suavizada, n = 0): |Δκ| ≤ `rel` veces el suyo en la misma ventana (y no menos de `PISO_DK_REL` de su máximo) y ningún cambio de
    signo de κ que ella no tenga. Si la línea de partida `n_ini` ya la pasa en algún tramo, ahí el límite es el de la partida (no empeora), como los otros topes."""
    dk_ref, c_ref = perfil_curvatura(mapa, n_ref)
    dk_ini, c_ini = perfil_curvatura(mapa, n_ini)
    piso = PISO_DK_REL * float(dk_ref.max())
    return CotaCurvatura(np.maximum(np.maximum(rel * dk_ref, piso), dk_ini), np.maximum(c_ref, c_ini))


def cumple_cota_curvatura(mapa: Mapa, n: np.ndarray, cota: CotaCurvatura) -> bool:
    dk, cambios = perfil_curvatura(mapa, n)
    return bool(np.all(dk <= cota.dk_max + 1e-12) and np.all(cambios <= cota.cambios_max + 1e-9))


def medir_curvatura_local(mapa: Mapa, n: np.ndarray, n_ref: np.ndarray) -> Tuple[float, int]:
    """(mayor cociente entre el |Δκ| local de `n` y el de `n_ref` —con el mismo piso—, nº de puntos del mapa con más cambios de signo de κ que `n_ref` en su ventana)."""
    dk_ref, c_ref = perfil_curvatura(mapa, n_ref)
    dk, c = perfil_curvatura(mapa, n)
    piso = PISO_DK_REL * float(dk_ref.max())
    return float(np.max(dk / np.maximum(dk_ref, piso))), int(np.sum(c > c_ref + 1e-9))


# ---- optimizador ----------------------------------------------------------------------------------------------------------------
@dataclass
class Resultado:
    n: np.ndarray  # por punto del mapa
    nudos: np.ndarray
    s_nudos: np.ndarray
    tiempo_s: float
    tiempo_base_s: float  # con n = 0 (línea suavizada)
    barridos: int
    evaluaciones: int
    historial: List[Tuple[int, float, float]] = field(default_factory=list)  # (barrido, paso, tiempo)
    salto_max: float = 0.0  # salto máx. de |κ| entre metros contiguos de la línea final
    pendiente_max: float = 0.0  # |dn/ds| máx. de la línea final


def punto_inicial(b: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Puntos de control más cercanos al eje (0) cuya spline cabe en el pasillo.

    `n` es una combinación convexa de los 4 puntos de control que la sostienen: si cada punto de control está entre la mayor cota inferior y la menor cota superior de todos
    los puntos que sostiene, `n` cabe en todos. Si el pasillo es de verdad más estrecho que eso (cota inferior > superior) se queda en el punto medio y puede no caber.
    Con un pasillo que incluye el eje (`lo <= 0 <= hi`) devuelve ceros."""
    sostiene = b > 0.0
    cota_inf = np.array([lo[sostiene[:, j]].max() for j in range(b.shape[1])])
    cota_sup = np.array([hi[sostiene[:, j]].min() for j in range(b.shape[1])])
    return np.where(cota_inf > cota_sup, (cota_inf + cota_sup) / 2.0, np.clip(0.0, cota_inf, cota_sup))


def medir_linea(mapa: Mapa, n: np.ndarray, coche: pv.CarParams) -> Tuple[float, float, float]:
    """(tiempo de vuelta, salto máx. de |κ|, |dn/ds| máx.) de la línea `n`; se calcula la pista una sola vez."""
    track = track_de_n(mapa, n)[0]
    pendiente = np.abs(np.roll(n, -1) - np.roll(n, 1)) / 2.0  # un punto por metro de s
    return pv.solve(track, coche).time_s, curvatura_continua(track)["salto_max"], float(pendiente.max())


def optimizar(mapa: Mapa, lo: np.ndarray, hi: np.ndarray, coche: pv.CarParams, paso_nudos_m: float = PASO_NUDOS_M,
              paso_inicial_m: float = PASO_INICIAL_M, paso_final_m: float = PASO_FINAL_M, max_barridos: int = 60,
              progreso: Optional[Callable[[int, float, float], None]] = None,
              salto_max: Optional[float] = None, pendiente_max: Optional[float] = None, curvatura_local_rel: Optional[float] = None) -> Resultado:
    """Descenso por coordenadas sobre los nudos. Parte del punto más cercano al eje que cabe en el pasillo (el eje mismo si cabe).

    `salto_max` y `pendiente_max` (opcionales) topan el salto de |κ| entre metros contiguos y |dn/ds| de toda la línea: un movimiento que los pase se descarta aunque gane tiempo.
    Si la línea de partida ya los pasa, el tope es el de la línea de partida (no empeora).
    `curvatura_local_rel` (opcional, V62) añade la cota local de curvatura de `cota_curvatura`: en ventanas de `VENTANA_CURV_M` m la variación de κ no pasa de ese múltiplo de la de la
    línea suavizada y no aparecen cambios de signo de κ que la suavizada no tenga (el seguidor falla donde la línea serpentea y la suavizada no, V61)."""
    b, s_nudos = base_spline(mapa.longitud_m, mapa.s, paso_nudos_m)
    k = punto_inicial(b, lo, hi)
    n = b @ k
    lo, hi = np.minimum(lo, n), np.maximum(hi, n)  # si el pasillo es más estrecho que el coche, la línea de partida no puede empeorar
    evals = 0

    def medir(cand: np.ndarray) -> Tuple[float, bool]:
        nonlocal evals
        evals += 1
        t, salto, pend = medir_linea(mapa, cand, coche)
        return t, salto <= tope_salto and pend <= tope_pend and (cota is None or cumple_cota_curvatura(mapa, cand, cota))

    base = tiempo_vuelta(mapa, np.zeros(mapa.n_puntos), coche) if np.any(n) else None
    best, salto0, pend0 = medir_linea(mapa, n, coche)
    base = best if base is None else base
    tope_salto = max(salto_max, salto0) if salto_max is not None else np.inf
    tope_pend = max(pendiente_max, pend0) if pendiente_max is not None else np.inf
    cota = cota_curvatura(mapa, np.zeros(mapa.n_puntos), n, curvatura_local_rel) if curvatura_local_rel is not None else None
    paso = paso_inicial_m
    historial: List[Tuple[int, float, float]] = []
    barridos = 0
    rng = np.random.default_rng(0)
    while paso >= paso_final_m - 1e-12 and barridos < max_barridos:
        antes = best
        for j in rng.permutation(len(k)):
            col = b[:, j]
            for signo in (+1.0, -1.0):
                avanzo = False
                while True:  # mientras mejore en esa dirección, sigue
                    cand = n + col * (signo * paso)
                    if np.any(cand < lo - TOLERANCIA_M) or np.any(cand > hi + TOLERANCIA_M):
                        break
                    t, admitida = medir(cand)
                    if admitida and t < best - 1e-9:
                        best, n, k[j] = t, cand, k[j] + signo * paso
                        avanzo = True
                    else:
                        break
                if avanzo:
                    break  # no pruebes la otra dirección si esta ya mejoró
        barridos += 1
        historial.append((barridos, paso, best))
        if progreso:
            progreso(barridos, paso, best)
        if antes - best < MEJORA_MIN_S:
            paso /= 2.0
    _, salto_f, pend_f = medir_linea(mapa, n, coche)
    return Resultado(n, k, s_nudos, best, base, barridos, evals, historial, salto_f, pend_f)


# ---- salida --------------------------------------------------------------------------------------------------------------------
def _rumbo(x: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Rumbo con la convención de `ori[1]` de las referencias: atan2(−dz, dx) − π/2 (std de 0,007 rad con el de la suavizada)."""
    return np.arctan2(-(np.roll(z, -1) - np.roll(z, 1)), np.roll(x, -1) - np.roll(x, 1))


def escribir_linea(mapa: Mapa, n: np.ndarray, datos_suavizada: Dict, meta: Optional[Dict] = None) -> Dict:
    """Copia de la referencia suavizada con `pos` y el rumbo de la línea `n`. Hay un punto por cada punto del mapa, con la misma `d`."""
    pts = datos_suavizada["points"]
    if len(pts) != mapa.n_puntos or not np.allclose([p["d"] for p in pts], mapa.s):
        raise ValueError("la referencia y el mapa no tienen los mismos puntos")
    x0, z0 = geometria(mapa, np.zeros(mapa.n_puntos))
    x1, z1 = geometria(mapa, n)
    giro = _rumbo(x1, z1) - _rumbo(x0, z0)
    giro = (giro + np.pi) % (2 * np.pi) - np.pi
    out = json.loads(json.dumps(datos_suavizada))
    for p, ax, az, g in zip(out["points"], x1, z1, giro):
        p["pos"][0] = round(float(ax), 3)
        p["pos"][2] = round(float(az), 3)
        p["ori"][1] = round(float((p["ori"][1] + g + np.pi) % (2 * np.pi) - np.pi), 5)
    out["optima"] = {"origen": "linea_optima.py (D2)", **(meta or {})}
    return out


def curvatura_continua(track: pv.Track) -> Dict[str, float]:
    """|κ| máxima y salto máximo de |κ| entre metros contiguos: cuánto exige la línea al seguidor."""
    k = track.kappa
    return {"kappa_max": float(k.max()), "salto_max": float(np.abs(np.diff(np.append(k, k[0]))).max())}


def coche_ia(n_ajuste: int = 10) -> pv.CarParams:
    """Envolventes de la IA (aceleración, frenada y lateral `μ + k·v²`) ajustadas a las `n_ajuste` primeras vueltas (V13)."""
    return ajuste_ia.ajustar(ajuste_ia.cargar()[:n_ajuste])


COCHE_A1 = REPO / "circuito_virtual" / "coches" / "formula_rookie" / "parametros_a1.json"


def coche_a1(mu: float, k: float = 0.0, ruta: Path = COCHE_A1, tope_kmh: Optional[float] = None) -> pv.CarParams:
    """El coche **que conduce el teacher**: tablas de aceleración y frenada de A1 (tope de velocidad `v_known_kmh` = 140) y un límite lateral fijo `μ` (sin `k·v²`).

    Es el modelo con el que `aislado.py --lat-accel-limit μ` ha medido el tiempo de vuelta (V26-V31); la línea de V15 se optimizó con las envolventes de la IA, que no son las mismas."""
    base = pv.load_params(ruta)
    return pv.CarParams(base.accel, base.brake, mu, k, base.v_known_kmh if tope_kmh is None else tope_kmh, base.brake_delay_s)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--ritmos", type=float, nargs="+", default=list(RITMOS))
    ap.add_argument("--coche-a1-mu", type=float, default=None,
                    help="optimiza para el coche del teacher (A1 con límite lateral fijo MU, p. ej. 9) y escribe sugo_optima_a1mu<MU>.json; sin esto, las envolventes de la IA por ritmo")
    ap.add_argument("--paso-nudos", type=float, default=PASO_NUDOS_M)
    ap.add_argument("--margen", type=float, default=MARGEN_M)
    ap.add_argument("--max-barridos", type=int, default=60)
    ap.add_argument("--salida-dir", type=Path, default=PISTA)
    ap.add_argument("--observaciones", default="observaciones_logs.json", help="archivo de observaciones (en --salida-dir) del que sale el pasillo; p. ej. observaciones_pasillo_d11.json (video_vuelta, D12)")
    ap.add_argument("--pasillo-estricto", action="store_true",
                    help="no obliga a que el eje quepa: el margen al borde se respeta también donde el pasillo comprobado es más estrecho que el coche (V35, 759-771 m)")
    ap.add_argument("--salto-max-rel", type=float, default=None,
                    help="tope del salto de |κ| entre metros contiguos, como múltiplo del de la línea suavizada (1 = no peor que ella; V35)")
    ap.add_argument("--pendiente-max", type=float, default=None, help="tope de |dn/ds| (m de desplazamiento lateral por m de recorrido) de la línea")
    ap.add_argument("--tope-kmh", type=float, default=None,
                    help="con --coche-a1-mu: tope de velocidad del solver en km/h (por defecto el de las tablas de A1, 140; las líneas a1mu9 y a1mu9b se hicieron con 125)")
    ap.add_argument("--curvatura-local-rel", type=float, default=None,
                    help="cota local de curvatura (V62): en ventanas de 100 m la variación de κ no pasa de este múltiplo de la de la suavizada y no hay cambios de signo de κ que ella no tenga (p. ej. 1,5)")
    ap.add_argument("--nombre", default=None, help="nombre del archivo de salida sin extensión (por defecto sugo_optima_a1mu<MU> o sugo_optima_f<ritmo>)")
    args = ap.parse_args(argv)
    mapa = Mapa.cargar(args.salida_dir / "mapa.json")
    obs = Observaciones.de_dict(json.loads((args.salida_dir / args.observaciones).read_text(encoding="utf-8")))
    suavizada = json.loads((args.salida_dir / "sugo_smooth.json").read_text(encoding="utf-8"))
    lo, hi = pasillo_centro(mapa, obs, args.margen, incluir_eje=not args.pasillo_estricto)
    if args.coche_a1_mu is not None:
        _optimizar_y_escribir(mapa, obs, suavizada, lo, hi, coche_a1(args.coche_a1_mu, tope_kmh=args.tope_kmh), args.nombre or f"sugo_optima_a1mu{args.coche_a1_mu:g}",
                              {"modelo": f"coche A1, mu {args.coche_a1_mu:g}, k 0, tope {args.tope_kmh or coche_a1(args.coche_a1_mu).v_known_kmh:g}"}, args)
        return 0
    coche = coche_ia()
    print(f"pasillo del centro: ancho mediano {np.median(hi - lo):.2f} m, mínimo {np.min(hi - lo):.2f} m; {len(base_spline(mapa.longitud_m, mapa.s, args.paso_nudos)[1])} puntos de control", flush=True)
    for f in args.ritmos:
        print(f"\n== ritmo f = {f:g} ==", flush=True)
        _optimizar_y_escribir(mapa, obs, suavizada, lo, hi, ajuste_ia.escalar(coche, f), args.nombre or f"sugo_optima_f{round(f * 1000)}", {"ritmo_f": f}, args)
    return 0


def _optimizar_y_escribir(mapa, obs, suavizada, lo, hi, coche, nombre, meta_extra, args) -> None:
    t0 = time.time()
    cero = curvatura_continua(track_de_n(mapa, np.zeros(mapa.n_puntos))[0])
    salto_max = args.salto_max_rel * cero["salto_max"] if args.salto_max_rel is not None else None
    res = optimizar(mapa, lo, hi, coche, args.paso_nudos, max_barridos=args.max_barridos,
                    progreso=lambda b, p, t: print(f"  barrido {b:2d}  paso {p:.3f} m  tiempo {t:.3f} s", flush=True),
                    salto_max=salto_max, pendiente_max=args.pendiente_max, curvatura_local_rel=args.curvatura_local_rel)
    cociente, nuevos = medir_curvatura_local(mapa, res.n, np.zeros(mapa.n_puntos))
    hizq, hdcha = holgura_rueda(obs, res.n)
    holgura = np.fmin(hizq, hdcha)
    meta = {**meta_extra, "margen_m": args.margen, "paso_nudos_m": args.paso_nudos, "tiempo_previsto_s": round(res.tiempo_s, 3),
            "tiempo_suavizada_s": round(res.tiempo_base_s, 3), "semivia_m": obs.semivia_m, "pasillo_estricto": bool(args.pasillo_estricto),
            "salto_max_kappa": round(res.salto_max, 6), "salto_max_suavizada": round(cero["salto_max"], 6), "pendiente_max": round(res.pendiente_max, 4),
            "holgura_min_rueda_m": round(float(np.nanmin(holgura)), 3),
            "curvatura_local_rel": args.curvatura_local_rel, "dk_local_max_sobre_suavizada": round(cociente, 3), "puntos_con_cambios_de_signo_nuevos": nuevos}
    print(f"  salto de |κ| máx. {res.salto_max:.5f} (suavizada {cero['salto_max']:.5f}); |dn/ds| máx. {res.pendiente_max:.3f}; holgura mínima de la rueda al borde "
          f"{np.nanmin(holgura):.2f} m, {int(np.sum(holgura < args.margen - 1e-3))} m con menos de {args.margen:g} m", flush=True)
    print(f"  variación local de κ: hasta {cociente:.2f} veces la de la suavizada; {nuevos} puntos del mapa con más cambios de signo de κ que ella", flush=True)
    salida = args.salida_dir / f"{nombre}.json"
    salida.write_text(json.dumps(escribir_linea(mapa, res.n, suavizada, meta)), encoding="utf-8")
    np.save(args.salida_dir / f"{nombre}_n.npy", res.n)
    print(f"  {res.tiempo_base_s:.3f} s -> {res.tiempo_s:.3f} s ({100 * (res.tiempo_s / res.tiempo_base_s - 1):+.2f} %) en {res.barridos} barridos, "
          f"{res.evaluaciones} evaluaciones, {time.time() - t0:.0f} s -> {salida}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
