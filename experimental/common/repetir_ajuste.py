"""Repite un log por el ajuste unificado (`PCARS2-AI/src/curve_adapt.py`) y dice qué habría decidido, vuelta a vuelta, frente a lo que decidieron los ajustes de entonces.

Sin juego (paso 3 de `circuito_virtual/docs/DISENO_AJUSTE_UNIFICADO.md`). Arranca con los valores que la sesión aplicó al empezar (eventos `*_adapt_start`:
base × multiplicador) y alimenta el `CurveAdapter` tick a tick con lo que el log trae.

Con `log_schema` ≤ 4 faltan datos y se aproximan:
- la fase del teacher sale de `teacher_reason`: `brake_overspeed` y `lift_lock` = frenada, `accel_exit` = salida, el resto = conducción;
- no hay `exit_bound`: se supone que el tope recortaba (la subida del gas puede salir optimista);
- no hay `v*(s)`: el canal `brake` no se puede juzgar por la velocidad al soltar (sale «media» salvo por síntomas comunes) y por defecto va apagado (`--canales`).

Uso: `python repetir_ajuste.py <log.jsonl> [--canales lat,exit] [--bases lat=9.5,exit=18,brake=11] [--json salida.json]`
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "PCARS2-AI" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from curve_adapt import CHANNELS, CurveAdaptConfig, CurveAdapter, Tick  # noqa: E402

ENTRY_REASONS = {"brake_overspeed", "lift_lock"}
OLD_EVENT = {"lat": "lat_adapt", "exit": "exit_adapt", "brake": "brake_adapt"}
CHANGES = {"sube", "baja", "aviso", "limite", "tope"}


def parse_bases(text: str) -> Dict[str, float]:
    out = {}
    for part in text.split(","):
        k, _, v = part.partition("=")
        out[k.strip()] = float(v)
    return out


def _phase(r: dict) -> str:
    reason = r.get("teacher_reason") or ""
    if r.get("phase_teacher"):  # log_schema 5
        return str(r["phase_teacher"])
    if reason in ENTRY_REASONS:
        return "entry"
    if reason == "accel_exit":
        return "exit"
    return "drive"


def tick_of(r: dict) -> Tick:
    v = r.get("vehicle") or {}
    lv = v.get("local_velocity") or [0.0, 0.0, 0.0]
    tyres = v.get("tyre_temp") or []
    return Tick(
        lap=int(r.get("lap", 0)), s=float(r.get("lap_distance", 0.0)), signed_cte=float(r.get("signed_cte", r.get("cte", 0.0))),
        local_vx=float(lv[0]), local_vz=float(lv[2]), terrain=v.get("terrain") or (0, 0, 0, 0),
        tyre_c=(sum(tyres) / len(tyres)) if tyres else None, phase=_phase(r),
        exit_bound=bool(r.get("exit_bound", True)), gas=float(v.get("game_throttle", r.get("throttle", 0.0))), gas_req=float(r.get("throttle", 0.0)),
        brake=float(v.get("game_brake", r.get("brake", 0.0))), limiter_scale=float(v.get("brake_scale", 1.0)), over_ms=float(r.get("over_profile_ms", 0.0)),
        rps=v.get("tyre_rps") or (0.0, 0.0, 0.0, 0.0), gear=int(r.get("gear", 0)), clutch=int(v.get("clutch", 0)),
        steering=float(r.get("steering", 0.0)), speed_ms=float(r.get("speed_kmh", 0.0)) / 3.6,
    )


def replay(path: Path, channels: Sequence[str], bases: Dict[str, float], curvas: Path, track_length: float,
           config: Optional[CurveAdaptConfig] = None) -> Dict[str, Any]:
    rows: List[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    ad = CurveAdapter.from_curvas_json(curvas, bases, track_length, config or CurveAdaptConfig(), channels)
    started: Dict[str, Any] = {}
    absolute: Dict[str, Dict[str, float]] = {}
    old: Dict[str, Dict[int, Dict[str, str]]] = {ch: {} for ch in CHANNELS}
    for r in rows:
        t = r.get("type")
        if t == "curve_adapt_start" and isinstance(r.get("valores"), dict):  # logs con el ajuste unificado: valores absolutos
            absolute = {ch: v for ch, v in r["valores"].items() if isinstance(v, dict)}
        if t == "curve_adapt" and isinstance(r.get("curvas"), dict):
            for c, row in r["curvas"].items():
                for ch, cell in row.items():
                    old.setdefault(ch, {}).setdefault(int(r["lap"]), {})[c] = cell.get("decision", "")
        for ch in CHANNELS:
            if t == f"{OLD_EVENT[ch]}_start" and r.get("applied") and r.get("scales"):
                started[ch] = r["scales"]
            if t == OLD_EVENT[ch] and isinstance(r.get("decisions"), dict):
                old[ch][int(r["lap"])] = r["decisions"]
    for ch, scales in started.items():
        if ch in ad.channels:
            for k, s in scales.items():
                if int(k) in ad.state:
                    ad.state[int(k)][ch].value = ad._clip(ch, bases[ch] * float(s))
    for ch, vals in absolute.items():
        if ch in ad.channels:
            for k, v in vals.items():
                if int(k) in ad.state:
                    ad.state[int(k)][ch].value = ad._clip(ch, float(v))
    initial = {ch: ad.values(ch) for ch in ad.channels}
    laps: List[dict] = []
    for r in rows:
        if r.get("type") != "tick" or "vehicle" not in r:
            continue
        upd = ad.observe(tick_of(r))
        if upd is not None:
            laps.append(upd)
    return {"log": path.name, "canales": list(ad.channels), "iniciales": initial, "vueltas": laps, "antes": old,
            "finales": {ch: ad.values(ch) for ch in ad.channels}, "razon_libre": round(ad.free.value, 4)}


def _print(res: Dict[str, Any]) -> None:
    print(f"== {res['log']}  canales {','.join(res['canales'])}  razón libre {res['razon_libre']}")
    for ch in res["canales"]:
        print(f"  {ch} al empezar: " + " ".join(f"C{k}={v:g}" for k, v in res["iniciales"][ch].items()))
    for lap in res["vueltas"]:
        n = lap["lap"]
        now = []
        for c, row in lap["curvas"].items():
            for ch, cell in row.items():
                if cell["decision"] in CHANGES:
                    why = f" ({cell['motivo']})" if cell["motivo"] and cell["decision"] in ("baja", "aviso") else ""
                    now.append(f"C{c}.{ch} {cell['decision']}{why}")
        before = []
        for ch in res["canales"]:
            for c, d in (res["antes"].get(ch, {}).get(n) or {}).items():
                if d in ("sube", "baja"):
                    before.append(f"C{c}.{ch} {d}")
        print(f"  vuelta {n:2d}: ahora  " + ("; ".join(now) or "sin cambios"))
        print("            antes  " + ("; ".join(before) or "sin cambios"))
    for ch in res["canales"]:
        print(f"  {ch} al final:   " + " ".join(f"C{k}={v:g}" for k, v in res["finales"][ch].items()))


def main(argv: Optional[Sequence[str]] = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("log", type=Path, nargs="+")
    ap.add_argument("--canales", default="lat,exit", help="canales a repetir (por defecto lat,exit: los logs viejos no traen v* para la frenada)")
    ap.add_argument("--bases", default="lat=9.5,exit=18,brake=11", help="valores base de la sesión (--lat-accel-limit, --exit-circle, --brake-decel-straight)")
    ap.add_argument("--curvas", type=Path, default=REPO / "circuito_virtual" / "pistas" / "sugo_gp" / "curvas.json")
    ap.add_argument("--largo", type=float, default=3567.01)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    channels = [c.strip() for c in a.canales.split(",") if c.strip()]
    out = []
    for p in a.log:
        res = replay(p, channels, parse_bases(a.bases), a.curvas, a.largo)
        _print(res)
        print()
        out.append(res)
    if a.json:
        a.json.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
