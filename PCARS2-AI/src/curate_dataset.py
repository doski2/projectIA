"""
curate_dataset.py
Compacta data/online_buffer.jsonl (ticks a 60 Hz casi idénticos, ~85 % maintain_speed)
en un .npz pequeño que el fine-tune carga en segundos.

    python src/curate_dataset.py --archive-raw

- Se queda con `universal_v1` de calidad >= --min-quality.
- Dentro de cada (pista, etapa, banda) descarta la fila que apenas cambia respecto a la
  última conservada (obs y acción).
- Limita `maintain_speed` a --maintain-cap del total; las razones raras se conservan todas.
- --archive-raw mueve el JSONL original a data/archive/ para que no se cuente dos veces.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Optional

import numpy as np

from obs_universal import OBS_SCHEMA, OBS_UNIVERSAL_DIM

DEFAULT_RAW = "data/online_buffer.jsonl"
DEFAULT_OUT = "data/curated_buffer.npz"
MAINTAIN_REASON = "maintain_speed"
OBS_EPS = 0.01
ACT_EPS = 0.05


def _similar(a: list, b: list, eps: float) -> bool:
    return all(abs(x - y) < eps for x, y in zip(a, b))


def curate(
    src: str,
    dst: str,
    min_quality: float = 0.9,
    maintain_cap: float = 0.4,
    seed: int = 0,
) -> dict:
    """Escribe `dst` (.npz) y devuelve estadísticas del curado."""
    read = 0
    last: dict = {}
    obs_l: list = []
    act_l: list = []
    rid_l: list = []
    maintain_l: list = []
    quality_l: list = []
    stage_l: list = []
    band_l: list = []
    track_l: list = []
    with open(src, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            read += 1
            if row.get("obs_schema") != OBS_SCHEMA or row.get("quality", 0.0) < min_quality:
                continue
            key = (row.get("track_name"), row.get("learn_stage"), row.get("speed_band_kmh"))
            obs, act = row["obs"], row["action"]
            prev = last.get(key)
            if prev is not None and _similar(obs, prev[0], OBS_EPS) and _similar(act, prev[1], ACT_EPS):
                continue
            last[key] = (obs, act)
            obs_l.append(obs)
            act_l.append(act)
            rid_l.append(int(row.get("reason_id") or 0))
            maintain_l.append(row.get("teacher_reason", "") == MAINTAIN_REASON)
            quality_l.append(row.get("quality", 0.0))
            stage_l.append(row.get("learn_stage") or "")
            band_l.append(float(row.get("speed_band_kmh") or 0.0))
            track_l.append(row.get("track_name") or "")

    maintain = np.array(maintain_l, dtype=bool)
    keep = np.ones(len(maintain), dtype=bool)
    n_rare = int((~maintain).sum())
    if maintain_cap < 1.0:
        n_maintain_keep = int(maintain_cap / (1.0 - maintain_cap) * n_rare)
    else:
        n_maintain_keep = len(maintain)
    maintain_idx = np.flatnonzero(maintain)
    if len(maintain_idx) > n_maintain_keep:
        drop = np.random.default_rng(seed).choice(
            maintain_idx, size=len(maintain_idx) - n_maintain_keep, replace=False,
        )
        keep[drop] = False

    def pick(values: list, dtype) -> np.ndarray:
        return np.array(values, dtype=dtype)[keep]

    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    np.savez_compressed(
        dst,
        obs=pick(obs_l, np.float32).reshape(-1, OBS_UNIVERSAL_DIM),
        act=pick(act_l, np.float32).reshape(-1, 3),
        rid=pick(rid_l, np.int64),
        quality=pick(quality_l, np.float32),
        stage=pick(stage_l, "U16"),
        band=pick(band_l, np.float32),
        track=pick(track_l, "U24"),
    )
    return {"read": read, "after_dedupe": len(maintain), "kept": int(keep.sum()), "rare": n_rare}


def load_curated(
    path: str,
    learn_stage: Optional[str] = None,
    speed_band_kmh: Optional[float] = None,
    track_name: Optional[str] = None,
) -> tuple:
    """(obs, act, reason_ids, []) con los mismos filtros que `load_universal_dataset`."""
    with np.load(path) as d:
        mask = np.ones(len(d["rid"]), dtype=bool)
        if learn_stage is not None:
            mask &= d["stage"] == learn_stage
        if speed_band_kmh is not None:
            mask &= d["band"] == np.float32(speed_band_kmh)
        if track_name:
            mask &= d["track"] == track_name
        return d["obs"][mask], d["act"][mask], d["rid"][mask], []


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--src", default=DEFAULT_RAW)
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--min-quality", type=float, default=0.9)
    p.add_argument("--maintain-cap", type=float, default=0.4)
    p.add_argument("--archive-raw", action="store_true",
                   help="Mueve el JSONL original a data/archive/ tras curarlo")
    args = p.parse_args()
    if os.path.isfile(args.out):
        print(f"[Curate] {args.out} ya existe: bórralo o elige otro --out (no se sobrescribe).")
        return 1
    t0 = time.monotonic()
    stats = curate(args.src, args.out, args.min_quality, args.maintain_cap)
    print(f"[Curate] {stats['read']:,} filas leídas -> {stats['kept']:,} conservadas "
          f"({stats['rare']:,} no-maintain) en {time.monotonic() - t0:.0f} s -> {args.out} "
          f"({os.path.getsize(args.out) / 1e6:.1f} MB)")
    if args.archive_raw:
        arch = os.path.join(os.path.dirname(args.src) or ".", "archive")
        os.makedirs(arch, exist_ok=True)
        dest = os.path.join(arch, f"online_buffer_raw_{time.strftime('%Y%m%dT%H%M%S')}.jsonl")
        os.replace(args.src, dest)
        print(f"[Curate] Original archivado en {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
