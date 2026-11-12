"""Bloque de reglaje, amortiguadores (sin juego): histograma de `susp_vel` por rueda, por zona y por curva.

Convenio (comprobado con V118): `susp_travel` crece al extenderse (al frenar baja delante y sube detrás) y
`susp_vel` ≈ −d(susp_travel)/dt, así que **`susp_vel` > 0 es compresión y < 0 es extensión**. Ruedas en el orden
del juego: delantera izquierda, delantera derecha, trasera izquierda, trasera derecha (se comprueba con la carga en
las curvas a izquierdas: las ruedas derechas, las de fuera, van más comprimidas).

Rodilla lenta → rápida de cada amortiguador = transición (N) / coeficiente lento (N·s/m), con el reglaje vigente
(`PCARS2-AI/docs/CONFIGURACION_JUEGO.md`). Por debajo de la rodilla trabaja el ajuste lento (balanceo, cabeceo,
transferencia de carga: lo que se siente en el paso por curva); por encima, el rápido (pianos y baches).

Uso: `python amortiguadores.py <log.jsonl> [--vueltas 4-6] [--zona 865-885]`
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[2]
CURVAS = REPO / "circuito_virtual" / "pistas" / "sugo_gp" / "curvas.json"
WHEELS = ("DI", "DD", "TI", "TD")
KERB_TERRAIN = (10, 25, 47, 48, 49)  # pianos, piano de salida, franja ilegal y pintura (48 sin nombre en el enum: entre 47 y 49)

# reglaje vigente (CONFIGURACION_JUEGO.md, 2026-11-11): (coef. lento compresión, transición compresión,
# coef. lento extensión, transición extensión) por eje
DAMPERS = {"del": (3600.0, 250.0, 3700.0, 210.0), "tras": (2300.0, 100.0, 3700.0, 200.0)}


def knees() -> np.ndarray:
    """Velocidad (m/s) de la rodilla lenta → rápida por rueda: columnas (compresión, extensión)."""
    out = []
    for w in range(4):
        cb, tb, cr, trn = DAMPERS["del" if w < 2 else "tras"]
        out.append((tb / cb, trn / cr))
    return np.array(out)


def parse_range(text: str) -> Tuple[float, float]:
    a, b = text.split("-")
    return float(a), float(b)


def load(path: Path, laps: Tuple[int, int]) -> Dict[str, np.ndarray]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("type") != "tick" or not (laps[0] <= r.get("lap", 0) <= laps[1]):
                continue
            v = r.get("vehicle") or {}
            if "susp_vel" not in v:
                continue
            rows.append(r)
    if not rows:
        raise SystemExit("sin ticks con susp_vel en esas vueltas")
    veh = [r["vehicle"] for r in rows]
    return {
        "lap": np.array([r["lap"] for r in rows]),
        "s": np.array([r["lap_distance"] for r in rows], float),
        "kmh": np.array([r["speed_kmh"] for r in rows], float),
        "sv": np.array([v["susp_vel"] for v in veh], float),
        "travel": np.array([v["susp_travel"] for v in veh], float),
        "terrain": np.array([v["terrain"] for v in veh], int),
        "lat": np.array([v.get("lat_accel", 0.0) for v in veh], float),
        "long": np.array([v.get("long_accel", 0.0) for v in veh], float),
        "brake": np.array([r.get("brake", 0.0) for r in rows], float),
        "throttle": np.array([r.get("throttle", 0.0) for r in rows], float),
    }


def curves() -> List[Dict[str, Any]]:
    return json.loads(CURVAS.read_text(encoding="utf-8"))["curvas"]


def curve_mask(s: np.ndarray, cs: Sequence[Dict[str, Any]]) -> np.ndarray:
    m = np.zeros(len(s), bool)
    for c in cs:
        m |= (s >= c["s_ini"]) & (s <= c["s_fin"])
    return m


def stats(sv: np.ndarray, knee: Tuple[float, float]) -> Dict[str, float]:
    comp, reb = sv[sv > 0], -sv[sv < 0]
    n = max(len(sv), 1)
    return {
        "n": len(sv),
        "comp_p50": float(np.percentile(comp, 50)) if len(comp) else 0.0,
        "comp_p95": float(np.percentile(comp, 95)) if len(comp) else 0.0,
        "comp_p99": float(np.percentile(comp, 99)) if len(comp) else 0.0,
        "comp_max": float(comp.max()) if len(comp) else 0.0,
        "reb_p95": float(np.percentile(reb, 95)) if len(reb) else 0.0,
        "reb_p99": float(np.percentile(reb, 99)) if len(reb) else 0.0,
        "reb_max": float(reb.max()) if len(reb) else 0.0,
        "rapida_comp_pct": 100.0 * float((sv > knee[0]).sum()) / n,
        "rapida_ext_pct": 100.0 * float((sv < -knee[1]).sum()) / n,
    }


def fmt_stats(name: str, st: Dict[str, float]) -> str:
    return (f"{name:<4} n={st['n']:>6}  comp p50 {st['comp_p50']:.3f} p95 {st['comp_p95']:.3f} p99 {st['comp_p99']:.3f} "
            f"máx {st['comp_max']:.3f} | ext p95 {st['reb_p95']:.3f} p99 {st['reb_p99']:.3f} máx {st['reb_max']:.3f} | "
            f"rápida: comp {st['rapida_comp_pct']:4.1f} %  ext {st['rapida_ext_pct']:4.1f} %")


HIST_EDGES = np.array([-1.0, -0.3, -0.15, -0.1, -0.05, -0.025, 0.0, 0.025, 0.05, 0.1, 0.15, 0.3, 1.0])


def histogram(sv: np.ndarray) -> np.ndarray:
    clipped = np.clip(sv, HIST_EDGES[0] + 1e-9, HIST_EDGES[-1] - 1e-9)
    h, _ = np.histogram(clipped, HIST_EDGES)
    return 100.0 * h / max(len(sv), 1)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Histograma de susp_vel por rueda, por zona y por curva (bloque de amortiguadores).")
    ap.add_argument("log", type=Path)
    ap.add_argument("--vueltas", default="4-6")
    ap.add_argument("--zona", default="865-885", help="tramo de lap_distance (m) para el detalle por vuelta")
    ap.add_argument("--json", type=Path, help="guardar el resumen en este fichero")
    a = ap.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")  # consola de Windows en cp1252
    lo, hi = (int(x) for x in a.vueltas.split("-"))
    d = load(a.log, (lo, hi))
    k = knees()
    cs = curves()
    sv, terr = d["sv"], d["terrain"]
    on_kerb = np.isin(terr, KERB_TERRAIN)
    in_curve = curve_mask(d["s"], cs)
    out: Dict[str, object] = {"log": a.log.name, "vueltas": a.vueltas, "rodillas_m_s": {w: {"comp": round(k[i, 0], 4), "ext": round(k[i, 1], 4)} for i, w in enumerate(WHEELS)}}

    print(f"{a.log.name}  vueltas {a.vueltas}  ticks {len(sv)}")
    print("rodilla lenta→rápida (m/s): " + "  ".join(f"{w} comp {k[i, 0]:.3f} ext {k[i, 1]:.3f}" for i, w in enumerate(WHEELS)))

    # orden de ruedas: en curvas a izquierdas las de la derecha (fuera) se comprimen más
    left = curve_mask(d["s"], [c for c in cs if c["sentido"] == "izq"])
    right = curve_mask(d["s"], [c for c in cs if c["sentido"] == "dcha"])
    tl, trr = d["travel"][left].mean(0), d["travel"][right].mean(0)
    print(f"comprobación del orden: recorrido medio en curvas izq {np.round(tl, 4)}  dcha {np.round(trr, 4)} "
          f"(en izq deben ir más comprimidas —recorrido menor— DD y TD)")

    print("\n== Toda la vuelta ==")
    out["total"] = {}
    for i, w in enumerate(WHEELS):
        st = stats(sv[:, i], tuple(k[i]))
        out["total"][w] = st
        print(fmt_stats(w, st))

    print("\n== Histograma (% de ticks; + = compresión) ==")
    labels = [f"{HIST_EDGES[j]:+.3f}…{HIST_EDGES[j + 1]:+.3f}" for j in range(len(HIST_EDGES) - 1)]
    print("      " + " ".join(f"{lab[:6]:>6}" for lab in labels))
    for i, w in enumerate(WHEELS):
        print(f"{w:<5} " + " ".join(f"{x:6.1f}" for x in histogram(sv[:, i])))

    print("\n== Por zona (rueda en piano / curva sin piano / recta sin piano) ==")
    out["zonas"] = {}
    for i, w in enumerate(WHEELS):
        kerb_i = on_kerb[:, i]
        for zname, m in (("piano", kerb_i), ("curva", in_curve & ~kerb_i), ("recta", ~in_curve & ~kerb_i)):
            st = stats(sv[m, i], tuple(k[i]))
            out["zonas"].setdefault(zname, {})[w] = st
            print(fmt_stats(f"{w}", st) + f"  [{zname}]")
        print()

    print("== Por curva (delanteras: p99 compresión, máx, % rápida comp.; % ticks con la rueda en piano) ==")
    out["curvas"] = {}
    for c in cs:
        m = (d["s"] >= c["s_ini"] - 20) & (d["s"] <= c["s_fin"] + 20)
        if not m.any():
            continue
        row = {}
        parts = []
        for i, w in enumerate(WHEELS):
            st = stats(sv[m, i], tuple(k[i]))
            kp = 100.0 * float(on_kerb[m, i].mean())
            row[w] = {**st, "piano_pct": kp}
            if i < 2:
                parts.append(f"{w} p99 {st['comp_p99']:.3f} máx {st['comp_max']:.3f} ráp {st['rapida_comp_pct']:4.1f} % piano {kp:4.1f} %")
        rear_fast = max(row["TI"]["rapida_comp_pct"], row["TD"]["rapida_comp_pct"])
        out["curvas"][f"C{c['id']}"] = row
        print(f"C{c['id']:<2} {c['sentido']:<4} {c['s_ini']:.0f}-{c['s_fin']:.0f}  " + " | ".join(parts) + f" | tras ráp. máx {rear_fast:4.1f} %")

    z0, z1 = parse_range(a.zona)
    print(f"\n== Tramo {a.zona} m por vuelta (máximos; km/h y lateral medias) ==")
    out["tramo"] = {"zona": a.zona, "vueltas": {}}
    for lap in range(lo, hi + 1):
        m = (d["lap"] == lap) & (d["s"] >= z0) & (d["s"] <= z1)
        if not m.any():
            continue
        cmax = sv[m].max(0)
        emax = -sv[m].min(0)
        kp = on_kerb[m].mean(0) * 100
        row = {"kmh": float(d["kmh"][m].mean()), "lat": float(d["lat"][m].mean()),
               "comp_max": cmax.round(3).tolist(), "ext_max": emax.round(3).tolist(), "piano_pct": kp.round(1).tolist()}
        out["tramo"]["vueltas"][lap] = row
        print(f"v{lap}: {row['kmh']:.0f} km/h lat {row['lat']:+.1f}  comp máx {np.round(cmax, 3)}  ext máx {np.round(emax, 3)}  piano % {np.round(kp, 0)}")

    if a.json:
        a.json.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nguardado {a.json}")


if __name__ == "__main__":
    main()
