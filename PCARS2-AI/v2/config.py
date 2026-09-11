"""
PCARS2-AI v2 — Presets de entrenamiento y configuración por defecto.

Los modos definen qué flags de main.py se activan. Los ajustes de la GUI
se fusionan con los defaults del modo seleccionado.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


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


TRAINING_MODES: List[TrainingMode] = [
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


def get_mode(mode_id: str) -> TrainingMode:
    for mode in TRAINING_MODES:
        if mode.id == mode_id:
            return mode
    return TRAINING_MODES[0]


def apply_mode_defaults(settings: TrainingSettings) -> TrainingSettings:
    """Aplica overrides del modo al settings (no borra model_path)."""
    mode = get_mode(settings.mode_id)
    for key, value in mode.default_overrides.items():
        setattr(settings, key, value)
    return settings


def settings_to_dict(settings: TrainingSettings) -> Dict[str, Any]:
    return asdict(settings)


def settings_from_dict(data: Dict[str, Any]) -> TrainingSettings:
    s = TrainingSettings()
    for key, value in data.items():
        if hasattr(s, key):
            setattr(s, key, value)
    return s
