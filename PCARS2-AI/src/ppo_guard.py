"""
ppo_guard.py
Entrenamiento de PPO que se protege solo, para dejarlo sin vigilancia (p. ej. toda la noche).

La velocidad objetivo sube con pruebas, no con el reloj:
  - 3 episodios limpios seguidos (lap_done, CTE medio <= 1,2 m y velocidad media a menos de 6 km/h
    del objetivo) validan la velocidad: se guarda el modelo (`*_safe.zip`) y el objetivo sube un paso pequeño.
  - 2 fallos seguidos (stuck, wrong_way, no_progress, pit_box, o una vuelta con CTE > 1,6 m)
    restauran el último modelo seguro y vuelven a la velocidad validada.
  - Demasiados retrocesos sin avanzar, o varios udp_timeout seguidos (el juego se ha cerrado o
    pausado), frenan el coche, restauran el modelo seguro y terminan el entrenamiento.
"""

from __future__ import annotations

import json
import os

from stable_baselines3.common.callbacks import BaseCallback

from ppo_defaults import GATE_CLEAN_CTE_M, GATE_FAIL_CTE_M, SPEED_MAX_KMH, SPEED_STEP_KMH

FAIL_REASONS = frozenset({"stuck", "wrong_way", "no_progress", "pit_box"})


class SpeedGate:
    """Reglas puras (sin SB3 ni juego): cada episodio terminado devuelve una acción."""

    def __init__(
        self,
        target_kmh: float,
        step_kmh: float = SPEED_STEP_KMH,
        max_kmh: float = SPEED_MAX_KMH,
        clean_needed: int = 3,
        clean_cte_m: float = GATE_CLEAN_CTE_M,
        speed_slack_kmh: float = 6.0,
        fail_cte_m: float = GATE_FAIL_CTE_M,
        fails_to_backoff: int = 2,
        max_backoffs: int = 3,
        max_udp_streak: int = 5,
    ):
        self.target_kmh = target_kmh
        self.safe_target_kmh = target_kmh
        self.step_kmh = step_kmh
        self.max_kmh = max_kmh
        self.clean_needed = clean_needed
        self.clean_cte_m = clean_cte_m
        self.speed_slack_kmh = speed_slack_kmh
        self.fail_cte_m = fail_cte_m
        self.fails_to_backoff = fails_to_backoff
        self.max_backoffs = max_backoffs
        self.max_udp_streak = max_udp_streak
        self.clean = 0
        self.fails = 0
        self.backoffs = 0
        self.udp_streak = 0

    def on_episode(self, info: dict) -> str:
        """Devuelve 'none' | 'raise' | 'safe' | 'backoff' | 'stop'."""
        reason = info.get("term_reason", "?")
        if reason == "udp_timeout":
            self.udp_streak += 1
            return "stop" if self.udp_streak >= self.max_udp_streak else "none"
        self.udp_streak = 0

        cte = float(info.get("ep_cte_mean", 0.0))
        speed = float(info.get("ep_speed_kmh", 0.0))
        failed = reason in FAIL_REASONS or (reason == "lap_done" and cte > self.fail_cte_m)
        if failed:
            self.clean = 0
            self.fails += 1
            if self.fails < self.fails_to_backoff:
                return "none"
            self.fails = 0
            self.backoffs += 1
            if self.backoffs > self.max_backoffs:
                return "stop"
            self.target_kmh = self.safe_target_kmh
            return "backoff"

        self.fails = 0
        clean = (
            reason == "lap_done"
            and cte <= self.clean_cte_m
            and speed >= self.target_kmh - self.speed_slack_kmh
        )
        if not clean:
            self.clean = 0
            return "none"
        self.clean += 1
        if self.clean < self.clean_needed:
            return "none"
        self.clean = 0
        self.safe_target_kmh = self.target_kmh
        if self.target_kmh + self.step_kmh <= self.max_kmh:
            self.target_kmh += self.step_kmh
            self.backoffs = 0
            return "raise"
        return "safe"


class SpeedGateCallback(BaseCallback):
    """Aplica las acciones de SpeedGate: guarda/restaura el modelo seguro y mueve la velocidad objetivo."""

    def __init__(self, raw_env, safe_path: str, state_path: str, gate: SpeedGate, restore_state: bool = True):
        super().__init__()
        self._env = raw_env
        self._safe_path = safe_path
        self._state_path = state_path
        self.gate = gate
        self._restore_state = restore_state   # el estado solo vale con los pesos que lo validaron

    def _save_safe(self) -> None:
        self.model.save(self._safe_path)
        try:
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump({"safe_target_kmh": self.gate.safe_target_kmh}, f)
        except OSError as exc:
            print(f"[Gate] No puedo escribir {self._state_path}: {exc}")

    def _restore_safe(self) -> None:
        if os.path.isfile(self._safe_path + ".zip") or os.path.isfile(self._safe_path):
            self.model.set_parameters(self._safe_path)

    def _on_training_start(self) -> None:
        if self._restore_state and os.path.isfile(self._state_path):
            try:
                with open(self._state_path, encoding="utf-8") as f:
                    proven = float(json.load(f)["safe_target_kmh"])
                self.gate.target_kmh = self.gate.safe_target_kmh = proven
                print(f"[Gate] Retomo desde la última velocidad validada: {proven:.1f} km/h")
            except (OSError, ValueError, KeyError):
                pass
        self._env.set_speed_target_kmh(self.gate.target_kmh)
        self._save_safe()
        print(f"[Gate] Objetivo {self.gate.target_kmh:.1f} km/h; sube {self.gate.step_kmh:g} km/h tras "
              f"{self.gate.clean_needed} episodios limpios (techo {self.gate.max_kmh:.0f} km/h).")

    def _on_step(self) -> bool:
        dones, infos = self.locals.get("dones"), self.locals.get("infos")
        if dones is None or infos is None or not dones[0]:
            return True
        info = infos[0]
        action = self.gate.on_episode(info)
        g = self.gate
        if action == "raise":
            self._save_safe()
            self._env.set_speed_target_kmh(g.target_kmh)
            print(f"[Gate] Velocidad validada ({g.safe_target_kmh:.1f} km/h). Nuevo objetivo: {g.target_kmh:.1f} km/h")
        elif action == "safe":
            self._save_safe()
            print(f"[Gate] Techo alcanzado y validado ({g.safe_target_kmh:.1f} km/h).")
        elif action == "backoff":
            self._restore_safe()
            self._env.set_speed_target_kmh(g.target_kmh)
            print(f"[Gate] Fallos seguidos ({info.get('term_reason')}): restauro el modelo seguro "
                  f"y vuelvo a {g.target_kmh:.1f} km/h (retroceso {g.backoffs}/{g.max_backoffs}).")
        elif action == "stop":
            self._restore_safe()
            self._env.hold_brake()
            print(f"[Gate] PARO el entrenamiento por seguridad (último fin: {info.get('term_reason')}). "
                  "Modelo seguro restaurado; revisa consola.log.")
            return False
        return True
