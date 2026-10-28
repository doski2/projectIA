"""Reetiquetado sin solape de gas y freno (P16): quita el solape de las acciones de los datos de entrenamiento.

No modifica los originales: escribe copias en `experimental/data/` (ignoradas por git) y un resumen `.json`.

Modos:
    menor  pone a 0 el pedal menor de cada fila (el plan del roadmap)
    neto   deja un solo eje: gas − freno

Las filas de `maintain_speed` y `brake_overspeed` se pueden descartar (`--drop-reasons`): sus etiquetas vienen del
teacher antiguo (gas fijo de 0,2 y freno por la velocidad de curva heurística) y no coinciden con lo que hace el nuevo.

Uso:
    python experimental/common/reetiquetar.py --mode menor [--drop-reasons maintain_speed,brake_overspeed]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "PCARS2-AI"
OUT = REPO / "experimental" / "data"
sys.path.insert(0, str(APP / "src"))

from teacher_intents import encode_reason_id  # noqa: E402

MODES = ("menor", "neto")
OVERLAP_MIN = 0.05  # ambos pedales por encima de esto cuentan como solape


def relabel_actions(act: np.ndarray, mode: str = "menor") -> np.ndarray:
    """`act` en [-1, 1] con columnas (gas, freno, volante); devuelve una copia sin solape de pedales."""
    if mode not in MODES:
        raise ValueError(f"modo desconocido: {mode}")
    out = np.array(act, dtype=np.float32, copy=True)
    thr, brk = (out[:, 0] + 1.0) / 2.0, (out[:, 1] + 1.0) / 2.0
    if mode == "menor":
        brake_wins = brk > thr
        thr = np.where(brake_wins, 0.0, thr)
        brk = np.where(brake_wins, brk, 0.0)
    else:
        net = thr - brk
        thr, brk = np.clip(net, 0.0, 1.0), np.clip(-net, 0.0, 1.0)
    out[:, 0], out[:, 1] = 2.0 * thr - 1.0, 2.0 * brk - 1.0
    return out


def overlap_share(act: np.ndarray) -> float:
    if len(act) == 0:
        return 0.0
    thr, brk = (act[:, 0] + 1.0) / 2.0, (act[:, 1] + 1.0) / 2.0
    return float(np.mean((thr > OVERLAP_MIN) & (brk > OVERLAP_MIN)))


def _summary(acts_before: List[List[float]], acts_after: List[List[float]], reasons: List[str]) -> dict:
    before, after = np.array(acts_before, dtype=np.float32), np.array(acts_after, dtype=np.float32)
    by: Dict[str, List[int]] = defaultdict(list)
    for i, r in enumerate(reasons):
        by[r].append(i)
    per_reason = {
        r: {"filas": len(ix), "solape_antes": round(overlap_share(before[ix]), 3),
            "solape_despues": round(overlap_share(after[ix]), 3)}
        for r, ix in sorted(by.items(), key=lambda kv: -len(kv[1]))
    }
    return {
        "filas": int(len(before)), "solape_antes": round(overlap_share(before), 3),
        "solape_despues": round(overlap_share(after), 3),
        "cambio_medio_gas": round(float(np.abs((after[:, 0] - before[:, 0]) / 2).mean()), 4) if len(before) else 0.0,
        "cambio_medio_freno": round(float(np.abs((after[:, 1] - before[:, 1]) / 2).mean()), 4) if len(before) else 0.0,
        "por_razon": per_reason,
    }


def relabel_jsonl(src: Path, dst: Path, mode: str, drop_reasons: Iterable[str] = ()) -> dict:
    drop = set(drop_reasons)
    before: List[List[float]] = []
    after: List[List[float]] = []
    reasons: List[str] = []
    dropped = 0
    with open(src, encoding="utf-8") as fin, open(dst, "w", encoding="utf-8") as fout:
        for raw in fin:
            line = raw.strip()
            if not line:
                continue
            row = json.loads(line)
            reason = row.get("teacher_reason", "")
            if reason in drop:
                dropped += 1
                continue
            act = np.array([row["action"]], dtype=np.float32)
            new = relabel_actions(act, mode)
            before.append(list(map(float, act[0])))
            after.append(list(map(float, new[0])))
            reasons.append(reason)
            row["action"] = [float(x) for x in new[0]]
            row["relabel"] = mode
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
    out = _summary(before, after, reasons)
    out["descartadas"] = dropped
    return out


def relabel_npz(src: Path, dst: Path, mode: str, drop_reasons: Iterable[str] = ()) -> dict:
    data = {k: v for k, v in np.load(src, allow_pickle=True).items()}
    act = data["act"]
    drop_ids = {encode_reason_id(r) for r in drop_reasons}
    keep = ~np.isin(data["rid"], list(drop_ids)) if drop_ids else np.ones(len(act), dtype=bool)
    new = relabel_actions(act, mode)
    ids = data["rid"]
    summary = _summary(act[keep].tolist(), new[keep].tolist(), [str(i) for i in ids[keep]])
    summary["descartadas"] = int((~keep).sum())
    out = {k: (v[keep] if getattr(v, "shape", None) and len(v) == len(act) else v) for k, v in data.items()}
    out["act"] = new[keep]
    np.savez_compressed(dst, **out)
    return summary


def run(sources: List[Path], mode: str, drop_reasons: List[str], out_dir: Path = OUT, force: bool = False) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict = {"modo": mode, "descartadas_por_razon": drop_reasons, "archivos": {}}
    for src in sources:
        dst = out_dir / f"{src.stem}_sinsolape{src.suffix}"
        if dst.exists() and not force:
            raise FileExistsError(f"{dst} ya existe (usa --force para sobrescribirlo)")
        if dst.resolve() == src.resolve():
            raise ValueError("el destino no puede ser el original")
        fn = relabel_npz if src.suffix == ".npz" else relabel_jsonl
        results["archivos"][str(dst)] = fn(src, dst, mode, drop_reasons)
    (out_dir / "reetiquetado_resumen.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=MODES, default="menor")
    ap.add_argument("--src", nargs="*", type=Path,
                    default=[APP / "data" / "universal_teacher.jsonl", APP / "data" / "curated_buffer.npz"])
    ap.add_argument("--drop-reasons", default="", help="razones del teacher que se descartan, separadas por comas")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    drops = [r for r in a.drop_reasons.split(",") if r]
    res = run(a.src, a.mode, drops, force=a.force)
    for path, s in res["archivos"].items():
        print(f"{path}: {s['filas']} filas · solape {s['solape_antes']:.1%} → {s['solape_despues']:.1%} · "
              f"descartadas {s['descartadas']}")
        for r, v in list(s["por_razon"].items())[:6]:
            print(f"    {r:24s} {v['filas']:7d} filas  solape {v['solape_antes']:.1%} → {v['solape_despues']:.1%}")
