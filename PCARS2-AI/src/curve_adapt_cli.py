"""Opciones de línea de órdenes del ajuste por curva y su manejo en el bucle de `learn_driver.py` (`curve_adapt.py`).

Opciones nuevas: `--curve-adapt`, `--curve-adapt-only lat,exit,brake`, `--curve-adapt-load` (repetible: un mapa de formato 2, o `canal=ruta` para uno de formato 1),
`--curve-adapt-save` (el mapa «limpio», con las dos últimas vueltas sin bajadas, y además `<mapa>_ultimo.json` en cada vuelta), `--curve-adapt-fixed` y `--curve-adapt-max lat=14.6,exit=23.4,brake=13.2`.

Las de antes (`--lat-adapt*`, `--exit-adapt*`, `--brake-adapt*`) siguen valiendo como alias con el mismo efecto: cada una activa su canal, su `-load` carga el mapa de
formato 1 en ese canal, su `-fixed` congela ese canal, y la cota máxima sale como antes (lateral: el menor de `--lat-adapt-cap` y base × `--lat-adapt-max-scale`;
gas y frenada: base × su `-max-scale`). Su `-save` guarda el mapa unificado (formato 2) en esa ruta.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from curve_adapt import CHANNELS, CurveAdaptConfig, CurveAdapter, Tick, load_map, save_map

OLD = {"lat": "lat_adapt", "exit": "exit_adapt", "brake": "brake_adapt"}
DEFAULT_SCALE = {"lat": 1.15, "exit": 1.3, "brake": 1.15}


def add_arguments(parser: argparse.ArgumentParser) -> None:
    g = parser.add_argument_group("ajuste por curva (curve_adapt.py, diseño en circuito_virtual/docs/DISENO_AJUSTE_UNIFICADO.md)")
    g.add_argument("--curve-adapt", action="store_true",
                   help="Ajusta por curva, vuelta a vuelta, el límite lateral, el gas de salida y la frenada (valores absolutos; baja con 2 de 3 vueltas malas; recuerda el último nivel malo).")
    g.add_argument("--curve-adapt-only", default="", help="Con --curve-adapt: solo estos canales, p. ej. «lat» o «lat,exit» (por defecto los tres).")
    g.add_argument("--curve-adapt-load", action="append", default=[],
                   help="Mapa de partida: uno de formato 2, o «canal=ruta» para uno de formato 1 (los de --lat/exit/brake-adapt). Se puede repetir.")
    g.add_argument("--curve-adapt-save", default="", help="Guarda aquí el mapa (formato 2) al cerrar cada vuelta, solo si las dos últimas no tuvieron ninguna bajada.")
    g.add_argument("--curve-adapt-fixed", action="store_true", help="Con --curve-adapt-load: usa el mapa y no aprende (se mide y se registra todo).")
    g.add_argument("--curve-adapt-max", default="", help="Cotas máximas absolutas en m/s², p. ej. «lat=14.6,exit=23.4,brake=13.2» (por defecto esas).")
    # alias de las opciones de antes
    g.add_argument("--lat-adapt", action="store_true", help="Alias: --curve-adapt con el canal lat.")
    g.add_argument("--lat-adapt-max-scale", type=float, default=DEFAULT_SCALE["lat"], help="Alias: cota del canal lat = base × esto (sin pasar de --lat-adapt-cap).")
    g.add_argument("--lat-adapt-cap", type=float, default=10.0, help="Alias: cota absoluta del canal lat en m/s² (por defecto 10).")
    g.add_argument("--lat-adapt-save", default="", help="Alias de --curve-adapt-save.")
    g.add_argument("--lat-adapt-load", default="", help="Alias: mapa de formato 1 para el canal lat.")
    g.add_argument("--lat-adapt-fixed", action="store_true", help="Alias: el canal lat no aprende.")
    g.add_argument("--brake-adapt", action="store_true", help="Alias: --curve-adapt con el canal brake.")
    g.add_argument("--brake-adapt-max-scale", type=float, default=DEFAULT_SCALE["brake"], help="Alias: cota del canal brake = base × esto.")
    g.add_argument("--brake-adapt-save", default="", help="Alias de --curve-adapt-save.")
    g.add_argument("--brake-adapt-load", default="", help="Alias: mapa de formato 1 para el canal brake.")
    g.add_argument("--brake-adapt-fixed", action="store_true", help="Alias: el canal brake no aprende.")
    g.add_argument("--exit-adapt", action="store_true", help="Alias: --curve-adapt con el canal exit.")
    g.add_argument("--exit-adapt-max-scale", type=float, default=DEFAULT_SCALE["exit"], help="Alias: cota del canal exit = base × esto.")
    g.add_argument("--exit-adapt-save", default="", help="Alias de --curve-adapt-save.")
    g.add_argument("--exit-adapt-load", default="", help="Alias: mapa de formato 1 para el canal exit.")
    g.add_argument("--exit-adapt-fixed", action="store_true", help="Alias: el canal exit no aprende.")


def _bases(args: Any) -> Dict[str, float]:
    return {"lat": float(getattr(args, "lat_accel_limit", 0.0) or 0.0), "exit": float(getattr(args, "exit_circle", 0.0) or 0.0),
            "brake": float(getattr(args, "brake_decel_straight", 0.0) or 0.0)}


def _check_channel(ch: str, args: Any, bases: Dict[str, float]) -> None:
    pedal = bool(getattr(args, "pedal_technique", False))
    if ch == "lat" and not bases["lat"]:
        raise SystemExit("el canal lat (--curve-adapt / --lat-adapt) necesita --lat-accel-limit")
    if ch == "exit" and (not bases["exit"] or not pedal):
        raise SystemExit("el canal exit (--curve-adapt / --exit-adapt) necesita --exit-circle y --pedal-technique")
    if ch == "brake" and (not bases["brake"] or not pedal or not getattr(args, "brake_profile", False)):
        raise SystemExit("el canal brake (--curve-adapt / --brake-adapt) necesita --brake-decel-straight, --brake-profile y --pedal-technique")


def _parse_max(text: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for part in [p for p in text.split(",") if p.strip()]:
        k, _, v = part.partition("=")
        if k.strip() not in CHANNELS or not v:
            raise SystemExit(f"--curve-adapt-max: «{part}» no es «canal=valor» (canales: lat, exit, brake)")
        out[k.strip()] = float(v)
    return out


def build(args: Any, reference: str, track_length: float) -> Optional["CurveRuntime"]:  # noqa: C901 - una comprobación por opción
    """El ajuste por curva según las opciones, o None si no se pidió. Sale con SystemExit ante una combinación imposible."""
    new = bool(getattr(args, "curve_adapt", False))
    old = [ch for ch in CHANNELS if getattr(args, OLD[ch], False)]
    if not new and not old:
        return None
    if new and old:
        raise SystemExit("--curve-adapt no se mezcla con --lat-adapt / --exit-adapt / --brake-adapt (son sus alias)")
    bases = _bases(args)
    cfg = CurveAdaptConfig()
    loads: List[tuple] = []
    if new:
        only = [c.strip() for c in str(getattr(args, "curve_adapt_only", "") or "").split(",") if c.strip()]
        bad = set(only) - set(CHANNELS)
        if bad:
            raise SystemExit(f"--curve-adapt-only: canales desconocidos {sorted(bad)} (lat, exit, brake)")
        channels = only or list(CHANNELS)
        cfg.maxima.update(_parse_max(str(getattr(args, "curve_adapt_max", "") or "")))
        cfg.learn = not getattr(args, "curve_adapt_fixed", False)
        for item in getattr(args, "curve_adapt_load", []) or []:
            ch, sep, path = str(item).partition("=")
            loads.append((ch.strip(), path) if sep and ch.strip() in CHANNELS else (None, str(item)))
        save = str(getattr(args, "curve_adapt_save", "") or "")
        if not cfg.learn and not loads:
            raise SystemExit("--curve-adapt-fixed necesita --curve-adapt-load")
    else:
        channels = old
        fixed = []
        saves = []
        for ch in old:
            scale = float(getattr(args, f"{OLD[ch]}_max_scale", DEFAULT_SCALE[ch]))
            top = bases[ch] * scale
            if ch == "lat":
                top = min(top, float(getattr(args, "lat_adapt_cap", 10.0)))
            cfg.maxima[ch] = max(top, bases[ch])  # con la base por encima de la cota, las curvas pueden bajar pero no subir (como antes)
            load = str(getattr(args, f"{OLD[ch]}_load", "") or "")
            if getattr(args, f"{OLD[ch]}_fixed", False):
                if not load:
                    raise SystemExit(f"--{OLD[ch].replace('_', '-')}-fixed necesita --{OLD[ch].replace('_', '-')}-load")
                fixed.append(ch)
            if load:
                loads.append((ch, load))
            s = str(getattr(args, f"{OLD[ch]}_save", "") or "")
            if s and s not in saves:
                saves.append(s)
        cfg.fixed = tuple(fixed)
        if len(saves) > 1:
            print(f"[Learn] ajuste por curva: varias rutas de guardado ({', '.join(saves)}); el mapa es uno solo y va a {saves[0]}")
        save = saves[0] if saves else ""
    for ch in channels:
        _check_channel(ch, args, bases)
        cfg.minima[ch] = min(cfg.minima[ch], bases[ch])
    curvas_json = Path(reference).with_name("curvas.json")
    if not curvas_json.is_file():
        raise SystemExit(f"el ajuste por curva necesita el catálogo de curvas junto a la referencia: {curvas_json}")
    adapter = CurveAdapter.from_curvas_json(curvas_json, {ch: bases[ch] for ch in channels}, float(track_length), cfg, channels)
    for ch, path in loads:
        try:
            data = load_map(Path(path))
            if ch is not None and ch not in adapter.channels:
                print(f"[Learn] ajuste por curva: el mapa {path} es del canal {ch}, que no está activo; no se carga")
                continue
            adapter.load_prior(data, ch)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"ajuste por curva: no puedo cargar el mapa {path}: {exc}") from exc
        print(f"[Learn] ajuste por curva: mapa {path}" + (f" (canal {ch})" if ch else "") + " (se aplica al llegar las condiciones de hoy; si no son compatibles se ignora)")
    estado = "fijo" if not cfg.learn else ("aprende" + (f", fijos: {','.join(cfg.fixed)}" if cfg.fixed else ""))
    print(f"[Learn] ajuste por curva: canales {','.join(adapter.channels)} ({estado}) | bases " + " ".join(f"{ch}={bases[ch]:g}" for ch in adapter.channels)
          + " | cotas " + " ".join(f"{ch}={cfg.minima[ch]:g}-{cfg.maxima[ch]:g}" for ch in adapter.channels) + " m/s²")
    return CurveRuntime(adapter, save, str(getattr(args, "experiment", "") or ""), int(track_length),
                        setup_path=Path(reference).with_name("reglaje_vigente.json"))


def tick_from(telem: Any, timings: Any, decision: Any, final: Any, teacher: Any, brake_slip: Any) -> Tick:
    """El tick del ajuste con lo que hay en el bucle de `learn_driver`."""
    tyres = list(getattr(telem, "tyre_temp", None) or ())
    cfg = teacher.config
    over = 0.0
    if getattr(cfg, "brake_profile", False) and getattr(cfg, "lat_accel_limit", None):
        over = float(telem.speed) - float(teacher.profile_at(timings.lap_distance))
    return Tick(
        lap=int(timings.current_lap), s=float(timings.lap_distance), signed_cte=float(decision.signed_cte),
        local_vx=float(telem.local_velocity[0]), local_vz=float(telem.local_velocity[2]), terrain=tuple(getattr(telem, "terrain", (0, 0, 0, 0)) or (0, 0, 0, 0)),
        tyre_c=(sum(tyres) / len(tyres)) if tyres else None, phase=str(teacher.phase), exit_bound=bool(teacher.exit_bound),
        gas=float(final[0]), gas_req=float(final[0]), brake=float(final[1]), limiter_scale=float(brake_slip.scale) if brake_slip is not None else 1.0,
        over_ms=over, rps=tuple(telem.tyre_rps), gear=int(getattr(telem, "gear", 0) or 0), clutch=int(getattr(telem, "clutch", 0) or 0),
        steering=float(final[2]), speed_ms=float(telem.speed),
    )


class CurveRuntime:
    """Arranque con las condiciones de hoy, un tick, y al cerrar cada vuelta: aplicar al teacher, registrar, guardar e imprimir."""

    CHANGES = ("sube", "baja", "aviso", "limite", "tope")

    def __init__(self, adapter: CurveAdapter, save_path: str, experiment: str, track_m: int, setup_path: Optional[Path] = None):
        self.adapter = adapter
        self.save_path = save_path
        self.experiment = experiment
        self.track_m = track_m
        self.setup_path = setup_path
        self.started = False

    def last_path(self) -> Path:
        """`<mapa>_ultimo.json`: el estado al cerrar cada vuelta, junto al mapa «limpio»."""
        p = Path(self.save_path)
        return p.with_name(p.stem + "_ultimo" + p.suffix)

    def apply(self, teacher: Any) -> None:
        setters = {"lat": "set_lat_scales", "exit": "set_exit_scales", "brake": "set_brake_scales"}
        for ch in self.adapter.channels:
            getattr(teacher, setters[ch])(self.adapter.scales_per_m(ch, self.track_m))

    def start(self, now_cond: dict, setup: Optional[dict], teacher: Any, record_event: Callable[[dict], None]) -> None:
        self.started = True
        info = self.adapter.start(now_cond, setup=setup)
        record_event({"type": "curve_adapt_start", "conditions": now_cond, "canales": list(self.adapter.channels),
                      **(info or {"applied": False, "reason": "sin mapa cargado", "valores": {ch: self.adapter.values(ch) for ch in self.adapter.channels}})})
        self.apply(teacher)  # con o sin mapa: los valores de partida (la base, o lo cargado) van al teacher
        if info is not None and info.get("applied"):
            print(f"[Learn] ajuste por curva: mapa aplicado, desajuste {info['mismatch']:g} (pista {info['mismatch_track']:g}, gomas {info['mismatch_tyre']:g})"
                  + ("" if info["memoria"] else " · memoria de niveles malos olvidada" + (" (otro reglaje)" if info["reglaje_distinto"] else ""))
                  + " | " + self.values_text())
        elif info is not None:
            print(f"[Learn] ajuste por curva: mapa IGNORADO ({info['reason']}); sigo desde la base")

    def values_text(self) -> str:
        return " · ".join(f"{ch}: " + " ".join(f"C{k}={v:g}" for k, v in self.adapter.values(ch).items()) for ch in self.adapter.channels)

    def tick(self, tick: Tick, teacher: Any, record_event: Callable[[dict], None]) -> Optional[dict]:
        upd = self.adapter.observe(tick)
        if upd is None:
            return None
        self.apply(teacher)
        record_event({"type": "curve_adapt", **upd})
        if self.save_path and self.adapter.cfg.learn and len(self.adapter.cfg.fixed) < len(self.adapter.channels):
            snap = self.adapter.snapshot({"experiment": self.experiment, "lap": upd["lap"]})
            save_map(self.last_path(), snap)  # el estado de cada vuelta, aunque haya bajadas (2026-11-13: con 42 casillas casi siempre baja alguna)
            if self.adapter.clean_tail():
                save_map(Path(self.save_path), snap)
                print(f"[Learn] ajuste por curva: mapa guardado en {self.save_path} (vuelta {upd['lap']}, dos últimas sin bajadas)")
        changes = [f"C{c}.{ch} {cell['decision']}" + (f" ({cell['motivo']})" if cell["decision"] in ("baja", "aviso") else "")
                   for c, row in upd["curvas"].items() for ch, cell in row.items() if cell["decision"] in self.CHANGES]
        print(f"[Learn] ajuste por curva, vuelta {upd['lap']}: " + ("; ".join(changes) or "sin cambios") + f" | razón libre {upd['razon_libre']:g}")
        return upd


__all__ = ["CurveRuntime", "add_arguments", "build", "tick_from"]
