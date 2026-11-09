"""Mapa de bordes corregido: el límite de carrera del vídeo ajustado con lo que dicen las ruedas en las vueltas manuales (D11 de docs/DECISIONES.md).

Uso:
    python video_vuelta/src/mapa_corregido.py <log izquierdo> <log derecho> [más logs] [--video mapa_bordes_video.json] [--salida mapa_bordes_corregido.json]

Por cada metro y lado hay tres fuentes:
  * el límite del vídeo (línea blanca + 0,06 m de cámara ∓ 0,18 m), que falla entre 0,6 y 1,8 m donde la cámara mide mal (curvas, pasillos de
    asfalto fuera de la línea) y que no ve los pianos;
  * una cota inferior de las ruedas (`dentro`): la rueda más exterior que seguía en superficie legal;
  * una cota superior (`fuera`): la rueda más interior que ya estaba fuera.
Superficie legal = terrenos de carrera del juego + 48 (piano plano pintado, D11). En los pianos de dos partes (48 plano por dentro y 10 rugoso por fuera,
C4, C9, C10, C12, C13) solo vale la parte plana; si el log no distingue las dos partes, el piano vale entero. El asfalto que se vuelve a pisar detrás de
una salida (parche detrás del piano, entrada a boxes) no cuenta: solo valen las ruedas legales hasta la primera superficie ilegal.

Las excepciones propias de cada pista (tramos donde el 48 no es piano, tramos donde manda la línea blanca) viven en `circuito_virtual/pistas/<pista>/reglas_limite.json`
(`--reglas`); sin ese archivo no hay excepciones.

Combinación por metro: con las dos cotas a menos de 0,6 m, su punto medio; si no, el límite del vídeo recortado a las cotas que haya. La corrección
(`límite − vídeo`) se propaga a los metros vecinos sin cota (interpolada entre dos cotas o mantenida y atenuada junto a una), y se guarda la
incertidumbre y la fuente de cada metro. Solo lee los logs y el mapa de vídeo: no toca la pista ni el juego.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "PCARS2-AI" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from circuito_virtual.src.bordes_logs import LEFT_WHEELS, RIGHT_WHEELS, SEMIVIA_M  # noqa: E402
from circuito_virtual.src.mapa import Mapa  # noqa: E402
from pcars2_surface import RACING_TERRAIN_IDS  # noqa: E402
from video_vuelta.src.verificar_limite import BORDES, MAPA, MIN_KMH, leer  # noqa: E402

PIANO_RUGOSO = 10  # TERRAIN_RUMBLE_STRIPS
PIANO_PLANO = 48  # piano plano pintado: legal (D11); el juego no lo da como superficie de carrera
LEGAL = frozenset(RACING_TERRAIN_IDS) | {PIANO_PLANO}
VENTANA_PIANO_M = 10  # la zona de dos partes se extiende esto a cada lado de donde se ven las dos
HOLGURA_M = 0.30  # el rugoso cuenta como banda exterior si está a más de (plano − esto)
MIN_AFUERA_M = 0.3  # una rueda ilegal con menos de esto «hacia fuera» está al otro lado de la pista (el coche en la hierba contraria), no marca este borde
TOLERANCIA_M = 0.15  # una rueda legal más allá de la primera ilegal no cuenta, salvo por el ruido de la posición
MAX_HORQUILLA_M = 0.6
MIN_CAMBIO_M = 0.10  # una cota que mueve el límite del vídeo menos que esto es ruido de la posición, no corrección
ALCANCE_M, PLENO_M, MAX_HUECO_M = 25, 8, 50  # propagación de la corrección
SIGMA_VIDEO_M, SIGMA_COTA_M, SIGMA_PROPAGADO_M = 0.6, 0.4, 0.6
FUENTE_VIDEO, FUENTE_DENTRO, FUENTE_FUERA, FUENTE_HORQUILLA, FUENTE_PROPAGADO = 0, 1, 2, 3, 4
LADOS = {"izq": (LEFT_WHEELS, -1.0), "dcha": (RIGHT_WHEELS, 1.0)}


def _ventana(a: np.ndarray, m: int, f) -> np.ndarray:
    """f.reduce sobre una ventana circular de ±m metros (f = np.fmax o np.fmin)."""
    out = a.copy()
    for d in range(1, m + 1):
        out = f(out, np.roll(a, d))
        out = f(out, np.roll(a, -d))
    return out


def cotas_de_lado(bins: np.ndarray, afuera: np.ndarray, terreno: np.ndarray, n_bins: int, longitud_m: float, lado: str, sin_48=(), linea_manda=()) -> tuple[np.ndarray, np.ndarray]:
    """Cotas por metro de un lado en coordenadas «hacia fuera» (m desde el eje, positivo hacia el borde de ese lado).

    `bins` (N,) metro de cada tick, `afuera` (N, 2) posición hacia fuera de las dos ruedas del lado, `terreno` (N, 2) su terreno.
    Devuelve `(dentro, fuera)`: NaN donde no hay dato."""
    bins2 = np.repeat(bins[:, None], 2, axis=1)
    metro = bins2 * longitud_m / n_bins
    plano = terreno == PIANO_PLANO
    for a, b in sin_48:  # 48 sin valor de piano en estas zonas
        plano &= ~((metro >= a) & (metro <= b))
    legal = np.isin(terreno, list(LEGAL)) & ~(np.isin(terreno, [PIANO_PLANO]) & ~plano)
    rugoso = terreno == PIANO_RUGOSO
    p48 = np.full(n_bins, np.nan)
    p10 = np.full(n_bins, np.nan)
    np.fmax.at(p48, bins2[plano], afuera[plano])
    np.fmin.at(p10, bins2[rugoso], afuera[rugoso])
    p48w = _ventana(p48, VENTANA_PIANO_M, np.fmax)
    p10w = _ventana(p10, VENTANA_PIANO_M, np.fmin)
    dos_partes = np.isfinite(p48w) & np.isfinite(p10w) & (p10w >= p48w - HOLGURA_M)
    legal &= ~(rugoso & dos_partes[bins2])  # en piano de dos partes, el rugoso queda fuera
    fuera = np.full(n_bins, np.nan)
    ilegal = ~legal & (afuera > MIN_AFUERA_M)
    np.fmin.at(fuera, bins2[ilegal], afuera[ilegal])
    # el asfalto legal detrás de la primera superficie ilegal (parche tras el piano, entrada a boxes) no cuenta
    util = legal & (afuera <= np.where(np.isfinite(fuera[bins2]), fuera[bins2], np.inf) + TOLERANCIA_M)
    dentro = np.full(n_bins, np.nan)
    np.fmax.at(dentro, bins2[util], afuera[util])
    metros = np.arange(n_bins) * longitud_m / n_bins
    for a, b in linea_manda:  # aquí manda la línea del vídeo: se ignoran las cotas
        zona = (metros >= a) & (metros <= b)
        dentro[zona], fuera[zona] = np.nan, np.nan
    return dentro, fuera


def combinar(video: np.ndarray, dentro: np.ndarray, fuera: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Límite (hacia fuera), incertidumbre y fuente por metro."""
    lim = video.copy()
    sigma = np.where(np.isfinite(video), SIGMA_VIDEO_M, np.nan)
    fuente = np.full(len(video), FUENTE_VIDEO, dtype=int)
    d_ok, f_ok = np.isfinite(dentro), np.isfinite(fuera)
    # recorte del vídeo a las cotas: solo cuenta la que lo cambia (una cota muy por dentro o muy por fuera del vídeo no dice nada)
    d_manda = d_ok & (~np.isfinite(lim) | (lim < dentro - MIN_CAMBIO_M))
    f_manda = f_ok & (~np.isfinite(lim) | (lim > fuera + MIN_CAMBIO_M))
    lim = np.where(d_manda, dentro, lim)
    lim = np.where(f_manda, fuera, lim)
    fuente[d_manda] = FUENTE_DENTRO
    fuente[f_manda] = FUENTE_FUERA
    sigma[d_manda | f_manda] = SIGMA_COTA_M
    horq = d_ok & f_ok & (fuera - dentro <= MAX_HORQUILLA_M)
    lim[horq] = 0.5 * (dentro[horq] + fuera[horq])
    sigma[horq] = 0.5 * np.abs(fuera[horq] - dentro[horq]) + 0.10
    fuente[horq] = FUENTE_HORQUILLA
    return lim, sigma, fuente


def propagar(delta: np.ndarray, ancla: np.ndarray, alcance: int = ALCANCE_M, pleno: int = PLENO_M, max_hueco: int = MAX_HUECO_M) -> np.ndarray:
    """Corrección en los metros sin ancla a partir de los que la tienen: interpolada entre dos anclas (si están a menos de `max_hueco` entre sí), o
    mantenida `pleno` metros y atenuada hasta `alcance` junto a una sola. NaN donde no llega."""
    n = len(delta)
    out = np.full(n, np.nan)
    idx = np.where(ancla & np.isfinite(delta))[0]
    if len(idx) == 0:
        return out
    out[idx] = delta[idx]
    for i in range(n):
        if ancla[i] and np.isfinite(delta[i]):
            continue
        k = np.searchsorted(idx, i)
        b = idx[k % len(idx)]
        a = idx[(k - 1) % len(idx)]
        dl, dr = (i - a) % n, (b - i) % n
        if len(idx) > 1 and dl + dr <= max_hueco:
            out[i] = (delta[a] * dr + delta[b] * dl) / (dl + dr)
        else:
            d, v = (dl, delta[a]) if dl <= dr else (dr, delta[b])
            if d <= pleno:
                out[i] = v
            elif d <= alcance:
                out[i] = v * (alcance - d) / (alcance - pleno)
    return out


def corregir_lado(video_afuera: np.ndarray, dentro: np.ndarray, fuera: np.ndarray) -> dict:
    lim, sigma, fuente = combinar(video_afuera, dentro, fuera)
    delta = lim - video_afuera
    ancla = fuente > FUENTE_VIDEO
    prop = propagar(np.where(ancla, delta, np.nan), ancla)
    usar = ~ancla & np.isfinite(prop) & np.isfinite(video_afuera)
    lim = np.where(usar, video_afuera + prop, lim)
    sigma = np.where(usar, SIGMA_PROPAGADO_M, sigma)
    fuente = np.where(usar, FUENTE_PROPAGADO, fuente)
    return {"limite": lim, "sigma": sigma, "fuente": fuente, "delta": lim - video_afuera}


def validacion_cruzada(video_afuera: np.ndarray, dentro: np.ndarray, fuera: np.ndarray, excluir_m: int = 4) -> dict:
    """Predice la corrección de cada metro con horquilla sin usar sus vecinos (±`excluir_m`) y compara el error con no corregir (vídeo solo)."""
    lim, _, fuente = combinar(video_afuera, dentro, fuera)
    delta = lim - video_afuera
    horq = np.where((fuente == FUENTE_HORQUILLA) & np.isfinite(delta))[0]
    ancla = (fuente > FUENTE_VIDEO) & np.isfinite(delta)
    n = len(video_afuera)
    err_video, err_prop = [], []
    for i in horq[::3]:  # un metro de cada tres: los vecinos casi repiten
        a = ancla.copy()
        a[[(i + d) % n for d in range(-excluir_m, excluir_m + 1)]] = False
        pred = propagar(np.where(a, delta, np.nan), a)[i]
        err_video.append(abs(delta[i]))
        err_prop.append(abs(delta[i] - (pred if np.isfinite(pred) else 0.0)))
    ev, ep = np.array(err_video), np.array(err_prop)
    return {"n": len(ev), "error_video_mediano": float(np.median(ev)) if len(ev) else None, "error_corregido_mediano": float(np.median(ep)) if len(ep) else None,
            "mejora_en": float(np.mean(ep < ev)) if len(ev) else None, "p90_video": float(np.percentile(ev, 90)) if len(ev) else None,
            "p90_corregido": float(np.percentile(ep, 90)) if len(ep) else None}


def cargar_reglas(ruta: Path | None) -> dict[str, dict[str, list[tuple[float, float]]]]:
    """`{"sin_48": {lado: [(desde, hasta)]}, "linea_manda": {lado: [(desde, hasta)]}}`; vacío si no hay archivo."""
    vacio: dict[str, dict[str, list[tuple[float, float]]]] = {"sin_48": {"izq": [], "dcha": []}, "linea_manda": {"izq": [], "dcha": []}}
    if ruta is None or not Path(ruta).exists():
        return vacio
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    for clave in vacio:
        for lado in LADOS:
            vacio[clave][lado] = [(float(a), float(b)) for a, b in datos.get(clave, {}).get(lado, [])]
    return vacio


def cotas_de_logs(logs: list[Path], mapa: Mapa, reglas: dict | None = None) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    reglas = reglas or cargar_reglas(None)
    n = mapa.n_puntos
    acum = {lado: (np.full(n, np.nan), np.full(n, np.nan)) for lado in LADOS}
    muestras = {lado: ([], [], []) for lado in LADOS}
    for ruta in logs:
        d = leer(ruta)
        marcha = d["v"] > MIN_KMH
        s_map, n_car = mapa.xz_a_sn(d["x"][marcha], d["z"][marcha], s_hint=d["s"][marcha])
        bins = np.rint(s_map * n / mapa.longitud_m).astype(int) % n
        for lado, (ruedas, signo) in LADOS.items():
            afuera = signo * n_car[:, None] + SEMIVIA_M + np.zeros((1, 2))  # las dos ruedas del lado, misma n (se ignora el rumbo, como bordes_logs)
            terr = d["terreno"][marcha][:, list(ruedas)]
            for lista, arr in zip(muestras[lado], (bins, afuera, terr)):
                lista.append(arr)
    for lado in LADOS:
        bins, afuera, terr = (np.concatenate(m) for m in muestras[lado])
        acum[lado] = cotas_de_lado(bins, afuera, terr, n, mapa.longitud_m, lado, reglas["sin_48"][lado], reglas["linea_manda"][lado])
    return acum


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("logs", type=Path, nargs="+", help="logs de sesion_manual.py (uno por lado como mínimo)")
    ap.add_argument("--video", type=Path, default=BORDES)
    ap.add_argument("--mapa", type=Path, default=MAPA)
    ap.add_argument("--reglas", type=Path, help="reglas_limite.json de la pista (por defecto, junto al mapa de la pista si existe)")
    ap.add_argument("--salida", type=Path, help="por defecto, junto al mapa del vídeo como mapa_bordes_corregido.json")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    mapa = Mapa.cargar(a.mapa)
    video = Mapa.cargar(a.video)
    reglas = cargar_reglas(a.reglas or Path(a.mapa).with_name("reglas_limite.json"))
    cotas = cotas_de_logs(a.logs, mapa, reglas)
    res, afuera_video = {}, {"izq": -video.borde_izq, "dcha": video.borde_dcha}
    for lado, (dentro, fuera) in cotas.items():
        res[lado] = corregir_lado(afuera_video[lado], dentro, fuera)
        r, v = res[lado], afuera_video[lado]
        f = r["fuente"]
        print(f"[{lado}] metros: vídeo solo {np.sum(f == 0)}, cota inferior {np.sum(f == 1)}, cota superior {np.sum(f == 2)}, horquilla {np.sum(f == 3)}, propagado {np.sum(f == 4)}")
        d = r["delta"][np.isfinite(r["delta"])]
        print(f"[{lado}] corrección: |Δ| mediana {np.median(np.abs(d)):.2f} m, > 0,3 m en {100 * np.mean(np.abs(d) > 0.3):.0f} % de los metros; ancho a este lado: "
              f"vídeo {np.nanmedian(v):.2f} m, corregido {np.nanmedian(r['limite']):.2f} m")
        print(f"[{lado}] validación cruzada (metros con horquilla, sin sus vecinos):", json.dumps(validacion_cruzada(v, dentro, fuera), ensure_ascii=False))
    izq = -res["izq"]["limite"]
    dcha = res["dcha"]["limite"]
    out = Mapa(video.nombre, video.longitud_m, video.s.copy(), video.x.copy(), video.y.copy(), video.z.copy(), izq, dcha, video.sup_izq.copy(), video.sup_dcha.copy(), dict(video.meta))
    out.meta["bordes"] = "corregido: vídeo + cotas de las ruedas de " + ", ".join(p.name for p in a.logs) + " (D11)"
    ruta = a.salida or Path(a.video).with_name("mapa_bordes_corregido.json")
    datos = out.a_dict()
    redondea = lambda arr: [None if not np.isfinite(v) else round(float(v), 3) for v in arr]  # noqa: E731
    for lado in LADOS:
        datos[f"sigma_{lado}"] = redondea(res[lado]["sigma"])
        datos[f"fuente_{lado}"] = res[lado]["fuente"].tolist()
        datos[f"delta_{lado}"] = redondea(res[lado]["delta"])
    Path(ruta).write_text(json.dumps(datos, separators=(",", ":")), encoding="utf-8")
    print("guardado:", ruta)
    ancho = dcha - izq
    print(f"ancho del límite de carrera: mediana {np.nanmedian(ancho):.2f} m (vídeo {np.nanmedian(video.borde_dcha - video.borde_izq):.2f} m)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
