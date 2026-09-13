"""
Utilidades compartidas para seleccionar checkpoints de SB3.
"""

from __future__ import annotations

import glob
import os
from typing import List, Optional


def step_number_from_checkpoint(path: str) -> int:
    """Extrae el número de pasos de un archivo `*_NNNNN_steps.zip`."""
    name = os.path.basename(path)
    marker = "_steps.zip"
    if not name.endswith(marker):
        return -1
    stem = name[: -len(marker)]
    digits = stem.rsplit("_", 1)[-1]
    try:
        return int(digits)
    except ValueError:
        return -1


def pick_latest_checkpoint(paths: List[str]) -> Optional[str]:
    """Devuelve la ruta al checkpoint con más pasos, o None si la lista está vacía."""
    if not paths:
        return None
    return max(paths, key=step_number_from_checkpoint)


def resolve_combo_checkpoint(model_dir: str, name_prefix: str) -> Optional[str]:
    """
    Mejor checkpoint del combo (ruta sin .zip).

    Prioridad unificada GUI / main:
      1. *_steps.zip con más pasos
      2. *_final.zip
    """
    pattern = os.path.join(model_dir, f"{name_prefix}_*_steps.zip")
    best = pick_latest_checkpoint(glob.glob(pattern))
    if best:
        return best[:-4]

    final = os.path.join(model_dir, f"{name_prefix}_final.zip")
    if os.path.isfile(final):
        return final[:-4]

    return None
