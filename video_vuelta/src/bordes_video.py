"""Línea blanca de los bordes a partir de un vídeo y su log (D5 de docs/DECISIONES.md).

Uso:
    python video_vuelta/src/bordes_video.py <manifiesto.json> [--cada 6] [--salida linea_blanca.json]

Por cada fotograma muestreado: busca la línea blanca de cada lado (`lineas.py`), la pasa al suelo con la cámara
(`camara.py`), coloca el punto en el mundo con la posición y el rumbo del log en ese instante (`t_log = t_vídeo +
desfase`, de `sincronia.py`) y lo proyecta sobre el mapa de la pista, `(s, n)`. Por cada metro de vuelta guarda la
mediana de `n` de cada lado y cuántas medidas la apoyan. Con `observaciones_logs.json` (las cotas por ruedas que
dan los logs antiguos) comprueba cuántos metros caen dentro de su horquilla.

Solo lee: ni el juego ni los archivos de la pista se tocan.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "PCARS2-AI" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from circuito_virtual.src.mapa import Mapa  # noqa: E402
from video_vuelta.src.camara import Camara, camara_de_manifiesto  # noqa: E402
from video_vuelta.src.lineas import Linea, lineas_del_fotograma  # noqa: E402

Z_MIN, Z_MAX, Z_PASO = 3.6, 9.6, 0.5  # tramo de cada línea (delante de la cámara) que se proyecta: el más preciso
VELOCIDAD_MIN_KMH = 5.0
# De la línea blanca al límite de carrera del juego, medido con las cotas por ruedas de los logs antiguos (2026-11-08, 516 m a la izquierda y
# 228 a la derecha con horquilla estrecha): error de la línea frente al punto medio de la horquilla = +0,24 m (izq) y −0,12 m (dcha), es decir
# un desplazamiento común de la cámara de +0,06 m y un límite 0,18 m más allá de la línea a cada lado (incluye el error de la semivía supuesta).
SESGO_CAMARA_M = 0.06
LIMITE_FUERA_M = 0.18
ANCHO_PLAUSIBLE_M = (7.0, 14.5)  # entre líneas; fuera de esto una de las dos es otra cosa (pit lane, muro...)
MAPA = REPO / "circuito_virtual" / "pistas" / "sugo_gp" / "mapa.json"
OBSERVACIONES = REPO / "circuito_virtual" / "pistas" / "sugo_gp" / "observaciones_logs.json"


@dataclass
class LogPose:
    t: np.ndarray
    vuelta: np.ndarray
    s: np.ndarray
    x: np.ndarray
    z: np.ndarray
    rumbo: np.ndarray  # rad, atan2(dx, dz) del avance del coche (orientation[1] del log menos π)
    v_kmh: np.ndarray

    def en(self, t_log: float) -> tuple[float, float, float, float, float, int]:
        """(x, z, rumbo, s, v_kmh, vuelta) interpolados en `t_log`."""
        i = int(np.clip(np.searchsorted(self.t, t_log), 1, len(self.t) - 1))
        a = float(np.clip((t_log - self.t[i - 1]) / max(self.t[i] - self.t[i - 1], 1e-9), 0.0, 1.0))
        lerp = lambda arr: float(arr[i - 1] + a * (arr[i] - arr[i - 1]))  # noqa: E731
        return lerp(self.x), lerp(self.z), lerp(self.rumbo), lerp(self.s), lerp(self.v_kmh), int(self.vuelta[i])


def leer_pose(ruta: str | Path) -> LogPose:
    t, vu, s, x, z, yaw, v = [], [], [], [], [], [], []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            if '"type": "tick"' not in linea[:20]:
                continue
            r = json.loads(linea)
            veh = r.get("vehicle") or {}
            if not veh.get("position") or not veh.get("orientation"):
                continue
            t.append(r["t_s"]); vu.append(r["lap"]); s.append(r["lap_distance"]); v.append(r["speed_kmh"])
            x.append(veh["position"][0]); z.append(veh["position"][2]); yaw.append(veh["orientation"][1])
    if not t:
        raise ValueError(f"{ruta}: sin ticks con posición y orientación")
    # orientation[1] del log = rumbo del avance (atan2(dx, dz)) + π: medido el 2026-11-08 con el movimiento real (error medio 0,005 rad, desviación 0,03 rad)
    return LogPose(np.array(t), np.array(vu), np.array(s), np.array(x), np.array(z), np.unwrap(np.array(yaw)) - np.pi, np.array(v))


def punto_al_mundo(x: float, z: float, rumbo: float, Z: np.ndarray, X: np.ndarray, atras_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Puntos (Z adelante, X derecha) respecto a la cámara -> mundo. La cámara va `atras_m` por detrás de la posición del log."""
    fx, fz = np.sin(rumbo), np.cos(rumbo)
    dx, dz = np.cos(rumbo), -np.sin(rumbo)  # derecha del coche, igual que el mapa: (tz, -tx)
    adelante = np.asarray(Z, dtype=float) - atras_m
    X = np.asarray(X, dtype=float)
    return x + adelante * fx + X * dx, z + adelante * fz + X * dz


def muestras_de_linea(linea: Linea, pose: tuple, cam: Camara, mapa: Mapa, z_max: float = Z_MAX) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(s, n) de los puntos de una línea entre Z_MIN y `z_max` (acotado a lo que se vio realmente)."""
    x, z, rumbo, s_coche, _, _ = pose
    z0, z1 = max(Z_MIN, float(linea.Z.min())), min(z_max, float(linea.Z.max()))
    if z1 <= z0:
        return np.empty(0), np.empty(0), np.empty(0)
    Z = np.arange(z0, z1 + 1e-9, Z_PASO)
    wx, wz = punto_al_mundo(x, z, rumbo, Z, linea.x_en(Z), cam.atras_m)
    s, n = mapa.xz_a_sn(wx, wz, s_hint=np.full(len(Z), s_coche))
    return s, n, Z


def _mediana_ponderada(valores: np.ndarray, pesos: np.ndarray) -> float:
    o = np.argsort(valores)
    c = np.cumsum(pesos[o])
    return float(valores[o][int(np.searchsorted(c, 0.5 * c[-1]))])


def agregar(muestras: list[tuple[float, float, float]], mapa: Mapa) -> dict:
    """Mediana de n (ponderada por 1/Z², lo cercano pesa más) y número de medidas por metro de vuelta (casillas de `Observaciones`)."""
    n_pts = mapa.n_puntos
    med = np.full(n_pts, np.nan)
    cuenta = np.zeros(n_pts, dtype=int)
    if muestras:
        s, n, Zm = np.array(muestras).T
        peso = 1.0 / np.maximum(Zm, 1.0) ** 2
        b = np.clip((np.mod(s, mapa.longitud_m) / mapa.longitud_m * n_pts).astype(int), 0, n_pts - 1)
        orden = np.argsort(b, kind="stable")
        b, n, peso = b[orden], n[orden], peso[orden]
        inicios = np.r_[0, np.where(np.diff(b) != 0)[0] + 1]
        for ini, fin in zip(inicios, np.r_[inicios[1:], len(b)]):
            med[b[ini]] = _mediana_ponderada(n[ini:fin], peso[ini:fin])
            cuenta[b[ini]] = fin - ini
    return {"n": med, "cuenta": cuenta}


def _rellenar(a: np.ndarray, hueco_max: int) -> np.ndarray:
    """Interpola linealmente (con la vuelta cerrada) los huecos de hasta `hueco_max` metros que tienen dato a los dos lados."""
    a = a.copy()
    n = len(a)
    ok = np.isfinite(a)
    if ok.sum() < 2:
        return a
    idx = np.where(ok)[0]
    for k in range(len(idx)):
        i0, i1 = idx[k], idx[(k + 1) % len(idx)]
        salto = (i1 - i0) % n
        if 1 < salto <= hueco_max + 1:
            pos = (i0 + np.arange(1, salto)) % n
            a[pos] = a[i0] + (a[i1] - a[i0]) * np.arange(1, salto) / salto
    return a


def _mediana_movil(a: np.ndarray, ventana: int) -> np.ndarray:
    """Mediana móvil circular que ignora los huecos (un metro sin dato sigue sin dato)."""
    n, m = len(a), ventana // 2
    out = np.full(n, np.nan)
    ext = np.concatenate([a[-m:], a, a[:m]]) if m else a
    for i in range(n):
        if np.isfinite(a[i]):
            w = ext[i:i + 2 * m + 1]
            out[i] = np.nanmedian(w)
    return out


def limites(res: dict, hueco_max: int = 15, ventana: int = 5, ancho: tuple[float, float] = ANCHO_PLAUSIBLE_M) -> dict:
    """Del `n` de la línea blanca al `n` del límite de carrera, por metro: descarta los metros con un ancho imposible, quita picos con una
    mediana móvil, rellena huecos cortos y aplica el sesgo de la cámara y el límite 0,18 m más allá de la línea."""
    izq, dcha = res["izq"]["n"].copy(), res["dcha"]["n"].copy()
    w = dcha - izq
    mal = np.isfinite(w) & ((w < ancho[0]) | (w > ancho[1]))
    izq[mal], dcha[mal] = np.nan, np.nan
    izq = _rellenar(_mediana_movil(izq, ventana), hueco_max)
    dcha = _rellenar(_mediana_movil(dcha, ventana), hueco_max)
    return {"izq": izq - SESGO_CAMARA_M - LIMITE_FUERA_M, "dcha": dcha - SESGO_CAMARA_M + LIMITE_FUERA_M, "descartados": int(mal.sum())}


def procesar(manifiesto: Path, cada: int, mapa: Mapa, vueltas: list[int] | None = None, cam: Camara | None = None,
             fila_min: int = 500, z_max: float = Z_MAX, v_min_kmh: float = VELOCIDAD_MIN_KMH, v_max_kmh: float = 1e9) -> dict:
    man = json.loads(Path(manifiesto).read_text(encoding="utf-8"))
    cam = cam or camara_de_manifiesto(man)
    pose = leer_pose(REPO / man["log"])
    desfase = float(man["sincronia"]["desfase_s"])
    cap = cv2.VideoCapture(man["video"], cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise ValueError(f"no se abre {man['video']}")
    acum: dict[str, list[tuple[float, float, float]]] = {"izq": [], "dcha": []}
    vistos = {"izq": 0, "dcha": 0, "fotogramas": 0}
    k = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        k += 1
        if k % cada:
            continue
        ok, fot = cap.retrieve()
        if not ok:
            break
        t_log = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0 + desfase
        if t_log < pose.t[0] or t_log > pose.t[-1]:
            continue
        p = pose.en(t_log)
        if not (v_min_kmh <= p[4] <= v_max_kmh) or (vueltas and p[5] not in vueltas):
            continue
        vistos["fotogramas"] += 1
        for lado, linea in lineas_del_fotograma(fot, cam, filas=tuple(range(fila_min, 830, 4))).items():
            if linea is None:
                continue
            s, n, Zl = muestras_de_linea(linea, p, cam, mapa, z_max)
            if len(s):
                vistos[lado] += 1
                acum[lado].extend(zip(s.tolist(), n.tolist(), Zl.tolist()))
    cap.release()
    return {"izq": agregar(acum["izq"], mapa), "dcha": agregar(acum["dcha"], mapa), "vistos": vistos, "camara": cam}


def validar(res: dict, obs_ruta: Path, mapa: Mapa, tol_m: float = 0.15) -> dict:
    """¿Cae la línea dentro de la horquilla (fuera, dentro) de los logs antiguos? Solo donde hay línea y cota."""
    obs = json.loads(Path(obs_ruta).read_text(encoding="utf-8"))
    nan = lambda a: np.array([np.nan if v is None else v for v in a], dtype=float)  # noqa: E731
    out = {}
    for lado, signo in (("izq", -1.0), ("dcha", 1.0)):
        n = res[lado]["n"]
        dentro, fuera = nan(obs[f"{lado}_dentro"]), nan(obs[f"{lado}_fuera"])
        # izquierda: fuera <= borde <= dentro; derecha: dentro <= borde <= fuera
        lo, hi = (fuera, dentro) if signo < 0 else (dentro, fuera)
        con_linea = np.isfinite(n)
        horquilla = con_linea & np.isfinite(lo) & np.isfinite(hi)
        dentro_h = horquilla & (n >= lo - tol_m) & (n <= hi + tol_m)
        solo_dentro = con_linea & np.isfinite(dentro) & ~np.isfinite(fuera)
        fuera_cota = solo_dentro & ((n <= dentro + tol_m) if signo < 0 else (n >= dentro - tol_m))
        out[lado] = {
            "metros_con_linea": int(con_linea.sum()),
            "con_horquilla": int(horquilla.sum()), "dentro_de_la_horquilla": int(dentro_h.sum()),
            "solo_cota_asfalto": int(solo_dentro.sum()), "no_contradice_la_cota": int(fuera_cota.sum()),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("manifiesto", type=Path)
    ap.add_argument("--cada", type=int, default=6, help="un fotograma de cada N (6 = 10 por segundo)")
    ap.add_argument("--vueltas", type=int, nargs="*", help="solo estas vueltas del log")
    ap.add_argument("--fila-min", type=int, default=500, help="fila más alta (lejana) que se mira; más baja = más lejos")
    ap.add_argument("--z-max", type=float, default=Z_MAX, help="metros por delante de la cámara hasta los que se usa la línea")
    ap.add_argument("--mapa", type=Path, default=MAPA)
    ap.add_argument("--salida", type=Path, help="JSON con la mediana de n por metro y lado (por defecto, junto al manifiesto)")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    mapa = Mapa.cargar(a.mapa)
    res = procesar(a.manifiesto, a.cada, mapa, a.vueltas, fila_min=a.fila_min, z_max=a.z_max)
    print("fotogramas usados:", res["vistos"])
    print("validación frente a las cotas de los logs:", json.dumps(validar(res, OBSERVACIONES, mapa), ensure_ascii=False, indent=1))
    lim = limites(res)
    print(f"límite de carrera: izquierda {100 * np.isfinite(lim['izq']).mean():.0f} % de la vuelta, derecha {100 * np.isfinite(lim['dcha']).mean():.0f} %, "
          f"metros descartados por ancho imposible: {lim['descartados']}")
    ancho = lim["dcha"] - lim["izq"]
    if np.isfinite(ancho).any():
        print(f"ancho del límite de carrera: mediana {np.nanmedian(ancho):.2f} m, p10 {np.nanpercentile(ancho, 10):.2f}, p90 {np.nanpercentile(ancho, 90):.2f}")
    mapa_bordes = Mapa(mapa.nombre, mapa.longitud_m, mapa.s.copy(), mapa.x.copy(), mapa.y.copy(), mapa.z.copy(), lim["izq"], lim["dcha"],
                       mapa.sup_izq.copy(), mapa.sup_dcha.copy(), dict(mapa.meta))
    mapa_bordes.meta["bordes"] = f"video {Path(a.manifiesto).parent.name}: línea blanca + {SESGO_CAMARA_M:g} (cámara) ∓ {LIMITE_FUERA_M:g} m (límite de carrera)"
    mapa_bordes.guardar(Path(a.manifiesto).with_name("mapa_bordes_video.json"))
    print("guardado:", Path(a.manifiesto).with_name("mapa_bordes_video.json"))
    salida = a.salida or Path(a.manifiesto).with_name("linea_blanca.json")
    lista = lambda arr: [None if not np.isfinite(v) else round(float(v), 3) for v in arr]  # noqa: E731
    datos = {"n_puntos": mapa.n_puntos, "longitud_m": mapa.longitud_m, "manifiesto": Path(a.manifiesto).name, "camara": res["camara"].__dict__,
             "izq": lista(res["izq"]["n"]), "dcha": lista(res["dcha"]["n"]),
             "izq_medidas": res["izq"]["cuenta"].tolist(), "dcha_medidas": res["dcha"]["cuenta"].tolist()}
    salida.write_text(json.dumps(datos, separators=(",", ":")), encoding="utf-8")
    print("guardado:", salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
