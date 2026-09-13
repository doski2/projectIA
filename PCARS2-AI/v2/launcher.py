"""
PCARS2-AI v2 — Construcción de comandos y lanzamiento de procesos.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from .config import TrainingSettings, get_mode

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from checkpoints import resolve_combo_checkpoint  # noqa: E402


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def venv_python() -> Path:
    return project_root().parent / ".venv" / "Scripts" / "python.exe"


def settings_file() -> Path:
    return Path(__file__).resolve().parent / "user_settings.json"


def save_settings(settings: TrainingSettings) -> None:
    path = settings_file()
    path.write_text(json.dumps(settings_to_dict(settings), indent=2), encoding="utf-8")


def load_settings() -> Optional[TrainingSettings]:
    path = settings_file()
    if not path.is_file():
        return None
    from .config import settings_from_dict

    return settings_from_dict(json.loads(path.read_text(encoding="utf-8")))


def settings_to_dict(settings: TrainingSettings) -> dict:
    from .config import settings_to_dict as _to_dict

    return _to_dict(settings)


def list_references() -> List[str]:
    refs_dir = project_root() / "src" / "refs"
    if not refs_dir.is_dir():
        return []
    return sorted(
        str(p.relative_to(project_root())).replace("\\", "/")
        for p in refs_dir.glob("*.json")
    )


def find_latest_checkpoint(combo: str) -> Optional[str]:
    """Devuelve ruta al checkpoint sin .zip (formato SB3)."""
    model_dir = project_root() / "models" / combo
    if not model_dir.is_dir():
        return None
    return resolve_combo_checkpoint(str(model_dir), f"pcars2_{combo}")


def build_argv(settings: TrainingSettings) -> List[str]:
    root = project_root()
    python = venv_python()
    main_py = root / "src" / "main.py"
    mode = get_mode(settings.mode_id)

    argv: List[str] = [
        str(python),
        str(main_py),
        "--reference",
        settings.reference,
        "--timesteps",
        str(settings.timesteps),
        "--frame-skip",
        str(settings.frame_skip),
        "--warmup-steps",
        str(settings.warmup_steps),
        "--gamepad",
        settings.gamepad,
        "--car",
        settings.car,
        "--track",
        settings.track,
        "--save-freq",
        str(settings.save_freq),
        "--seed",
        str(settings.seed),
    ]

    for flag in mode.cli_flags:
        argv.append(flag)

    if settings.speed_target_kmh > 0:
        argv.extend(["--speed-target-kmh", str(settings.speed_target_kmh)])

    if settings.model_path.strip():
        argv.extend(["--model", settings.model_path.strip()])
    elif settings.fresh_start:
        argv.append("--fresh")

    return argv


def format_command(settings: TrainingSettings) -> str:
    argv = build_argv(settings)
    return subprocess.list2cmdline(argv)


def launch_training(settings: TrainingSettings, new_console: bool = True) -> None:
    save_settings(settings)
    root = project_root()
    argv = build_argv(settings)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    if new_console and sys.platform == "win32":
        cmdline = subprocess.list2cmdline(argv)
        subprocess.Popen(
            f'start "PCARS2-AI Entrenamiento" cmd /k {cmdline}',
            shell=True,
            cwd=str(root),
            env=env,
        )
        return

    subprocess.Popen(argv, cwd=str(root), env=env)


def launch_monitor(settings: TrainingSettings) -> None:
    root = project_root()
    python = venv_python()
    monitor_py = root / "src" / "monitor.py"
    csv_path = root / "logs" / settings.combo() / "metricas.csv"
    argv = [
        str(python),
        str(monitor_py),
        "--refresh",
        "20",
        "--timesteps",
        str(settings.timesteps),
        str(csv_path),
    ]
    if sys.platform == "win32":
        cmdline = subprocess.list2cmdline(argv)
        subprocess.Popen(
            f'start "PCARS2-AI Monitor" cmd /k {cmdline}',
            shell=True,
            cwd=str(root),
        )
    else:
        subprocess.Popen(argv, cwd=str(root))


def launch_tensorboard(combo: str) -> None:
    root = project_root()
    python = venv_python()
    logdir = root / "logs" / combo
    argv = [str(python), "-m", "tensorboard.main", "--logdir", str(logdir)]
    if sys.platform == "win32":
        cmdline = subprocess.list2cmdline(argv)
        subprocess.Popen(
            f'start "PCARS2-AI TensorBoard" cmd /k {cmdline}',
            shell=True,
            cwd=str(root),
        )
    else:
        subprocess.Popen(argv, cwd=str(root))
