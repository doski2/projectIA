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

from .config import (
    LearnSettings,
    TeachingSettings,
    TrainingSettings,
    get_mode,
    get_teaching_mode,
    settings_to_dict,
)

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


def learn_settings_file() -> Path:
    from learn_progress import progress_file

    return progress_file()


def save_settings(settings: TrainingSettings) -> None:
    path = settings_file()
    path.write_text(json.dumps(settings_to_dict(settings), indent=2), encoding="utf-8")


def load_settings() -> Optional[TrainingSettings]:
    path = settings_file()
    if not path.is_file():
        return None
    from .config import settings_from_dict

    return settings_from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_learn_settings(settings: LearnSettings) -> None:
    from learn_progress import merge_and_save_learn_settings

    from .config import learn_settings_to_dict

    merge_and_save_learn_settings(learn_settings_to_dict(settings))


def load_learn_settings() -> Optional[LearnSettings]:
    path = learn_settings_file()
    if not path.is_file():
        return None
    from .config import learn_settings_from_dict

    return learn_settings_from_dict(json.loads(path.read_text(encoding="utf-8")))


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


def _launch_argv(argv: List[str], window_title: str, new_console: bool = True) -> None:
    root = project_root()
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    if new_console and sys.platform == "win32":
        cmdline = subprocess.list2cmdline(argv)
        subprocess.Popen(
            f'start "{window_title}" cmd /k {cmdline}',
            shell=True,
            cwd=str(root),
            env=env,
        )
        return

    subprocess.Popen(argv, cwd=str(root), env=env)


def launch_training(settings: TrainingSettings, new_console: bool = True) -> None:
    save_settings(settings)
    _launch_argv(build_argv(settings), "PCARS2-AI Entrenamiento", new_console)


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


def build_teaching_argv(settings: TeachingSettings) -> List[str]:
    root = project_root()
    python = venv_python()
    get_teaching_mode(settings.mode_id)  # valida el modo (lanza si no existe)

    if settings.mode_id in ("teacher", "record"):
        script = root / "src" / "teaching_driver.py"
        argv = [
            str(python),
            str(script),
            "--mode",
            settings.mode_id,
            "--reference",
            settings.reference,
            "--speed-target",
            str(settings.speed_target_kmh),
            "--gamepad",
            settings.gamepad,
        ]
        if settings.mode_id == "record":
            argv.extend(["--output", settings.dataset_output, "--universal"])
        if settings.max_laps > 0:
            argv.extend(["--max-laps", str(settings.max_laps)])
        return argv

    script = root / "src" / "imitation_driver.py"
    model = settings.bc_model_path.strip()
    use_universal = model.endswith(".pt")
    argv = [
        str(python),
        str(script),
        "--mode",
        settings.mode_id,
        "--reference",
        settings.reference,
        "--speed-target",
        str(settings.speed_target_kmh),
        "--gamepad",
        settings.gamepad,
        "--open-report",
    ]
    if use_universal:
        argv.extend(["--universal", "--model", model])
    else:
        argv.extend(["--model", model])
    if settings.mode_id == "hybrid":
        argv.extend(["--alpha", str(settings.hybrid_alpha)])
        argv.extend(["--graduation-laps", str(settings.graduation_laps)])
    if settings.max_laps > 0:
        argv.extend(["--max-laps", str(settings.max_laps)])
    return argv


def format_teaching_command(settings: TeachingSettings) -> str:
    return subprocess.list2cmdline(build_teaching_argv(settings))


def launch_teaching(settings: TeachingSettings, new_console: bool = True) -> None:
    _launch_argv(build_teaching_argv(settings), "PCARS2-AI Teaching", new_console)


def build_learn_argv(settings: LearnSettings) -> List[str]:
    root = project_root()
    python = venv_python()
    script = root / "src" / "learn_driver.py"
    argv = [
        str(python),
        str(script),
        "--reference",
        settings.reference,
        "--model",
        settings.model_path,
        "--base-dataset",
        settings.dataset_path,
        "--buffer",
        settings.buffer_path,
        "--stage",
        settings.stage_id,
        "--learn-every",
        str(settings.learn_every),
        "--gamepad",
        settings.gamepad,
    ]
    if settings.open_report:
        argv.append("--open-report")
    if settings.max_laps > 0:
        argv.extend(["--max-laps", str(settings.max_laps)])
    if settings.speed_band_kmh > 0:
        argv.extend(["--speed-band", str(int(settings.speed_band_kmh))])
    if settings.speed_target_kmh > 0:
        argv.extend(["--speed-target", str(settings.speed_target_kmh)])
    if settings.steer_comp:
        argv.append("--steer-comp")
    return argv


def format_learn_command(settings: LearnSettings) -> str:
    return subprocess.list2cmdline(build_learn_argv(settings))


def launch_learn(settings: LearnSettings, new_console: bool = True) -> None:
    save_learn_settings(settings)
    _launch_argv(build_learn_argv(settings), "PCARS2-AI Aprendizaje", new_console)


def launch_pretrain_bc(
    dataset: str = "data/universal_teacher.jsonl",
    output: str = "models/universal_bc.pt",
    new_console: bool = True,
) -> None:
    root = project_root()
    python = venv_python()
    script = root / "src" / "pretrain_universal.py"
    argv = [
        str(python),
        str(script),
        "--dataset",
        dataset,
        "--output",
        output,
    ]
    _launch_argv(argv, "PCARS2-AI Entrenar BC", new_console)


def launch_eval_bc(
    dataset: str = "data/universal_teacher.jsonl",
    model: str = "models/universal_bc.pt",
    new_console: bool = True,
) -> None:
    root = project_root()
    python = venv_python()
    script = root / "src" / "eval_universal.py"
    argv = [
        str(python),
        str(script),
        "--dataset",
        dataset,
        "--model",
        model,
    ]
    _launch_argv(argv, "PCARS2-AI Eval BC", new_console)


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
