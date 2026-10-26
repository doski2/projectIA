"""Informe de la prueba C0: comprueba el log ampliado y deja gráficas para revisarlo a ojo.

Uso:
    python experimental/common/informe_c0.py <log.jsonl> [--open]
Escribe experimental/logs/informe_<log>.html y .json (resultados de las comprobaciones).
"""

from __future__ import annotations

import base64
import io
import json
import sys
import webbrowser
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "PCARS2-AI"
OUT = REPO / "experimental" / "logs"
sys.path.insert(0, str(APP / "src"))

from session_log import VEHICLE_EXTRA_KEYS as NEW_FIELDS  # noqa: E402  (una sola lista de campos)
from session_log import VEHICLE_EXTRA_X4B_KEYS as X4B_FIELDS  # noqa: E402

OK, WARN, FAIL, SKIP = "ok", "aviso", "fallo", "omitido"
Check = Tuple[str, str, str]  # (nombre, estado, detalle)


def load_log(path: Path) -> Tuple[dict, List[dict], List[dict]]:
    header: dict = {}
    ticks: List[dict] = []
    events: List[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # última línea cortada
            kind = row.get("type")
            if kind == "session" and not header:
                header = row
            elif kind == "tick":
                ticks.append(row)
            else:
                events.append(row)
    return header, ticks, events


def _col(ticks: List[dict], key: str, idx: Optional[int] = None) -> np.ndarray:
    """Columna por tick: busca `key` en el bloque `vehicle` y, si no está, en el tick."""
    out = np.full(len(ticks), np.nan)
    for i, t in enumerate(ticks):
        veh = t.get("vehicle") or {}
        v = veh[key] if key in veh else t.get(key)
        if v is None:
            continue
        try:
            out[i] = v[idx] if idx is not None else v
        except (TypeError, IndexError):
            pass
    return out


def _corr(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 30 or np.std(a[m]) == 0 or np.std(b[m]) == 0:
        return None
    return float(np.corrcoef(a[m], b[m])[0, 1])


def _smooth(x: np.ndarray, n: int = 30) -> np.ndarray:
    """Media móvil sin efecto de borde (normaliza por el peso real de la ventana; ignora NaN)."""
    k = np.ones(n)
    ok = np.isfinite(x)
    num = np.convolve(np.where(ok, x, 0.0), k, mode="same")
    den = np.convolve(ok.astype(float), k, mode="same")
    return np.where(den > 0, num / np.maximum(den, 1e-9), np.nan)


def _load_reference(header: dict):
    ref = header.get("reference")
    if not ref:
        return None
    for base in (Path.cwd(), APP):
        p = base / ref
        if p.is_file():
            from reference_recorder import ReferenceLine

            return ReferenceLine.load(str(p))
    return None


def _bytes_per_tick(path: Path, n: int) -> float:
    return path.stat().st_size / max(n, 1)


def _old_log_bytes_per_tick(exclude: Path) -> Optional[Tuple[str, float]]:
    """Bytes/tick de un log reciente sin `log_schema` (formato antiguo), para medir el crecimiento."""
    for p in sorted((APP / "logs" / "learning").glob("*.jsonl"), reverse=True):
        if p == exclude or p.stat().st_size < 1_000_000:
            continue
        with open(p, encoding="utf-8") as fh:  # solo cabecera y número de líneas, sin parsear los ticks
            try:
                head = json.loads(fh.readline())
            except json.JSONDecodeError:
                continue
            if head.get("type") != "session" or "log_schema" in head:
                continue
            lines = 1 + sum(1 for _ in fh)
        return p.name, p.stat().st_size / lines
    return None


def pauses(ticks: List[dict], min_gap_s: float = 0.2) -> List[dict]:
    """Pausas del juego: el reloj del PC avanza más de `min_gap_s` y el del juego (o el estado) no.

    Con bloque `timing` se mide con `game_time_s`; sin él, con el estado congelado (distancia y velocidad iguales).
    """
    out: List[dict] = []
    for a, b in zip(ticks, ticks[1:]):
        gap = (b.get("t_s") or 0) - (a.get("t_s") or 0)
        if gap <= min_gap_s:
            continue
        ta, tb = a.get("timing"), b.get("timing")
        if ta and tb:
            frozen = tb["game_time_s"] - ta["game_time_s"] < 0.5 * gap
            method = "reloj del juego"
        else:
            # congelado = avanzó mucho menos de lo que la velocidad implicaba (con el coche parado no se sabe)
            expected = (a.get("speed_kmh") or 0) / 3.6 * gap
            moved = abs((b.get("lap_distance") or 0) - (a.get("lap_distance") or 0))
            frozen = expected > 2.0 and moved < 0.3 * expected
            method = "estado congelado"
        out.append({"tick": a.get("tick"), "duracion_s": round(gap, 2), "lap": a.get("lap"),
                    "lap_distance": a.get("lap_distance"), "pausa_del_juego": bool(frozen), "metodo": method})
    return out


def sector_table(ticks: List[dict]) -> List[dict]:
    """Un tramo por (vuelta, sector): duración sin pausas, velocidad media y rango de lap_distance."""
    rows: List[dict] = []
    cur: Optional[dict] = None
    prev = None
    for t in ticks:
        tm = t.get("timing")
        if not tm:
            return []
        key = (t.get("lap"), tm.get("sector"))
        gap = (t.get("t_s") or 0) - (prev.get("t_s") or 0) if prev else 0.0
        if cur is None or cur["key"] != key:
            if cur:
                rows.append(cur)
            cur = {"key": key, "lap": key[0], "sector": key[1], "ticks": 0, "dur": 0.0, "vsum": 0.0,
                   "d0": t.get("lap_distance"), "d1": t.get("lap_distance"), "game_t": 0.0, "incid": 0}
        else:
            cur["dur"] += gap if gap <= 0.2 else 0.0  # las pausas no cuentan como tiempo de conducción
        cur["ticks"] += 1
        cur["vsum"] += t.get("speed_kmh") or 0.0
        cur["d1"] = t.get("lap_distance")
        cur["game_t"] = tm.get("sector_time_s", 0.0)
        cur["incid"] += int(bool(t.get("safety_override") or t.get("off_track") or t.get("stuck")))
        prev = t
    if cur:
        rows.append(cur)
    return [{"vuelta": r["lap"], "sector": r["sector"], "ticks": r["ticks"], "tiempo_conduccion_s": round(r["dur"], 1),
             "tiempo_sector_juego_s": round(r["game_t"], 1), "vel_media_kmh": round(r["vsum"] / max(r["ticks"], 1), 1),
             "lap_distance": f"{r['d0']}–{r['d1']}", "ticks_con_incidencia": r["incid"]} for r in rows if r["ticks"] > 30]


def _veh(ticks: List[dict], key: str) -> Optional[np.ndarray]:
    """Matriz (ticks con el campo × componentes) de un campo del bloque `vehicle`; None si no aparece."""
    rows = [t["vehicle"][key] for t in ticks if key in (t.get("vehicle") or {})]
    if not rows:
        return None
    return np.array([r if isinstance(r, list) else [r] for r in rows], dtype=float)


def check_x4b(ticks: List[dict], events: List[dict], add) -> None:
    """Plausibilidad de la tanda 2 y del paquete 4: valida con datos reales los offsets deducidos en el parser."""
    flags = _veh(ticks, "tyre_flags")
    if flags is not None:
        on_ground = ((flags.astype(int) >> 2) & 1).mean()
        ok = flags.max() <= 7 and on_ground > 0.9
        add("tyre_flags (bit 2 = rueda en el suelo)", OK if ok else WARN,
            f"valores {sorted({int(v) for v in np.unique(flags)})}, en el suelo {100 * on_ground:.1f} % de las lecturas")
    h = _veh(ticks, "tyre_height")
    if h is not None:
        add("tyre_height (altura de la rueda al suelo)", OK if -0.1 <= h.min() and h.max() < 0.5 else WARN,
            f"{h.min():.3f} a {h.max():.3f} m")
    bt = _veh(ticks, "brake_temp")
    if bt is not None:
        add("brake_temp (°C)", OK if -50 <= bt.min() and bt.max() <= 1500 else WARN, f"{bt.min():.0f} a {bt.max():.0f} °C")
    sv = _veh(ticks, "susp_vel")
    if sv is not None:
        add("susp_vel (m/s)", OK if np.isfinite(sv).all() and abs(sv).max() < 10 else WARN,
            f"{sv.min():.3f} a {sv.max():.3f}")
    ap = _veh(ticks, "air_pressure")
    if ap is not None:
        add("air_pressure (unidad sin confirmar)", OK if ap.min() > 0 else WARN,
            f"{ap.min():.0f} a {ap.max():.0f} (el reglaje decía 1,25 bar delante y 1,15 detrás)")
    tq = _veh(ticks, "engine_torque")
    if tq is not None:
        add("engine_torque", OK if tq.max() > 0 else WARN, f"{tq.min():.1f} a {tq.max():.1f}")
    for key in ("brake_damage", "susp_damage", "crash_state"):
        v = _veh(ticks, key)
        if v is not None:
            add(f"{key} (sin daño = 0)", OK, f"máximo {v.max():.0f}" + (" — hay daño" if v.max() > 0 else ""))
    tc = _veh(ticks, "tick_count")
    if tc is not None and len(tc) > 100:
        step = np.diff(tc[:, 0].astype(int)) % 256
        share1 = float((step == 1).mean())
        top = ", ".join(f"+{int(v)}: {100 * float((step == v).mean()):.0f} %" for v in np.unique(step)[:4])
        add("tick_count (contador cíclico de paquetes)", OK if share1 > 0.9 else WARN,
            f"avanza de uno en uno el {100 * share1:.1f} % de los ticks ({top})")

    cf = _veh(ticks, "car_flags")
    if cf is not None:
        abs_share = float(((cf.astype(int) >> 4) & 1).mean())
        add("car_flags (bit 4 = ABS activo)", OK,
            f"ABS activo en {100 * abs_share:.2f} % de los ticks (indicador directo de poco agarre al frenar)")

    cond = [e for e in events if e.get("type") == "conditions"]
    if not cond:
        add("Paquete 4 (condiciones)", SKIP if flags is None else WARN, "no llegó ningún evento `conditions` (se envía cada ~10 s)")
        return
    c0 = cond[0]
    ok = -30 <= c0["ambient_c"] <= 50 and -30 <= c0["track_c"] <= 90
    rain = max(c["rain"] for c in cond)
    detail = (f"{len(cond)} eventos · ambiente {c0['ambient_c']} °C, pista {c0['track_c']} °C, lluvia {c0['rain']}, "
              f"nieve {c0['snow']}, viento {c0['wind_speed']} · bytes 12-23: {c0['raw_hex']}")
    add("Paquete 4 (temperaturas y clima)", (OK if ok else WARN), detail)
    if rain > 0:
        add("Lluvia durante la prueba", WARN, f"densidad máxima {rain}: los datos se conservan y etiquetan (D13); no entran en el dataset seco del BC")


def run_checks(path: Path, header: dict, ticks: List[dict], ref,
               events: Optional[List[dict]] = None) -> Tuple[List[Check], Dict[str, Any]]:
    checks: List[Check] = []

    def add(name: str, status: str, detail: str = "") -> None:
        checks.append((name, status, detail))

    stats: Dict[str, Any] = {"ticks": len(ticks)}

    # 1. Cabecera
    ok = header.get("log_schema") == 2 and header.get("origin") == "experimental" and header.get("experiment")
    add("Cabecera (log_schema 2, origin experimental, experiment)", OK if ok else FAIL,
        f"log_schema={header.get('log_schema')} origin={header.get('origin')} experiment={header.get('experiment')}")
    if len(ticks) < 200:
        add("Ticks suficientes", FAIL, f"solo {len(ticks)} ticks")
        return checks, stats

    # 2. Campos nuevos: presencia y variación
    for f in NEW_FIELDS:
        arr = _veh(ticks, f)
        if arr is None:
            if f in X4B_FIELDS:
                add(f"Campo {f}", SKIP, "el log no trae la tanda 2 (X4b)")
            else:
                add(f"Campo {f}", FAIL, "no aparece en ningún tick")
            continue
        pct = 100.0 * len(arr) / len(ticks)
        if not np.isfinite(arr).all():
            add(f"Campo {f}", FAIL, "contiene NaN/inf")
        elif pct < 99.0:
            add(f"Campo {f}", WARN, f"presente en {pct:.1f} % de los ticks")
        elif np.all(np.ptp(arr, axis=0) == 0):
            add(f"Campo {f}", WARN, f"constante ({arr[0].tolist()})")
        else:
            add(f"Campo {f}", OK, f"min {arr.min():.3g} · max {arr.max():.3g}")

    t_s = _col(ticks, "t_s")
    v_kmh = _col(ticks, "speed_kmh")
    moving = v_kmh > 8

    # 3. |local_velocity| frente a la velocidad escalar
    lv = np.stack([_col(ticks, "local_velocity", i) for i in range(3)], axis=1)
    mod_kmh = np.linalg.norm(lv, axis=1) * 3.6
    m = moving & np.isfinite(mod_kmh)
    if m.sum() > 30:
        err = float(np.median(np.abs(mod_kmh[m] - v_kmh[m]) / v_kmh[m]))
        stats["local_velocity_rel_err"] = err
        add("|local_velocity| ≈ speed_kmh", OK if err < 0.05 else WARN if err < 0.15 else FAIL,
            f"error relativo mediano {100 * err:.1f} %")
        med = np.nanmedian(np.abs(lv[m]), axis=0)
        stats["local_velocity_axis"] = int(np.argmax(med))
        add("Eje longitudinal de local_velocity", OK,
            f"eje dominante {int(np.argmax(med))} (mediana |v| por eje: {np.round(med, 2).tolist()})")
    else:
        add("|local_velocity| ≈ speed_kmh", SKIP, "poco tiempo en movimiento")

    # 4. Aceleración longitudinal frente a derivada de la velocidad
    la = np.stack([_col(ticks, "local_accel", i) for i in range(3)], axis=1)
    dt = np.diff(t_s)
    if (dt > 0).all():
        dv = np.gradient(_smooth(v_kmh / 3.6), t_s)
        corrs = [_corr(_smooth(la[:, i]), dv) for i in range(3)]
        best = max(range(3), key=lambda i: abs(corrs[i] or 0))
        c = corrs[best]
        stats["a_long_axis"], stats["a_long_corr"] = best, c
        add("local_accel longitudinal ≈ dv/dt", OK if c and abs(c) > 0.6 else WARN,
            f"mejor eje {best}, correlación {c:.2f}" if c is not None else "sin datos")
    else:
        add("Reloj de ticks creciente", WARN, "t_s no es estrictamente creciente")

    # 5. Eje lateral: el que mejor sigue a v · yaw_rate (la producción asume el eje 2; ver DECISIONES H1)
    yaw = _col(ticks, "yaw_rate")
    lat = _col(ticks, "lat_accel")  # campo antiguo = local_acceleration[2]
    target = _smooth((v_kmh / 3.6) * yaw)
    lcorr = [_corr(_smooth(la[:, i]), target) for i in range(3)]
    if any(c is not None for c in lcorr):
        lat_axis = max(range(3), key=lambda i: abs(lcorr[i] or 0))
        stats["lateral_axis"], stats["lateral_corr"] = lat_axis, lcorr[lat_axis]
        stats["old_lat_accel_corr"] = _corr(_smooth(lat), target)
        c_lat = lcorr[lat_axis] or 0.0
        add("Eje lateral de local_accel (mejor correlación con v · yaw_rate)",
            OK if abs(c_lat) > 0.8 else WARN,
            f"eje {lat_axis}, correlación {c_lat:.2f} ({'mismo signo' if c_lat > 0 else 'signo contrario'}); "
            f"todos los ejes: {[None if c is None else round(c, 2) for c in lcorr]}")
        c_old = stats["old_lat_accel_corr"]
        add("Campo antiguo lat_accel (= local_acceleration[2]) es realmente lateral",
            OK if c_old is not None and abs(c_old) > 0.8 else FAIL,
            f"correlación con v · yaw_rate {c_old:.2f}" if c_old is not None else "sin datos")
        axes = [stats.get("a_long_axis"), lat_axis]
        if len(set(axes)) < 2:
            add("Ejes longitudinal y lateral distintos", FAIL, f"ambos resultan ser el eje {axes[0]}")

    # 6. Curvatura de la referencia
    if ref is not None:
        kappa = np.array([ref.curvature(d) for d in _col(ticks, "lap_distance")])
        c = _corr(_smooth(yaw), _smooth((v_kmh / 3.6) * kappa))
        stats["yaw_vs_v_kappa_corr"] = c
        if c is not None:
            add("yaw_rate ≈ v · curvatura de la referencia", OK if abs(c) > 0.6 else WARN,
                f"correlación {c:.2f} (el signo fija la convención; el coche no sigue la línea exacta)")
    else:
        add("Curvatura de la referencia", SKIP, "no se encontró el archivo de referencia")

    # 7. Posición integrada frente a lap_distance
    pos = np.stack([_col(ticks, "position", i) for i in range(3)], axis=1)
    if np.isfinite(pos).all():
        step = np.linalg.norm(np.diff(pos[:, [0, 2]], axis=0), axis=1)
        path_len = float(step[step < 50].sum())
        covered = float(np.sum(np.clip(np.diff(_col(ticks, "lap_distance")), 0, 50)))
        if covered > 100:
            ratio = path_len / covered
            stats["position_vs_lapdist_ratio"] = ratio
            add("Longitud de position (x,z) ≈ lap_distance recorrido", OK if 0.9 < ratio < 1.1 else WARN,
                f"cociente {ratio:.3f}")

    # 8. Reloj y pausas del juego
    if (dt > 0).all():
        stats["dt_median"] = float(np.median(dt))
        ps = pauses(ticks)
        game = [p for p in ps if p["pausa_del_juego"]]
        other = [p for p in ps if not p["pausa_del_juego"]]
        stats["game_pauses"], stats["other_gaps"] = len(game), len(other)
        fmt = lambda p: f"tick {p['tick']} ({p['duracion_s']} s, lap_distance {p['lap_distance']})"  # noqa: E731
        add("Reloj de ticks", OK if not other else WARN,
            f"Δt mediano {1000 * np.median(dt):.1f} ms"
            + (f" · {len(game)} pausas del juego (p. ej. clic fuera de la ventana): " + "; ".join(map(fmt, game[:5])) if game else "")
            + (f" · {len(other)} saltos sin pausa del juego, a revisar: " + "; ".join(map(fmt, other[:5])) if other else ""))
    # 8b. Bloque timing
    tim = [t.get("timing") for t in ticks]
    if any(tim):
        sectors = {x["sector"] for x in tim if x}
        gt = np.array([x["game_time_s"] for x in tim if x])
        add("Bloque timing (sector y reloj del juego)", OK if sectors <= {1, 2, 3} else FAIL,
            f"sectores vistos {sorted(sectors)} · reloj del juego {gt.min():.1f}–{gt.max():.1f} s")
    else:
        add("Bloque timing (sector y reloj del juego)", SKIP, "el log no lo trae (X4a)")

    # 8c. Tanda 2 y condiciones (X4b)
    check_x4b(ticks, events or [], add)

    # 9. Tamaño
    bpt = _bytes_per_tick(path, len(ticks))
    stats["bytes_per_tick"] = bpt
    old = _old_log_bytes_per_tick(path)
    detail = f"{bpt:.0f} B/tick"
    if old:
        stats["bytes_per_tick_old"] = old[1]
        detail += f" frente a {old[1]:.0f} B/tick del log antiguo ({old[0]}): ×{bpt / old[1]:.2f}"
    add("Tamaño del log (P1)", OK, detail)
    return checks, stats


def incidents(ticks: List[dict]) -> List[dict]:
    flags = ("safety_override", "off_track", "off_surface", "off_track_cte", "stuck")
    out: List[dict] = []
    for fl in flags:
        start = None
        for i, t in enumerate(ticks + [{}]):
            on = bool(t.get(fl))
            if on and start is None:
                start = i
            elif not on and start is not None:
                a, b = ticks[start], ticks[i - 1]
                out.append({"tipo": fl, "vuelta": a.get("lap"), "tick": a.get("tick"),
                            "lap_distance": f"{a.get('lap_distance')}–{b.get('lap_distance')}",
                            "duracion_ticks": i - start,
                            "razon": a.get("safety_event") or a.get("teacher_reason")})
                start = None
    return sorted(out, key=lambda r: r["tick"] or 0)


def _png(fig) -> str:
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def make_plots(ticks: List[dict], ref, lat_axis: int = 0) -> List[Tuple[str, str]]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = _col(ticks, "lap_distance")
    lap = _col(ticks, "lap")
    v = _col(ticks, "speed_kmh")
    la = [_col(ticks, "local_accel", i) for i in range(3)]
    av = [_col(ticks, "ang_vel", i) for i in range(3)]
    yaw = _col(ticks, "yaw_rate")
    pos = np.stack([_col(ticks, "position", i) for i in range(3)], axis=1)
    laps = np.unique(lap[np.isfinite(lap)])
    plots: List[Tuple[str, str]] = []

    fig, ax = plt.subplots(5, 1, figsize=(14, 14), sharex=True)
    for L in laps:
        m = lap == L
        ax[0].plot(d[m], v[m], lw=1.0, label=f"vuelta {int(L)}")
        ax[2].plot(d[m], yaw[m], lw=.9)
    first = lap == laps[0] if len(laps) else np.ones(len(d), bool)
    for i, name in enumerate(("long", "vert", "lat")):
        ax[1].plot(d[first], la[i][first], lw=.6, label=f"local_accel {name}")
    for i, name in enumerate(("eje 0", "eje 1", "eje 2")):
        ax[3].plot(d[first], av[i][first], lw=.6, label=f"ang_vel {name}")
    if ref is not None:
        ax[4].plot(d[first], [ref.curvature(x) for x in d[first]], lw=.7, color="k")
    titles = ("Velocidad (km/h)", "local_accel (m/s²), 1ª vuelta", "yaw_rate (rad/s)",
              "ang_vel (rad/s), 1ª vuelta", "Curvatura referencia (+izq / −der)")
    for a, t in zip(ax, titles):
        a.set_ylabel(t, fontsize=8)
        a.grid(alpha=.3)
    for a in (ax[0], ax[1], ax[3]):
        a.legend(fontsize=7)
    ax[4].set_xlabel("lap_distance (m)")
    plots.append(("Señales por vuelta", _png(fig)))

    fig, ax = plt.subplots(1, 2, figsize=(14, 5.5))
    ax[0].scatter(la[lat_axis], (v / 3.6) * yaw, s=2, alpha=.25)
    ax[0].set_xlabel(f"local_accel eje {lat_axis} (m/s²)")
    ax[0].set_ylabel("v · yaw_rate")
    ax[0].grid(alpha=.3)
    if np.isfinite(pos).all():
        sc = ax[1].scatter(pos[:, 0], pos[:, 2], c=v, s=1, cmap="viridis")
        ax[1].set_aspect("equal")
        fig.colorbar(sc, ax=ax[1], label="km/h")
        ax[1].set_title("Trayectoria (position x,z)", fontsize=9)
    plots.append(("Coherencia lateral y trayectoria", _png(fig)))
    return plots


_CSS = ("body{font:14px system-ui,sans-serif;margin:24px;max-width:1100px}table{border-collapse:collapse;width:100%}"
        "td,th{border:1px solid #ccc;padding:4px 8px;text-align:left;font-size:13px}"
        ".ok{background:#e3f6e3}.aviso{background:#fff3cd}.fallo{background:#f8d7da}.omitido{background:#eee}"
        "img{max-width:100%}")


def build_report(log_path: Path, open_browser: bool = False) -> Dict[str, Any]:
    log_path = Path(log_path)
    header, ticks, events = load_log(log_path)
    ref = _load_reference(header)
    checks, stats = run_checks(log_path, header, ticks, ref, events)
    inc = incidents(ticks)
    secs = sector_table(ticks)
    pz = pauses(ticks)
    plots = make_plots(ticks, ref, stats.get("lateral_axis", 0)) if len(ticks) >= 200 else []

    OUT.mkdir(parents=True, exist_ok=True)
    stem = f"informe_{log_path.stem}"
    result: Dict[str, Any] = {
        "log": str(log_path), "stats": stats, "incidents": inc, "events": len(events), "sectors": secs, "pauses": pz,
        "checks": [dict(zip(("nombre", "estado", "detalle"), c)) for c in checks],
    }
    (OUT / f"{stem}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=float), encoding="utf-8")

    n = {s: sum(1 for c in checks if c[1] == s) for s in (OK, WARN, FAIL, SKIP)}
    rows = "".join(f"<tr class='{s}'><td>{escape(nm)}</td><td>{s}</td><td>{escape(d)}</td></tr>"
                   for nm, s, d in checks)
    irows = "".join("<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in r.values()) + "</tr>" for r in inc)
    srows = "".join("<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in r.values()) + "</tr>" for r in secs)
    sec_html = (f"<h2>Sectores ({len(secs)} tramos)</h2><table><tr><th>Vuelta</th><th>Sector</th><th>Ticks</th>"
                f"<th>Conducción (s)</th><th>Sector juego (s)</th><th>Vel. media</th><th>lap_distance</th>"
                f"<th>Ticks con incidencia</th></tr>{srows}</table>") if secs else ""
    html = (
        f"<!doctype html><meta charset='utf-8'><title>{escape(stem)}</title><style>{_CSS}</style>"
        f"<h1>Informe C0</h1><p>{escape(log_path.name)} · {len(ticks)} ticks · "
        f"{n[OK]} ok · {n[WARN]} avisos · {n[FAIL]} fallos · {n[SKIP]} omitidos</p>"
        f"<h2>Comprobaciones</h2><table><tr><th>Comprobación</th><th>Estado</th><th>Detalle</th></tr>{rows}</table>"
        + sec_html
        + "".join(f"<h2>{escape(t)}</h2><img src='data:image/png;base64,{b}'>" for t, b in plots)
        + f"<h2>Incidencias ({len(inc)})</h2><table><tr><th>Tipo</th><th>Vuelta</th><th>Tick</th>"
        f"<th>lap_distance</th><th>Duración (ticks)</th><th>Razón</th></tr>{irows}</table>"
    )
    html_path = OUT / f"{stem}.html"
    html_path.write_text(html, encoding="utf-8")
    result["html"] = str(html_path)
    if open_browser:
        webbrowser.open(html_path.as_uri())
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print(f"[informe] {build_report(Path(sys.argv[1]), open_browser='--open' in sys.argv)['html']}")
