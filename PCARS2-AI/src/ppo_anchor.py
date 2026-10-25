"""
ppo_anchor.py
Ancla de PPO al modelo de imitación (BC) para no perder lo aprendido al empezar.

- `anchor_log_std`: desviación inicial pequeña (PPO nace con std = 1,0 sobre acciones en [-1, 1]).
- `FreezeActorCallback`: congela el actor unas iteraciones para que el crítico (que el BC deja
  aleatorio) aprenda primero a valorar, y las ventajas no sean basura.
"""

from __future__ import annotations

import math
from typing import Callable

import torch
from stable_baselines3.common.callbacks import BaseCallback

DEFAULT_BC_STD = 0.1


def anchor_log_std(model, std: float = DEFAULT_BC_STD) -> bool:
    """Baja el log_std a log(std) si está por encima. Devuelve True si lo cambió."""
    log_std = getattr(model.policy, "log_std", None)
    if log_std is None:
        return False
    target = math.log(std)
    with torch.no_grad():
        if log_std.max().item() <= target:
            return False
        log_std.clamp_(max=target)
    return True


def _actor_params(policy) -> list:
    return (
        list(policy.mlp_extractor.policy_net.parameters())
        + list(policy.action_net.parameters())
        + [policy.log_std]
    )


class FreezeActorCallback(BaseCallback):
    """Mantiene el actor sin gradiente durante `warmup_steps` pasos de entorno."""

    def __init__(self, warmup_steps: int):
        super().__init__()
        self.warmup_steps = max(0, warmup_steps)
        self._frozen = False

    def _set_frozen(self, frozen: bool) -> None:
        for p in _actor_params(self.model.policy):
            p.requires_grad_(not frozen)
        self._frozen = frozen

    def _on_training_start(self) -> None:
        if self.warmup_steps > 0:
            self._set_frozen(True)
            print(f"[main] Actor congelado durante {self.warmup_steps} pasos (calentando el crítico).")

    def _on_rollout_end(self) -> None:
        # Los cambios de requires_grad deben hacerse entre rollouts, antes de optimizar.
        if self._frozen and self.num_timesteps >= self.warmup_steps:
            self._set_frozen(False)
            print("[main] Actor descongelado.")

    def _on_step(self) -> bool:
        return True


class HoldBrakeDuringUpdateCallback(BaseCallback):
    """El juego sigue en marcha mientras PPO actualiza la red: frena el coche durante la pausa."""

    def __init__(self, hold: Callable[[], None]):
        super().__init__()
        self._hold = hold

    def _on_rollout_end(self) -> None:
        self._hold()

    def _on_step(self) -> bool:
        return True
