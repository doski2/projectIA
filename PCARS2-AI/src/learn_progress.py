"""
learn_progress.py
Persistencia de etapa L1–L5 y ajustes de aprendizaje entre sesiones (GUI + learn_driver).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from learning_curriculum import DEFAULT_LEARN_STAGE

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


def save_learn_progress(
    stage_id: str,
    reference: Optional[str] = None,
    speed_target_kmh: Optional[float] = None,
    model_path: Optional[str] = None,
    dataset_path: Optional[str] = None,
) -> None:
    data = load_learn_progress()
    data["stage_id"] = stage_id
    if reference:
        data["reference"] = reference
    if speed_target_kmh is not None:
        data["speed_target_kmh"] = speed_target_kmh
    if model_path:
        data["model_path"] = model_path
    if dataset_path:
        data["dataset_path"] = dataset_path
    _PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PROGRESS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_saved_stage(default: str = DEFAULT_LEARN_STAGE) -> str:
    stage = load_learn_progress().get("stage_id", default)
    return stage if stage else default
