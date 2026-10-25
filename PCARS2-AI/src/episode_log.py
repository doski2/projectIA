"""
episode_log.py
Un CSV con una fila por episodio de PPO (`episodios.csv`): cómo terminó, dónde y cuánto tardó.
`metricas.csv` solo trae medias por rollout, y con eso no se sabe en qué punto de la pista se sale
el coche ni cuánto dura una vuelta.
"""

from __future__ import annotations

import csv
import os
import time

from stable_baselines3.common.callbacks import BaseCallback

FIELDS = (
    "timestamp", "total_timesteps", "fin", "pasos", "lap_distance_m", "cte_m",
    "speed_kmh", "lap_time_s", "ep_reward",
)


class EpisodeLogger:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        new = not os.path.isfile(path) or os.path.getsize(path) == 0
        self._file = open(path, "a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        if new:
            self._writer.writerow(FIELDS)
            self._file.flush()

    def add(self, info: dict, total_timesteps: int) -> None:
        lap_time = info.get("lap_time_s")
        episode = info.get("episode") or {}
        self._writer.writerow([
            time.strftime("%H:%M:%S"),
            total_timesteps,
            info.get("term_reason", "?"),
            info.get("step", ""),
            info.get("lap_distance", ""),
            info.get("cte", ""),
            info.get("speed_kmh", ""),
            "" if lap_time is None else lap_time,
            episode.get("r", ""),
        ])
        self._file.flush()

    def close(self) -> None:
        self._file.close()


class EpisodeLogCallback(BaseCallback):
    """Escribe una fila cuando el entorno (un solo env) termina un episodio."""

    def __init__(self, path: str):
        super().__init__()
        self._logger = EpisodeLogger(path)

    def _on_step(self) -> bool:
        dones = self.locals.get("dones")
        infos = self.locals.get("infos")
        if dones is not None and infos is not None and dones[0]:
            self._logger.add(infos[0], self.num_timesteps)
        return True

    def _on_training_end(self) -> None:
        self._logger.close()
