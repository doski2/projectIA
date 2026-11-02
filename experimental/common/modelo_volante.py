"""Modelo volante -> guiñada ajustado a los logs y simulación en lazo cerrado de la ley de volante del teacher (V38, V39).

Sirve para comprobar **sin juego** el efecto de las ganancias del teacher (`--steer-ff-gain`, `k_heading`...) antes de gastar una sesión. Es aproximado: con la planta ajustada el
error rms del CTE simulado es de 0,35-0,38 m frente a 0,6 m si el CTE no se moviera, y los picos salen entre el 75 y el 110 % de los reales. Por eso se compara cada variante bajo
**varias plantas** (la ajustada y dos extremas) y solo se fía de lo que mejora en todas.

Dos plantas (60 Hz, igual que el log): `Planta` de primer orden (V39) y `Bicicleta` (V41: modelo lineal de una pista con deriva lateral como segundo estado, que ve el adelanto de las
entradas en curva cerrada que la de primer orden no ve).
  Planta:    guiñada' = (G(v) · volante − guiñada) / τ,   G(v) = −v / (A + B·v²) · ganancia   (volante negativo = izquierda = guiñada positiva)
  Bicicleta: β' = (Fyf + Fyr)/(m v) − r,   r' = (a·Fyf − b·Fyr)/Iz,   Fyf = −Cf (β + a r/v − δ),   Fyr = −Cr (β − b r/v),   δ = −c · volante
Cinemática y ley de volante, comunes a las dos:
  rumbo'   = guiñada − κ_línea · v                (comprobado con los logs: correlación 0,90, pendiente 0,93)
  CTE'     = −v · sin(rumbo)                      (correlación 0,99, pendiente 0,98)
y el volante lo calcula la misma ley que `TeachingController.compute_steering` (CTE con ganancia por velocidad, rumbo, anticipación 2,5·κ + 1,8·κ(v·T) por 1 + g·v², suavizado 0,35;
sin la corrección por deriva). Un tick de retardo del juego es despreciable (`game_steer` ≈ `steering`).

Uso:
    python experimental/common/modelo_volante.py --ajuste "LOG|REF" ["LOG|REF" ...] --prueba "LOG|REF"
(LOG es el .jsonl de una sesión de A2.0 y REF la línea que seguía; se usa la vuelta 2).
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "PCARS2-AI" / "src", REPO / "experimental" / "common"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

DT = 1.0 / 60.0
VENTANA_AJUSTE = 90  # ticks (1,5 s) de las ventanas del ajuste de la guiñada


@dataclass(frozen=True)
class Planta:
    """Respuesta del coche: guiñada estacionaria = v · volante / (a + b·v²) y constante de tiempo `tau`; `gain_scale` y `tau_scale` la perturban."""
    a: float
    b: float
    tau: float
    gain_scale: float = 1.0
    tau_scale: float = 1.0

    def guinada_estacionaria(self, v: float, volante: float) -> float:
        return -v / (self.a + self.b * v * v) * volante * self.gain_scale

    def estado_inicial(self, yaw: Any, beta: Any) -> Any:
        """Estado de partida: la guiñada (escalar, o un array con una ventana por elemento en el ajuste)."""
        return yaw

    def paso(self, estado, v, volante):
        return estado + DT / (self.tau * self.tau_scale) * (self.guinada_estacionaria(v, volante) - estado)

    @staticmethod
    def guinada(estado) -> float:
        return float(estado)

    def necesario(self, v: float) -> float:
        """Volante por unidad de κ que pide el coche en curva estacionaria a la velocidad v."""
        return (self.a + self.b * v * v) / self.gain_scale


@dataclass(frozen=True)
class Bicicleta:
    """Modelo lineal de una pista. `kf` y `kr`: rigidez de deriva por masa de cada eje (m/s² por rad); `a`: distancia del centro de gravedad al eje delantero (m); `largo`: batalla (supuesta, 2,7 m);
    `c`: ángulo de las ruedas por unidad de volante (rad); `ciz`: momento de inercia / (m · a · b); `signo_beta`: signo con que el log registra la deriva respecto al del modelo (izquierda positiva)."""
    kf: float
    kr: float
    a: float
    c: float
    ciz: float = 1.0
    largo: float = 2.7
    signo_beta: float = 1.0
    gain_scale: float = 1.0
    tau_scale: float = 1.0  # sin uso: solo para que `calibrar_cerrado` y `ff_sobre_necesario` traten igual a las dos plantas

    @property
    def b(self) -> float:
        return self.largo - self.a

    def estado_inicial(self, yaw: Any, beta: Any) -> Any:
        """Estado de partida (deriva en el signo del modelo, guiñada); acepta escalares o arrays."""
        return (self.signo_beta * beta, yaw)

    def paso(self, estado, v, volante):
        beta, r = estado
        v = np.maximum(v, 5.0)
        delta = -self.c * self.gain_scale * volante
        fyf = -self.kf * (beta + self.a * r / v - delta)
        fyr = -self.kr * (beta - self.b * r / v)
        iz = self.ciz * self.a * self.b
        return beta + DT * ((fyf + fyr) / v - r), r + DT * (self.a * fyf - self.b * fyr) / iz

    @staticmethod
    def guinada(estado) -> float:
        return float(estado[1])

    def gradiente_subviraje(self) -> float:
        """K de la guiñada estacionaria r = v · δ / (L + K·v²), en s²/m."""
        return (self.b / self.kf - self.a / self.kr) / self.largo

    def necesario(self, v: float) -> float:
        """Volante por unidad de κ que pide el coche en curva estacionaria: (L + K·v²) / c."""
        return (self.largo + self.gradiente_subviraje() * v * v) / (self.c * self.gain_scale)


@dataclass(frozen=True)
class Ley:
    """Ganancias del teacher que se prueban (los valores por defecto son los de A2.0 en V35)."""
    k_cte: float = 0.12
    v0_kmh: float = 70.0  # `--lat-gain-v0-kmh`
    k_heading: float = 0.55
    k_curvature: float = 2.5
    k_lookahead: float = 1.8
    ff_gain: float = 0.003  # `--steer-ff-gain` con `--steer-ff-v0-kmh 0`
    ff_cap_kmh: float = 0.0  # tope de velocidad en el factor 1 + g·v² (0 = sin tope); opción `--steer-ff-cap-kmh` del teacher (V57)
    preview_s: float = 0.3  # `--steer-preview-s`
    smooth: float = 0.35

    def factor_ff(self, v: float) -> float:
        """Factor de la anticipación 1 + g · v², con v limitada a `ff_cap_kmh` si hay tope."""
        if self.ff_cap_kmh > 0.0:
            v = min(v, self.ff_cap_kmh / 3.6)
        return 1.0 + self.ff_gain * v * v


def ff_sobre_necesario(planta, v: float, ley: Ley) -> float:
    """Cociente entre el volante por unidad de κ que da la anticipación en curva estacionaria y el que pide el coche (> 1: la anticipación se pasa)."""
    return (ley.k_curvature + ley.k_lookahead) * ley.factor_ff(v) / planta.necesario(v)


def tabla_curvatura(ref) -> Tuple[np.ndarray, np.ndarray]:
    """(distancia, κ) cada 0,5 m con la curvatura del teacher (`ReferenceLine.curvature`), para interpolar rápido."""
    largo = int(ref.track_length)
    xs = np.arange(0.0, largo + 60.0, 0.5)
    return xs, np.array([ref.curvature(x % largo) for x in xs])


def cargar_vuelta(log: Path, referencia: Path, vuelta: int = 2) -> Dict[str, np.ndarray]:
    """Series de una vuelta del log (distancia, v en m/s, CTE, error de rumbo, volante ordenado, guiñada) y la tabla de curvatura de la línea que seguía."""
    from reference_recorder import ReferenceLine  # noqa: PLC0415
    import resumen_sesion as rs  # noqa: PLC0415

    ref = ReferenceLine.load(str(referencia))
    tk = [t for t in rs.cargar_ticks(Path(log)) if t["lap"] == vuelta]
    if len(tk) < 600:
        raise ValueError(f"{log}: la vuelta {vuelta} tiene solo {len(tk)} ticks")
    d = {k: np.array([t[k] for t in tk], float) for k in ("t_s", "lap_distance", "signed_cte", "heading_err", "steering")}
    d["v"] = np.array([t["speed_kmh"] for t in tk], float) / 3.6
    d["yaw"] = np.array([t["vehicle"]["yaw_rate"] for t in tk], float)
    lv = np.array([t["vehicle"]["local_velocity"] for t in tk], float)
    d["beta"] = np.arctan2(lv[:, 0], -lv[:, 2])  # deriva lateral (rad) con el signo del juego
    d["tabla"] = tabla_curvatura(ref)  # type: ignore[assignment]
    return d


# ---- ajuste de la planta -----------------------------------------------------------------------------------------------------------------
def _ventanas(v: np.ndarray, n: int, paso: int = 30, v_min: float = 15.0) -> np.ndarray:
    return np.array([i for i in range(10, n - VENTANA_AJUSTE - 1, paso) if v[i:i + VENTANA_AJUSTE].min() > v_min], dtype=int)


def error_guinada(vuelta: Dict[str, np.ndarray], idx: np.ndarray, a: float, b: float, tau: float) -> float:
    """Error rms de la guiñada simulada con el volante registrado (lazo abierto) en ventanas de 1,5 s que arrancan de la guiñada registrada."""
    y = vuelta["yaw"][idx].copy()
    suma, n = 0.0, 0
    for k in range(VENTANA_AJUSTE):
        j = idx + k
        v = vuelta["v"][j]
        y = y + (DT / tau) * (-v / (a + b * v * v) * vuelta["steering"][j] - y)
        e = y - vuelta["yaw"][j + 1]
        suma += float(np.sum(e * e))
        n += len(e)
    return math.sqrt(suma / max(n, 1))


def ajustar_guinada(vueltas: Sequence[Dict[str, np.ndarray]]) -> Tuple[Planta, float]:
    """Mínimos cuadrados (rejilla gruesa y refinado por coordenadas) de A, B y τ sobre las vueltas dadas. Devuelve la planta y el error rms de la guiñada (rad/s)."""
    conj = [(v, _ventanas(v["v"], len(v["yaw"]))) for v in vueltas]
    conj = [(v, i) for v, i in conj if len(i)]
    if not conj:
        raise ValueError("ninguna ventana con velocidad suficiente")

    def total(a: float, b: float, tau: float) -> float:
        return math.sqrt(float(np.mean([error_guinada(v, i, a, b, tau) ** 2 for v, i in conj])))

    mejor = min(((total(a, b, t), a, b, t) for a in (2, 4, 6, 8, 10, 12) for b in (0.002, 0.004, 0.008, 0.012, 0.016, 0.022) for t in (0.05, 0.1, 0.15, 0.2, 0.3, 0.45)))
    e, a, b, tau = mejor
    for _ in range(3):
        for nombre in ("a", "b", "tau"):
            for f in (0.8, 0.9, 1.1, 1.25):
                cand = {"a": a, "b": b, "tau": tau}
                cand[nombre] *= f
                ee = total(cand["a"], cand["b"], cand["tau"])
                if ee < e:
                    e, a, b, tau = ee, cand["a"], cand["b"], cand["tau"]
    return Planta(a, b, tau), e


def _error_bicicleta(conj, p: Bicicleta, sigma_r: float, sigma_b: float) -> float:
    suma, n = 0.0, 0
    for vuelta, idx in conj:
        est = p.estado_inicial(vuelta["yaw"][idx].copy(), vuelta["beta"][idx].copy())
        for k in range(VENTANA_AJUSTE):
            j = idx + k
            est = p.paso(est, vuelta["v"][j], vuelta["steering"][j])
            er = (est[1] - vuelta["yaw"][j + 1]) / sigma_r
            eb = (est[0] - p.signo_beta * vuelta["beta"][j + 1]) / sigma_b
            suma += float(np.sum(er * er + eb * eb))
            n += 2 * len(idx)
    return math.sqrt(suma / max(n, 1))


def ajustar_bicicleta(vueltas: Sequence[Dict[str, np.ndarray]], sigma_r: float = 0.05, sigma_b: float = 0.012) -> Tuple[Bicicleta, float, float]:
    """Ajusta kf, kr, a, c y ciz (largo fijo 2,7 m) a guiñada y deriva lateral en ventanas de 1,5 s, con descenso por coordenadas y los dos signos de la deriva.

    Devuelve (planta, error rms normalizado, error rms de la guiñada en rad/s)."""
    conj = [(v, _ventanas(v["v"], len(v["yaw"]))) for v in vueltas]
    conj = [(v, i) for v, i in conj if len(i)]
    if not conj:
        raise ValueError("ninguna ventana con velocidad suficiente")
    limites = {"kf": (20.0, 800.0), "kr": (20.0, 800.0), "a": (0.8, 1.9), "c": (0.08, 0.7), "ciz": (0.3, 2.5)}
    mejor_total: Optional[Tuple[float, Bicicleta]] = None
    for signo in (1.0, -1.0):
        p = Bicicleta(kf=205.0, kr=205.0, a=1.2, c=0.27, ciz=1.0, signo_beta=signo)
        e = _error_bicicleta(conj, p, sigma_r, sigma_b)
        for factor in (2.0, 1.5, 1.25, 1.1, 1.04):
            for _ in range(4):
                mejora = False
                for nombre, (lo, hi) in limites.items():
                    for f in (factor, 1.0 / factor):
                        cand = replace(p, **{nombre: min(hi, max(lo, getattr(p, nombre) * f))})
                        ee = _error_bicicleta(conj, cand, sigma_r, sigma_b)
                        if ee < e - 1e-9:
                            p, e, mejora = cand, ee, True
                if not mejora:
                    break
        if mejor_total is None or e < mejor_total[0]:
            mejor_total = (e, p)
    assert mejor_total is not None
    e, p = mejor_total
    suma, n = 0.0, 0
    for vuelta, idx in conj:
        est = p.estado_inicial(vuelta["yaw"][idx].copy(), vuelta["beta"][idx].copy())
        for k in range(VENTANA_AJUSTE):
            j = idx + k
            est = p.paso(est, vuelta["v"][j], vuelta["steering"][j])
            suma += float(np.sum((est[1] - vuelta["yaw"][j + 1]) ** 2))
            n += len(idx)
    return p, e, math.sqrt(suma / max(n, 1))


# ---- simulación en lazo cerrado ---------------------------------------------------------------------------------------------------------------
def simular(vuelta: Dict[str, np.ndarray], s0: float, s1: float, planta, ley: Ley = Ley()) -> Tuple[np.ndarray, np.ndarray]:
    """Ventana [s0, s1] m de la vuelta, desde el estado registrado en s0 y con la velocidad registrada. Devuelve (distancia, CTE simulado)."""
    xs, kt = vuelta["tabla"]
    d = vuelta["lap_distance"]
    i0 = int(np.searchsorted(d, s0))
    s = float(d[i0])
    cte, rumbo, yaw, volante = float(vuelta["signed_cte"][i0]), float(vuelta["heading_err"][i0]), float(vuelta["yaw"][i0]), float(vuelta["steering"][i0])
    beta0 = float(vuelta["beta"][i0]) if "beta" in vuelta else 0.0
    estado = planta.estado_inicial(yaw, beta0)
    v0 = ley.v0_kmh / 3.6
    out_s: List[float] = []
    out_c: List[float] = []
    while s < s1:
        v = float(np.interp(s, d, vuelta["v"]))
        k_cte = ley.k_cte * ((v0 / v) ** 2 if v0 > 0 and v > v0 else 1.0)
        kap = float(np.interp(s, xs, kt))
        kap_prev = float(np.interp(s + max(4.0, v * ley.preview_s), xs, kt))
        ff = (ley.k_curvature * kap + ley.k_lookahead * kap_prev) * ley.factor_ff(v)
        raw = max(-1.0, min(1.0, -k_cte * cte + ley.k_heading * rumbo - ff))
        volante += ley.smooth * (raw - volante)
        estado = planta.paso(estado, v, volante)
        yaw = planta.guinada(estado)
        rumbo += DT * (yaw - kap * v)
        cte += -v * math.sin(rumbo) * DT
        s += v * DT
        out_s.append(s)
        out_c.append(cte)
    return np.array(out_s), np.array(out_c)


def error_cte(vuelta: Dict[str, np.ndarray], planta, ley: Ley = Ley(), largo_m: float = 200.0, paso_m: float = 150.0) -> Tuple[float, float]:
    """(error rms del CTE simulado frente al registrado, media del cociente de picos simulado / registrado) en ventanas repartidas por la vuelta."""
    errs, razones = [], []
    d = vuelta["lap_distance"]
    for s0 in np.arange(300.0, d.max() - largo_m, paso_m):
        m = (d >= s0) & (d <= s0 + largo_m)
        if m.sum() < 100:
            continue
        ss, cs = simular(vuelta, s0, s0 + largo_m, planta, ley)
        ci = np.interp(d[m], ss, cs, left=np.nan, right=np.nan)
        ok = ~np.isnan(ci)
        errs.append(math.sqrt(float(np.mean((ci[ok] - vuelta["signed_cte"][m][ok]) ** 2))))
        razones.append(float(np.abs(ci[ok]).max() / max(np.abs(vuelta["signed_cte"][m][ok]).max(), 0.2)))
    return float(np.mean(errs)), float(np.mean(razones))


def calibrar_cerrado(vueltas: Sequence[Dict[str, np.ndarray]], planta):
    """Ajusta `gain_scale` y `tau_scale` a lazo cerrado (mínimo error de CTE): en lazo cerrado un error del 20 % en la guiñada se amplifica."""
    mejor: Optional[Tuple[float, Any]] = None
    for g in (0.85, 0.95, 1.0, 1.1, 1.25):
        for t in ((0.5, 0.75, 1.0, 1.5) if isinstance(planta, Planta) else (1.0,)):
            p = replace(planta, gain_scale=g, tau_scale=t)
            e = float(np.mean([error_cte(v, p)[0] for v in vueltas]))
            if mejor is None or e < mejor[0]:
                mejor = (e, p)
    assert mejor is not None
    return mejor[1]


def picos(vueltas: Sequence[Dict[str, np.ndarray]], planta, ley: Ley, tramos: Dict[str, Tuple[float, float]]) -> Dict[str, float]:
    """|CTE| máx. simulado (media de las vueltas) en cada tramo, y pico medio y rms medio en ventanas de 200 m de toda la vuelta."""
    res: Dict[str, float] = {}
    for nombre, (s0, s1) in tramos.items():
        res[nombre] = float(np.mean([np.abs(simular(v, s0, s1, planta, ley)[1]).max() for v in vueltas]))
    pk, rm = [], []
    for v in vueltas:
        for s0 in np.arange(300.0, v["lap_distance"].max() - 200.0, 150.0):
            _, cs = simular(v, s0, s0 + 200.0, planta, ley)
            pk.append(np.abs(cs).max())
            rm.append(math.sqrt(float(np.mean(cs ** 2))))
    res["pico medio"] = float(np.mean(pk))
    res["rms medio"] = float(np.mean(rm))
    res["ventanas > 1,8 m"] = float(np.sum(np.array(pk) > 1.8)) / len(vueltas)
    return res


def _media(x: np.ndarray) -> float:
    return float(np.mean(x)) if len(x) else float("nan")


def cambio_por_ventana(base: Dict[str, np.ndarray], nuevas: Sequence[Dict[str, np.ndarray]], planta, ley_base: Ley, ley_nueva: Ley, largo_m: float = 200.0, paso_m: float = 150.0) -> Dict[str, Any]:
    """Compara el cambio **real** del |CTE| máx. por ventana entre una sesión (`base`) y otra (`nuevas`, media de sus vueltas) con el cambio **simulado** de `ley_base` a `ley_nueva` desde el estado de `base`.

    Es la prueba de que el modelo sirve para elegir ganancias: correlación entre ambos cambios, ventanas que coinciden en signo (|cambio real| > 0,15 m) y medias por velocidad."""
    def pico(v, s0, s1):
        m = (v["lap_distance"] >= s0) & (v["lap_distance"] <= s1)
        return float(np.abs(v["signed_cte"][m]).max())

    filas = []
    for s0 in np.arange(300.0, base["lap_distance"].max() - largo_m, paso_m):
        s1 = s0 + largo_m
        m = (base["lap_distance"] >= s0) & (base["lap_distance"] <= s1)
        if m.sum() < 100:
            continue
        real = np.mean([pico(v, s0, s1) for v in nuevas]) - pico(base, s0, s1)
        sim = np.abs(simular(base, s0, s1, planta, ley_nueva)[1]).max() - np.abs(simular(base, s0, s1, planta, ley_base)[1]).max()
        filas.append((float(s0), float(base["v"][m].mean() * 3.6), float(real), float(sim)))
    f = np.array(filas)
    real, sim, vel = f[:, 2], f[:, 3], f[:, 1]
    sig = np.abs(real) > 0.15
    return {"filas": filas, "corr": float(np.corrcoef(real, sim)[0, 1]), "signo": int(np.sum(sig & (np.sign(real) == np.sign(sim)))), "con_cambio": int(sig.sum()),
            "alta": (_media(real[vel > 108]), _media(sim[vel > 108])), "baja": (_media(real[vel < 100]), _media(sim[vel < 100]))}


TRAMOS_SUGO = {"S 2200-2650": (2200.0, 2650.0), "curvas 2560-2900": (2560.0, 2900.0)}
VARIANTES = [("base", {}), ("ff 0,0025", {"ff_gain": 0.0025}), ("ff 0,002", {"ff_gain": 0.002}), ("ff 0,0015", {"ff_gain": 0.0015}), ("k_heading 1,0", {"k_heading": 1.0}),
             ("ff 0,002 + k_heading 1,0", {"ff_gain": 0.002, "k_heading": 1.0})]


def _par(txt: str) -> Tuple[Path, Path]:
    log, ref = txt.split("|", 1)
    return Path(log), Path(ref)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--ajuste", nargs="+", required=True, help="LOG|REF (separados por |) con los que se ajusta la planta")
    ap.add_argument("--prueba", nargs="+", required=True, help="LOG|REF con los que se comparan las variantes")
    args = ap.parse_args(argv)
    ajuste = [cargar_vuelta(*_par(x)) for x in args.ajuste]
    prueba = [cargar_vuelta(*_par(x)) for x in args.prueba]
    planta, e = ajustar_guinada(ajuste)
    print(f"planta: guiñada = v·volante / ({planta.a:.2f} + {planta.b:.4f}·v²), τ = {planta.tau:.2f} s; error de la guiñada {e:.3f} rad/s")
    for v in (20.0, 25.0, 30.0, 33.0):
        print(f"  anticipación / necesario a {v * 3.6:.0f} km/h: {ff_sobre_necesario(planta, v, Ley()):.2f}")
    cerrada = calibrar_cerrado(ajuste, planta)
    print(f"calibración en lazo cerrado: ganancia ×{cerrada.gain_scale}, τ ×{cerrada.tau_scale}; error de CTE (prueba) {error_cte(prueba[0], cerrada)[0]:.2f} m, picos {error_cte(prueba[0], cerrada)[1]:.2f} del real")
    plantas = {"ajustada": cerrada, "ganancia baja": replace(cerrada, gain_scale=0.95, tau_scale=1.0), "ganancia alta": replace(cerrada, gain_scale=1.25, tau_scale=0.75)}
    for nombre, p in plantas.items():
        print(f"\n== coche {nombre} (|CTE| máx. simulado, m) ==")
        print(f"{'variante':26s}" + "".join(f"{k:>18s}" for k in [*TRAMOS_SUGO, "pico medio", "rms medio", "ventanas > 1,8 m"]))
        for vn, kw in VARIANTES:
            r = picos(prueba, p, replace(Ley(), **kw), TRAMOS_SUGO)
            print(f"{vn:26s}" + "".join(f"{r[k]:18.2f}" for k in [*TRAMOS_SUGO, "pico medio", "rms medio", "ventanas > 1,8 m"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
