"""
learn_progress.py
Persistencia de etapa L1–L7, banda de velocidad y ajustes entre sesiones (GUI + learn_driver).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from learning_curriculum import DEFAULT_LEARN_STAGE, DEFAULT_SPEED_BAND_KMH

_PROGRESS_FILE = Path(__file__).resolve().parent.parent / "v2" / "user_learn_settings.json"


def progress_file() -> Path:
    return _PROGRESS_FILE


def load_learn_progress() -> Dict[str, Any]:
    if not _PROGRESS_FILE.is_file():
        return {}
    try:
        return json.loads(_PROGRESS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def merge_and_save_learn_settings(updates: Dict[str, Any]) -> None:
    """Única escritura de user_learn_settings.json (GUI + learn_driver)."""
    data = load_learn_progress()
    data.update(updates)
    _PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PROGRESS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def save_learn_progress(
    stage_id: str,
    reference: Optional[str] = None,
    speed_target_kmh: Optional[float] = None,
    speed_band_kmh: Optional[float] = None,
    model_path: Optional[str] = None,
    dataset_path: Optional[str] = None,
) -> None:
    updates: Dict[str, Any] = {"stage_id": stage_id}
    if reference:
        updates["reference"] = reference
    if speed_target_kmh is not None:
        updates["speed_target_kmh"] = speed_target_kmh
    if speed_band_kmh is not None:
        updates["speed_band_kmh"] = speed_band_kmh
    if model_path:
        updates["model_path"] = model_path
    if dataset_path:
        updates["dataset_path"] = dataset_path
    merge_and_save_learn_settings(updates)


def read_saved_stage(default: str = DEFAULT_LEARN_STAGE) -> str:
    stage = load_learn_progress().get("stage_id", default)
    return stage if stage else default


def read_saved_speed_band(default: float = DEFAULT_SPEED_BAND_KMH) -> float:
    band = load_learn_progress().get("speed_band_kmh", default)
    try:
        return float(band) if band else default
    except (TypeError, ValueError):
        return default
