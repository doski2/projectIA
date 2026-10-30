"""Gas que predice un modelo frente a la etiqueta del teacher, por buffer (diagnóstico sin juego, con la intención del teacher
como en `learn_driver`). Sirve para ver si una banda falla porque el BC no sube el gas y para medir un fine-tune antes de probarlo.

Uso:
    python experimental/common/diag_rows.py experimental/data/bc50_ft_model.pt bc50_check bc50_perturb
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "experimental" / "data"

sys.path.insert(0, str(REPO / "PCARS2-AI" / "src"))
from teacher_intents import encode_reason_id  # noqa: E402
from universal_policy import load_universal_policy  # noqa: E402


def main(model_path: str, names: list) -> None:
    model = load_universal_policy(model_path).eval()
    print("modelo", Path(model_path).name)
    for name in names:
        rows = [json.loads(line) for line in open(DATA / f"{name}_buffer.jsonl", encoding="utf-8")]
        obs = torch.tensor(np.array([r["obs"] for r in rows], dtype=np.float32))
        onehot = torch.zeros(len(rows), model.num_reasons)
        for i, r in enumerate(rows):
            onehot[i, int(r.get("reason_id", encode_reason_id(r.get("teacher_reason", ""))))] = 1.0
        with torch.no_grad():
            gas = (model(obs, onehot).numpy()[:, 0] + 1) / 2
        label = np.array([(r["action"][0] + 1) / 2 for r in rows])
        why = np.array([r["teacher_reason"] for r in rows])
        acc, maint = why == "accel_straight", why == "maintain_speed"
        big = acc & (label > 0.3)
        print(f"  {name}: accel n={acc.sum()} pred {gas[acc].mean():.3f} etq {label[acc].mean():.3f}"
              f" | accel con etq>0,3 n={big.sum()} pred {gas[big].mean():.3f} etq {label[big].mean():.3f}"
              f" | maintain pred {gas[maint].mean():.4f} etq {label[maint].mean():.4f} MAE {np.abs(gas[maint] - label[maint]).mean():.4f}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2:])
