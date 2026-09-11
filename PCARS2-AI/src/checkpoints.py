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
