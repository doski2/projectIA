"""Fine-tune del BC sin abrir el juego, a partir de buffers ya grabados (copia del modelo; nunca pisa el de origen).

Los buffers de las pruebas con perturbaciones (X18) llevan las filas que el BC visitó mal con la etiqueta del teacher, que es lo que
el fine-tune dentro del juego haría tras cada vuelta. Aquí se hace de golpe y se puede dejar una parte fuera para medir si generaliza.

Uso:
    python experimental/common/finetune_offline.py --model-src experimental/data/bc7c_ft_limpio_model.pt \
        --out experimental/data/bc40_ft_model.pt --source bc7c_ft_limpio_perturb_buffer.jsonl \
        --source bc40_perturb_buffer.jsonl:first=19469 --repeat-accel 3
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "PCARS2-AI"
DATA = REPO / "experimental" / "data"

sys.path.insert(0, str(APP / "src"))
from bc_training import fine_tune_universal  # noqa: E402
from dataset_recorder import load_universal_dataset  # noqa: E402
from teacher_intents import encode_reason_id  # noqa: E402

MIN_QUALITY = 0.5  # el de learn_driver.FINE_TUNE_MIN_QUALITY
BASE = DATA / "bc7c_ft_limpio_base.jsonl"  # lo que arma aislado.py con --finetune-every (teacher nuevo)


def parse_source(spec: str, data: Optional[Path] = None) -> Tuple[Path, Optional[int]]:
    """`fichero.jsonl` o `fichero.jsonl:first=N` (solo las N primeras líneas: sirve para dejar la última vuelta fuera)."""
    data = data or DATA
    name, _, opt = spec.partition(":")
    path = Path(name)
    if not path.is_absolute():
        path = data / path
    if not opt:
        return path, None
    key, _, val = opt.partition("=")
    if key != "first" or not val.isdigit() or int(val) <= 0:
        raise ValueError(f"opción no válida en {spec!r}: se espera `first=N` con N > 0")
    return path, int(val)


def load_source(path: Path, first: Optional[int] = None) -> tuple:
    """Carga un buffer entero o sus primeras `first` líneas, antes de filtrar por calidad (el índice es el de la línea)."""
    if first is None:
        return load_universal_dataset(str(path), min_quality=MIN_QUALITY)
    with tempfile.TemporaryDirectory() as tmp:
        cut = Path(tmp) / path.name
        with open(path, encoding="utf-8") as src, open(cut, "w", encoding="utf-8", newline="\n") as dst:
            for i, line in enumerate(src):
                if i >= first:
                    break
                dst.write(line)
        return load_universal_dataset(str(cut), min_quality=MIN_QUALITY)


def repeat_rows(chunk: tuple, mask: np.ndarray, times: int) -> tuple:
    """Añade `times - 1` copias de las filas marcadas (las pocas de recuperación frente a miles de `maintain_speed`)."""
    obs, act, rid, meta = chunk
    pick = np.flatnonzero(mask)
    if times <= 1 or len(pick) == 0:
        return chunk
    extra = times - 1
    return (
        np.concatenate([obs] + [obs[pick]] * extra),
        np.concatenate([act] + [act[pick]] * extra),
        np.concatenate([rid] + [rid[pick]] * extra),
        meta,
    )


def repeat_reason(chunk: tuple, reason: str, times: int) -> tuple:
    """Repite las filas de una intención."""
    if len(chunk[0]) == 0:
        return chunk
    return repeat_rows(chunk, chunk[2] == encode_reason_id(reason), times)


def repeat_off_line(chunk: tuple, cte_min: float, times: int) -> tuple:
    """Repite las filas con |CTE| ≥ cte_min: el BC ya iba fuera de la línea y el teacher dice cómo volver (dirección en curvas)."""
    if len(chunk[0]) == 0:
        return chunk
    cte = np.array([abs(float(r.get("cte", 0.0))) for r in chunk[3]])
    return repeat_rows(chunk, cte >= cte_min, times)


def concat(chunks: List[tuple]) -> tuple:
    chunks = [c for c in chunks if len(c[0])]
    return tuple(np.concatenate([c[i] for c in chunks]) for i in range(3))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model-src", required=True, type=Path, help="modelo de partida (no se modifica)")
    ap.add_argument("--out", required=True, type=Path, help="modelo nuevo; no puede ser el de origen")
    ap.add_argument("--source", action="append", default=[], help="buffer en experimental/data (repetible); admite :first=N")
    ap.add_argument("--base", type=Path, default=BASE, help="base del teacher nuevo; 'none' para no usarla")
    ap.add_argument("--repeat-accel", type=int, default=1, help="veces que entran las filas de accel_straight de los --source")
    ap.add_argument("--repeat-off-line", type=int, default=1, help="veces que entran las filas con |CTE| >= --off-line-cte de los --source")
    ap.add_argument("--off-line-cte", type=float, default=1.0)
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    if a.out.resolve() == a.model_src.resolve():
        ap.error("--out no puede ser el modelo de origen")
    if not a.source:
        ap.error("hace falta al menos un --source")
    import torch

    torch.manual_seed(a.seed)
    np.random.seed(a.seed)

    chunks = []
    if str(a.base).lower() != "none":
        base = load_universal_dataset(str(a.base), min_quality=MIN_QUALITY)
        print(f"[finetune] base {a.base.name}: {len(base[0])} filas")
        chunks.append(base)
    for spec in a.source:
        path, first = parse_source(spec)
        chunk = load_source(path, first)
        n = len(chunk[0])
        chunk = repeat_reason(chunk, "accel_straight", a.repeat_accel)
        chunk = repeat_off_line(chunk, a.off_line_cte, a.repeat_off_line)
        extra = (f" (accel_straight x{a.repeat_accel}, |CTE| >= {a.off_line_cte:g} x{a.repeat_off_line}: {len(chunk[0])})"
                 if a.repeat_accel > 1 or a.repeat_off_line > 1 else "")
        print(f"[finetune] {spec}: {n} filas{extra}")
        chunks.append(chunk)
    obs, act, rid = concat(chunks)
    print(f"[finetune] total {len(obs)} filas, {a.epochs} épocas, modelo de partida {a.model_src.name}")

    a.out.parent.mkdir(parents=True, exist_ok=True)
    work = a.out.with_suffix(".tmp.pt")
    shutil.copyfile(a.model_src, work)
    result = fine_tune_universal(str(work), obs, act, rid, output_path=str(a.out), epochs=a.epochs)
    work.unlink(missing_ok=True)
    print(f"[finetune] {result}")
    return 0 if result.get("trained") else 1


if __name__ == "__main__":
    raise SystemExit(main())
