"""
PCARS2-AI v2 — Presets de entrenamiento y configuración por defecto.

Los modos definen qué flags de main.py se activan. Los ajustes de la GUI
se fusionan con los defaults del modo seleccionado.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List

_CURR_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_CURR_SRC) not in sys.path:
    sys.path.insert(0, str(_CURR_SRC))

from learning_curriculum import LEARN_STAGES, SPEED_BANDS_KMH  # noqa: E402,F401  (re-export)
from ppo_defaults import RESUME_BC_PULL, SPEED_MAX_KMH, SPEED_STEP_KMH  # noqa: E402


@dataclass
class TeachingSettings:
    """Parámetros del Teaching Driver."""

    reference: str = "src/refs/sugo_ai.json"
    speed_target_kmh: float = 20.0
    gamepad: str = "xbox"
    mode_id: str = "teacher"
    dataset_output: str = "data/universal_teacher.jsonl"
    bc_model_path: str = "models/universal_bc.pt"
    hybrid_alpha: float = 0.7
    graduation_laps: int = 5
    max_laps: int = 0


@dataclass
class TrainingSettings:
    """Parámetros editables desde la GUI."""

    reference: str = "src/refs/sugo_ai.json"
    timesteps: int = 150_000
    speed_target_kmh: float = 20.0
    frame_skip: int = 4
    warmup_steps: int = 30
    gamepad: str = "xbox"
    car: str = "formula_rookie"
    track: str = "sugo"
    model_path: str = ""
    fresh_start: bool = False
    save_freq: int = 10_000
    seed: int = 42
    mode_id: str = "basico"

    def combo(self) -> str:
        return f"{self.car}__{self.track}"


@dataclass
class TrainingMode:
    id: str
    label: str
    description: str
    cli_flags: List[str] = field(default_factory=list)
    default_overrides: Dict[str, Any] = field(default_factory=dict)


TEACHING_MODES: List[TrainingMode] = [
    TrainingMode(
        id="teacher",
        label="Teacher — reglas puras",
        description="Conduce con reglas (CTE + heading + curvatura) a velocidad objetivo.",
        cli_flags=[],
        default_overrides={"speed_target_kmh": 20.0},
    ),
    TrainingMode(
        id="record",
        label="Record — teacher + dataset",
        description="Igual que Teacher pero graba demostraciones TEACHER en JSONL.",
        cli_flags=[],
        default_overrides={"speed_target_kmh": 20.0},
    ),
    TrainingMode(
        id="bc_drive",
        label="BC Drive — imitación con fallback",
        description="Política BC en vivo; teacher interviene si sale de línea.",
        cli_flags=[],
        default_overrides={"speed_target_kmh": 20.0},
    ),
    TrainingMode(
        id="hybrid",
        label="Hybrid — mezcla BC + teacher",
        description="Mezcla gradual; gradúa a autonomía tras vueltas limpias.",
        cli_flags=[],
        default_overrides={"speed_target_kmh": 20.0, "hybrid_alpha": 0.7},
    ),
    TrainingMode(
        id="autonomous",
        label="Autonomous — BC sin teacher",
        description="Control total BC; teacher solo en emergencia.",
        cli_flags=[],
        default_overrides={"speed_target_kmh": 25.0},
    ),
]


TRAINING_MODES: List[TrainingMode] = [
    TrainingMode(
        id="continuar_ppo",
        label="Continuar PPO - protegido, sin vigilancia - recomendado",
        description=(
            "Continúa desde el último modelo PPO del combo (si no hay, parte del BC destilado), "
            "con la observación universal, compensación del volante, episodios de 2 vueltas y la "
            "velocidad objetivo subiendo +2,5 km/h solo tras 3 episodios limpios (techo 80, el máximo del currículo). "
            "Se protege sola: vuelve al último modelo seguro tras 2 fallos y se detiene si no hay forma de avanzar. "
            "Pensado para dejarlo sin vigilancia; revisa el avance con ppo_progreso.bat."
        ),
        cli_flags=[
            "--obs-schema", "universal_v1", "--steer-comp", "--laps-per-episode", "2",
            "--resume-ppo", "--bc-pull", str(RESUME_BC_PULL), "--no-speed-ramp",
            "--speed-gate", "--speed-step-kmh", str(SPEED_STEP_KMH), "--speed-max-kmh", str(int(SPEED_MAX_KMH)),
            "--base-model", "models/ppo_universal_base.zip",
        ],
        default_overrides={
            "speed_target_kmh": 60.0,
            "warmup_steps": 30,
            "frame_skip": 1,
            "timesteps": 200_000,
            "fresh_start": False,
            "model_path": "",
        },
    ),
    TrainingMode(
        id="bc_anclado",
        label="Anclado al BC (universal) - recomendado",
        description=(
            "PPO parte del BC destilado (models/ppo_universal_base.zip; genéralo con "
            "src/ppo_bootstrap.py), observación universal_v1, compensación del volante y "
            "frame_skip 1 (el BC actúa a 60 Hz). Reward completa; el objetivo queda fijo (sin rampa) "
            "para poder comparar tiradas."
        ),
        cli_flags=[
            "--obs-schema", "universal_v1", "--steer-comp", "--no-speed-ramp", "--laps-per-episode", "2",
            "--base-model", "models/ppo_universal_base.zip",
        ],
        default_overrides={
            "speed_target_kmh": 60.0,
            "warmup_steps": 30,
            "frame_skip": 1,
            "timesteps": 50_000,
            "fresh_start": False,
            "model_path": "",
        },
    ),
    TrainingMode(
        id="basico",
        label="Básicos — línea, velocidad, girar",
        description=(
            "Conducir a la velocidad objetivo en el trazado. "
            "Empieza en 20 km/h; sube +5 km/h al mantener el ritmo."
        ),
        cli_flags=["--basics"],
        default_overrides={
            "speed_target_kmh": 20.0,
            "warmup_steps": 30,
            "frame_skip": 4,
            "timesteps": 150_000,
        },
    ),
    TrainingMode(
        id="curriculum",
        label="Curriculum (legacy)",
        description="Solo gas + velocidad. Útil si el coche no arranca; preferir Básicos.",
        cli_flags=["--curriculum"],
        default_overrides={
            "warmup_steps": 30,
            "frame_skip": 4,
            "speed_target_kmh": 0.0,
            "timesteps": 500_000,
        },
    ),
    TrainingMode(
        id="completo",
        label="Reward completa",
        description="Todas las señales (CTE, frenada ref, overspeed…). Solo cuando ya conduce bien.",
        cli_flags=[],
        default_overrides={
            "warmup_steps": 30,
            "frame_skip": 4,
            "speed_target_kmh": 0.0,
            "timesteps": 500_000,
        },
    ),
    TrainingMode(
        id="completo_velocidad",
        label="Completa + objetivo de velocidad",
        description="Reward completa con --speed-target-kmh para ir subiendo de forma controlada.",
        cli_flags=[],
        default_overrides={
            "warmup_steps": 30,
            "frame_skip": 4,
            "speed_target_kmh": 35.0,
            "timesteps": 500_000,
        },
    ),
    TrainingMode(
        id="personalizado",
        label="Personalizado",
        description="Tú eliges cada ajuste; sin flags de modo automáticos.",
        cli_flags=[],
        default_overrides={},
    ),
]


# Ritmo medido de PPO en el juego: 2048 pasos cada ~35 s (fps 54-59 en metricas.csv, pausas de actualización incluidas)
STEPS_PER_SECOND = 58.0


def steps_to_time_text(steps: int, frame_skip: int = 1) -> str:
    """Duración aproximada de un entrenamiento. Cada paso cubre `frame_skip` frames de juego a ~60 Hz."""
    seconds = max(0, steps) * max(1, frame_skip) / STEPS_PER_SECOND
    minutes = round(seconds / 60)
    hours, minutes = divmod(minutes, 60)
    return f"≈ {hours} h {minutes} min" if hours else f"≈ {minutes} min"


def get_mode(mode_id: str) -> TrainingMode:
    for mode in TRAINING_MODES:
        if mode.id == mode_id:
            return mode
    return TRAINING_MODES[0]


def get_teaching_mode(mode_id: str) -> TrainingMode:
    for mode in TEACHING_MODES:
        if mode.id == mode_id:
            return mode
    return TEACHING_MODES[0]


def apply_mode_defaults(settings: TrainingSettings) -> TrainingSettings:
    """Aplica overrides del modo al settings (no borra model_path)."""
    mode = get_mode(settings.mode_id)
    for key, value in mode.default_overrides.items():
        setattr(settings, key, value)
    return settings


def settings_to_dict(settings: TrainingSettings) -> Dict[str, Any]:
    return asdict(settings)


def learn_settings_to_dict(settings: LearnSettings) -> Dict[str, Any]:
    return asdict(settings)


@dataclass
class LearnSettings:
    """Parámetros del pipeline Aprendizaje BC (F5)."""

    reference: str = "src/refs/sugo_ai.json"
    stage_id: str = "l1_linea"
    model_path: str = "models/universal_bc.pt"
    dataset_path: str = "data/universal_teacher.jsonl"
    buffer_path: str = "data/online_buffer.jsonl"
    gamepad: str = "xbox"
    learn_every: int = 1
    max_laps: int = 0
    open_report: bool = True
    speed_target_kmh: float = 0.0  # 0 = usa banda; >0 = override fino (avanzado)
    speed_band_kmh: float = 20.0  # banda fija L1–L7 (teacher a este objetivo)
    steer_comp: bool = False  # compensar la curva de respuesta del volante (experimental)


LEARN_STAGE_IDS: List[str] = list(LEARN_STAGES.keys())


def learn_settings_from_dict(data: Dict[str, Any]) -> LearnSettings:
    s = LearnSettings()
    for key, value in data.items():
        if hasattr(s, key):
            setattr(s, key, value)
    return s


def settings_from_dict(data: Dict[str, Any]) -> TrainingSettings:
    s = TrainingSettings()
    for key, value in data.items():
        if hasattr(s, key):
            setattr(s, key, value)
    return s
