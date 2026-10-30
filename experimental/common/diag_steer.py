"""Dirección que predice un modelo frente a la etiqueta del teacher, según lo lejos que va el coche de la línea (|CTE|).
La ganancia es la pendiente de la predicción sobre la etiqueta: 1 = el BC gira lo que pide el teacher; < 1 = se queda corto.
Hace falta el log de la prueba (alineado tick a tick con el buffer) para conocer el CTE.

Uso:
    python experimental/common/diag_steer.py experimental/data/bc55_ft_model.pt bc55_check=20261030T212719Z
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "experimental" / "data"
LOGS = REPO / "PCARS2-AI" / "logs" / "learning"

sys.path.insert(0, str(REPO / "PCARS2-AI" / "src"))
from teacher_intents import encode_reason_id  # noqa: E402
from universal_policy import load_universal_policy  # noqa: E402

BINS = (("< 0,3", lambda c: c < 0.3), ("> 1", lambda c: c > 1.0), ("> 1,5", lambda c: c > 1.5))


def main(model_path: str, pairs: list) -> None:
    model = load_universal_policy(model_path).eval()
    print("modelo", Path(model_path).name)
    for pair in pairs:
        name, _, ts = pair.partition("=")
        rows = [json.loads(line) for line in open(DATA / f"{name}_buffer.jsonl", encoding="utf-8")]
        ticks = [t for t in map(json.loads, open(LOGS / f"{ts}_sugo_gp_l1_linea.jsonl", encoding="utf-8")) if t.get("type") == "tick"]
        if len(rows) != len(ticks):
            raise SystemExit(f"{name}: el buffer ({len(rows)}) y el log ({len(ticks)}) no están alineados")
        obs = torch.tensor(np.array([r["obs"] for r in rows], dtype=np.float32))
        onehot = torch.zeros(len(rows), model.num_reasons)
        for i, r in enumerate(rows):
            onehot[i, int(r.get("reason_id", encode_reason_id(r.get("teacher_reason", ""))))] = 1.0
        with torch.no_grad():
            pred = model(obs, onehot).numpy()[:, 2]
        label = np.array([r["action"][2] for r in rows])
        cte = np.array([abs(t["cte"]) for t in ticks])
        free = np.array([t["drive_source"] != "perturb:coast" for t in ticks])
        out = []
        for title, rule in BINS:
            m = rule(cte) & free
            out.append(f"|CTE| {title}: n={m.sum()} error {np.abs(pred - label)[m].mean():.4f} ganancia {np.sum(pred[m] * label[m]) / np.sum(label[m] ** 2):.3f}")
        print(f"  {name}: " + " | ".join(out))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2:])
