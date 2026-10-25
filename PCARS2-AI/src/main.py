"""
main.py
Lanzador de entrenamiento PPO para PCARS2-AI.

Entrena un agente PPO (Stable-Baselines3) que conduce en Project CARS 2
usando el entorno Gymnasium definido en environment.py.

Uso — entrenamiento desde cero:
    python main.py --reference refs/spa_ai.json

Continuar entrenamiento desde un checkpoint:
    python main.py --reference refs/spa_ai.json --model models/pcars2_ppo_100000_steps

Ajustar pasos de entrenamiento:
    python main.py --reference refs/spa_ai.json --timesteps 500000

Logs de TensorBoard:
    tensorboard --logdir logs/
"""

import argparse
import os
import sys
import glob
import csv

from checkpoints import pick_latest_checkpoint, resolve_combo_checkpoint
from ppo_defaults import (
    ANCHOR_EPOCHS,
    ANCHOR_LR,
    ANCHOR_TARGET_KL,
    BC_PULL,
    CRITIC_WARMUP_STEPS,
    DEFAULT_BC_STD,
    PPO_NET_ARCH,
)
import time as _time
import torch
from typing import Optional


# ---------------------------------------------------------------------------
# Utilidad: resetear log_std de la política a un valor razonable
# ---------------------------------------------------------------------------

def _reset_log_std(model, target_std: float = 0.8) -> None:
    """
    Resetea el log_std de la política PPO a log(target_std) SOLO si el std
    actual ha divergido (> 1.2). Si el modelo ya convergió a un std menor,
    no lo toca para no deshacer progreso.
    No afecta a los pesos del actor/crítico.
    """
    import math
    try:
        current_std = model.policy.log_std.exp().mean().item()
        if current_std <= 1.2:
            print(f"[main] log_std OK (std actual={current_std:.3f} ≤ 1.2) — no se resetea.")
            return
        log_std_val = math.log(target_std)
        with torch.no_grad():
            model.policy.log_std.fill_(log_std_val)
        print(f"[main] log_std reseteado: {current_std:.3f} → std={target_std:.2f} (divergido)")
    except AttributeError:
        pass  # Algunos tipos de política no tienen log_std separado


def _apply_update_settings(model, args) -> None:
    """Actualizaciones suaves: con std 0,1 un cambio pequeño de la media ya es un salto grande."""
    from stable_baselines3.common.utils import ConstantSchedule

    model.learning_rate = args.anchor_lr
    model.lr_schedule = ConstantSchedule(args.anchor_lr)
    model.n_epochs = args.anchor_epochs
    model.target_kl = args.anchor_target_kl
    print(f"[main] Actualizaciones suaves: lr={args.anchor_lr:g}, épocas={args.anchor_epochs}, "
          f"target_kl={args.anchor_target_kl:g}")


def _anchor_from_bc(model, args) -> None:
    """Modelo que nace del BC: std pequeña, actualizaciones suaves y actor congelado al inicio."""
    from ppo_anchor import anchor_log_std

    if anchor_log_std(model, args.bc_std):
        print(f"[main] log_std anclado al BC: std={args.bc_std:.2f}")
    _apply_update_settings(model, args)
    args.anchored_to_bc = True


def _create_ppo_from_scratch(env, tb_log):
    """Nueva política PPO con la arquitectura estándar del proyecto."""
    from stable_baselines3 import PPO

    return PPO(
        policy              = "MlpPolicy",
        policy_kwargs       = dict(net_arch=PPO_NET_ARCH),
        env                 = env,
        learning_rate       = 1e-4,
        n_steps             = 2048,
        batch_size          = 64,
        n_epochs            = 10,
        gamma               = 0.99,
        gae_lambda          = 0.95,
        clip_range          = 0.2,
        ent_coef            = 0.01,
        vf_coef             = 1.5,
        max_grad_norm       = 0.5,
        verbose             = 1,
        tensorboard_log     = tb_log,
    )


# ---------------------------------------------------------------------------
# Utilidad: buscar el mejor modelo disponible para un combo
# ---------------------------------------------------------------------------

def _find_best_model(
    model_dir:   str,
    name_prefix: str,
    models_root: str,
    subdir:      str,
) -> Optional[dict]:
    """
    Busca el mejor punto de partida para el combo dado.
    Devuelve un dict {'path': str, 'mode': 'continue'|'transfer'} o None.
    """
    combo_path = resolve_combo_checkpoint(model_dir, name_prefix)
    if combo_path:
        return {"path": combo_path, "mode": "continue"}

    # Transfer learning desde el base (solo si el combo no ES base)
    if subdir != "base":
        base_dir    = os.path.join(models_root, "base")
        base_final  = os.path.join(base_dir, "pcars2_base_final.zip")
        if os.path.isfile(base_final):
            return {"path": base_final[:-4], "mode": "transfer"}
        base_cps = glob.glob(os.path.join(base_dir, "pcars2_base_*_steps.zip"))
        best_base = pick_latest_checkpoint(base_cps)
        if best_base:
            return {"path": best_base[:-4], "mode": "transfer"}

    return None

# ---------------------------------------------------------------------------
# Argparser
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PCARS2-AI — Entrenamiento PPO",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--reference", "-r",
        required=True,
        metavar="RUTA_JSON",
        help="Ruta al archivo JSON de la línea de referencia grabada.",
    )
    parser.add_argument(
        "--timesteps", "-t",
        type=int,
        default=200_000,
        metavar="N",
        help="Número total de pasos de entrenamiento.",
    )
    parser.add_argument(
        "--model", "-m",
        default=None,
        metavar="RUTA_MODELO",
        help="Ruta a un modelo guardado para continuar el entrenamiento.",
    )
    parser.add_argument(
        "--save-freq",
        type=int,
        default=10_000,
        metavar="PASOS",
        help="Guardar checkpoint cada N pasos.",
    )
    parser.add_argument(
        "--log-dir",
        default="logs",
        metavar="DIR",
        help="Directorio para los logs de TensorBoard.",
    )
    parser.add_argument(
        "--model-dir",
        default="models",
        metavar="DIR",
        help="Directorio raíz donde guardar los checkpoints del modelo.",
    )
    parser.add_argument(
        "--gamepad",
        default="xbox",
        choices=["xbox", "ds4"],
        help="Tipo de mando virtual: 'xbox' (defecto) o 'ds4' (PS4).",
    )
    parser.add_argument(
        "--frame-skip",
        type=int,
        default=1,
        metavar="N",
        help="Ejecutar N frames de juego por cada paso del agente (defecto: 1). "
             "Valores útiles: 2-4. Cada paso cubre más tiempo de juego → "
             "señal de recompensa más clara y decisiones menos frecuentes.",
    )
    parser.add_argument(
        "--warmup-steps",
        type=int,
        default=0,
        metavar="N",
        help="Frames de gas automático al inicio de cada episodio para arrancar el coche "
             "antes de entregar el control al agente. Recomendado: 60-80 (~2-3 seg a 25fps).",
    )
    parser.add_argument(
        "--curriculum",
        action="store_true",
        default=False,
        help="Activa recompensa simplificada (solo gas + velocidad, sin CTE ni penalizaciones). "
             "Úsalo para que el agente aprenda a moverse primero. Desactivar una vez el coche se mueve.",
    )
    parser.add_argument(
        "--basics",
        action="store_true",
        default=False,
        help="Modo básicos: línea + velocidad objetivo + girar + acciones suaves. "
             "Recomendado con --speed-target-kmh 20. Ignora --curriculum si ambos están activos.",
    )
    parser.add_argument(
        "--car",
        default="formula_rookie",
        metavar="COCHE",
        help=(
            "Override manual del nombre del coche. "
            "Por defecto: 'formula_rookie'. Vaciar para auto-detectar desde UDP."
        ),
    )
    parser.add_argument(
        "--track",
        default="sugo",
        metavar="PISTA",
        help=(
            "Override manual del nombre de la pista. "
            "Por defecto: 'sugo'. Vaciar para auto-detectar desde UDP."
        ),
    )
    parser.add_argument(
        "--base-model",
        default=None,
        metavar="RUTA_MODELO",
        help=(
            "Modelo base para transfer learning. Carga los pesos de conducción general "
            "y empieza entrenamiento nuevo para el coche+pista especificados. "
            "No usar junto con --model."
        ),
    )
    parser.add_argument(
        "--obs-schema",
        choices=("legacy_19", "universal_v1"),
        default="legacy_19",
        help=(
            "Observación del entorno. `universal_v1` (17 dim) lleva el CTE con signo y es la "
            "misma que usa el BC actual; los modelos PPO guardados con otro esquema no son "
            "compatibles."
        ),
    )
    parser.add_argument(
        "--speed-target-kmh",
        type=float,
        default=0.0,
        metavar="KMH",
        help=(
            "Velocidad objetivo inicial (km/h). El agente recibe penalización si se aleja "
            "de ese valor en ambas direcciones. Sube +5 km/h cada 10k pasos si el promedio "
            "está dentro de ±10 km/h del objetivo. 0 = desactivado (por defecto)."
        ),
    )
    parser.add_argument(
        "--laps-per-episode", type=int, default=1, metavar="N",
        help="Vueltas por episodio. Con 2 el tiempo registrado es el de la segunda (lanzada), "
             "comparable con una vuelta de referencia; con 1 incluye el arranque desde parado.",
    )
    parser.add_argument(
        "--no-speed-ramp", action="store_true",
        help="La velocidad objetivo no sube sola (+5 km/h por ventana): queda fija en "
             "--speed-target-kmh. Útil para comparar tiradas.",
    )
    parser.add_argument(
        "--steer-comp", action="store_true",
        help="Compensa la curva de respuesta del volante del juego (steering_curve.py); "
             "igual que en learn_driver. Mantenerla igual que al grabar el BC.",
    )
    parser.add_argument(
        "--bc-std",
        type=float,
        default=DEFAULT_BC_STD,
        metavar="STD",
        help="Desviación inicial de la política cuando se parte de un modelo BC/base "
             "(PPO nace con 1,0 y destruiría lo imitado).",
    )
    parser.add_argument(
        "--anchor-lr", type=float, default=ANCHOR_LR, metavar="LR",
        help="Tasa de aprendizaje al partir de un modelo BC/base (más baja que la normal).",
    )
    parser.add_argument(
        "--anchor-epochs", type=int, default=ANCHOR_EPOCHS, metavar="N",
        help="Épocas por actualización al partir de un modelo BC/base.",
    )
    parser.add_argument(
        "--anchor-target-kl", type=float, default=ANCHOR_TARGET_KL, metavar="KL",
        help="Corta las épocas de una actualización si la KL aproximada supera este valor.",
    )
    parser.add_argument(
        "--bc-pull", type=float, default=BC_PULL, metavar="A",
        help="Tras cada actualización devuelve esta fracción (0-1) del desvío del actor hacia el BC "
             "inicial: evita que la conducción se degrade poco a poco. 0 = desactivado.",
    )
    parser.add_argument(
        "--critic-warmup-steps",
        type=int,
        default=CRITIC_WARMUP_STEPS,
        metavar="N",
        help="Pasos con el actor congelado al partir de un modelo BC/base, para que el "
             "crítico aprenda a valorar antes de tocar la política. 0 = desactivado.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        metavar="N",
        help="Semilla para reproducibilidad (NumPy + PyTorch).",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        default=False,
        help="Nueva política PPO: no cargar checkpoints, _final ni pretrained.zip.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entrenamiento
# ---------------------------------------------------------------------------

class MetricsAccumulator:
    """Acumula métricas por rollout para metricas.csv (sin dependencias de SB3)."""

    MAX_SPEED_MS = 97.0
    TERM_REASONS = ("stuck", "pit_box", "wrong_way", "no_progress", "lap_done")

    def __init__(self, track_length: float = 3567.0):
        self.track_length = track_length
        self.reset()

    def reset(self) -> None:
        self.speed_sum = 0.0
        self.speed_count = 0
        self.max_speed_kmh = 0.0
        self.steer_sum = self.throttle_sum = self.brake_sum = 0.0
        self.action_count = 0
        self.cte_sum = 0.0
        self.cte_count = 0
        self.ep_count = 0
        self.term_counts = {r: 0 for r in self.TERM_REASONS}
        self.n_timelimit = 0
        self.dist_total_m = 0.0
        self.dist_prev_prog = 0.0

    def add_step(self, new_obs, actions, infos, dones) -> None:
        if new_obs is not None:
            speed_kmh = float(new_obs[0][0]) * self.MAX_SPEED_MS * 3.6  # obs[0] = speed_norm
            self.speed_sum += speed_kmh
            self.speed_count += 1
            self.max_speed_kmh = max(self.max_speed_kmh, speed_kmh)
        if actions is not None:
            self.steer_sum += float(actions[0][2])
            self.throttle_sum += float(actions[0][0])
            self.brake_sum += float(actions[0][1])
            self.action_count += 1
        if infos is not None:
            cte = infos[0].get('cte', None)
            if cte is not None:
                self.cte_sum += cte
                self.cte_count += 1
            if dones is not None and dones[0]:
                tr = infos[0].get('term_reason', '?')
                self.ep_count += 1
                if tr in self.term_counts:
                    self.term_counts[tr] += 1
                else:
                    self.n_timelimit += 1
        prog = None
        lap_distance = infos[0].get('lap_distance') if infos else None
        if lap_distance is not None and self.track_length > 0:
            prog = lap_distance / self.track_length   # válido con cualquier observación
        elif new_obs is not None and len(new_obs[0]) > 18:
            prog = float(new_obs[0][18])              # legacy_19: obs[18] = progreso 0-1
        if prog is not None:
            delta = prog - self.dist_prev_prog
            if delta < -0.5:   # wrap-around: fin de vuelta
                delta += 1.0
            if delta > 0:
                self.dist_total_m += delta * self.track_length
            self.dist_prev_prog = prog

    @staticmethod
    def _mean(total: float, n: int, digits: int) -> float:
        return round(total / n, digits) if n > 0 else 0.0

    def _pct(self, n: int) -> float:
        return round(100 * n / self.ep_count, 1) if self.ep_count > 0 else 0.0

    def csv_values(self) -> list:
        """avg_speed, max_speed, avg_cte, steering, throttle, brake, dist_km, ep_count, pct_*."""
        return [
            self._mean(self.speed_sum, self.speed_count, 1),
            round(self.max_speed_kmh, 1),
            self._mean(self.cte_sum, self.cte_count, 3),
            self._mean(self.steer_sum, self.action_count, 4),
            self._mean(self.throttle_sum, self.action_count, 4),
            self._mean(self.brake_sum, self.action_count, 4),
            round(self.dist_total_m / 1000.0, 3),
            self.ep_count,
            *(self._pct(self.term_counts[r]) for r in self.TERM_REASONS),
            self._pct(self.n_timelimit),
        ]


def _load_or_create_model(args, PPO, env, tb_log, model_dir, name_prefix, subdir):
    """Devuelve (model, reset_num_timesteps) según --model / --base-model / --fresh / auto."""
    # Prioridad:
    #   1. --model → continuar ese checkpoint
    #   2. --base-model → transfer learning
    #   3. --fresh → política nueva (sin auto-carga)
    #   4. Auto: max steps del combo → _final → base → pretrained → cero
    if args.model:
        print(f"[main] Cargando modelo indicado: {args.model}")
        model = PPO.load(args.model, env=env, tensorboard_log=tb_log,
                         custom_objects={'learning_rate': 1e-4, 'clip_range': 0.15})
        model.ent_coef = 0.007
        model.vf_coef  = 1.0
        _reset_log_std(model, target_std=0.85)
        reset_num_timesteps = False

    elif args.base_model:
        print(f"[main] Transfer learning desde: {args.base_model}")
        model = PPO.load(args.base_model, env=env, tensorboard_log=tb_log,
                         custom_objects={'learning_rate': 1e-4, 'clip_range': 0.2})
        model.ent_coef = 0.01
        _anchor_from_bc(model, args)
        reset_num_timesteps = True

    else:
        if args.fresh:
            print(f"[main] Desde cero (--fresh): nueva política PPO para {subdir}")
            model = _create_ppo_from_scratch(env, tb_log)
            reset_num_timesteps = True
        else:
            auto_model = _find_best_model(model_dir, name_prefix, args.model_dir, subdir)
            if auto_model and auto_model["mode"] == "continue":
                print(f"[main] Continuando desde: {auto_model['path']}")
                model = PPO.load(auto_model["path"], env=env, tensorboard_log=tb_log,
                                 custom_objects={'learning_rate': 1e-4, 'clip_range': 0.15})
                model.ent_coef  = 0.007
                model.vf_coef   = 1.0
                _reset_log_std(model, target_std=0.85)
                reset_num_timesteps = False
            elif auto_model and auto_model["mode"] == "transfer":
                print(f"[main] Transfer learning desde modelo base: {auto_model['path']}")
                print(f"[main] → Combo: {subdir}  (contador de pasos a cero)")
                model = PPO.load(auto_model["path"], env=env, tensorboard_log=tb_log,
                                 custom_objects={'learning_rate': 1e-4, 'clip_range': 0.2})
                model.vf_coef = 1.5
                _anchor_from_bc(model, args)
                reset_num_timesteps = True
            else:
                pretrained_path = os.path.join(args.model_dir, "pretrained.zip")
                if os.path.isfile(pretrained_path):
                    print(f"[main] Cargando pretrained.zip como base: {pretrained_path}")
                    model = PPO.load(pretrained_path[:-4], env=env, tensorboard_log=tb_log)
                    model.ent_coef  = 0.01
                    model.vf_coef   = 1.5
                    _anchor_from_bc(model, args)
                    reset_num_timesteps = True
                else:
                    print(f"[main] Creando modelo PPO desde cero para: {subdir}")
                    model = _create_ppo_from_scratch(env, tb_log)
                    reset_num_timesteps = True
    return model, reset_num_timesteps


def train(args: argparse.Namespace) -> None:
    # Importaciones pesadas después del argparse para que --help sea rápido
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import CheckpointCallback
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
    from environment import PCARS2Env
    import numpy as np

    # ---- Fijar seeds para reproducibilidad ----
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    print(f"[main] Seed: {args.seed}")

    # TensorBoard es opcional — si no está instalado, se deshabilitan los logs
    try:
        import tensorboard  # type: ignore[import]  # noqa: F401
        tb_log = args.log_dir
        print(f"[main] TensorBoard disponible → logs en: {args.log_dir}/")
    except ImportError:
        tb_log = None
        print("[main] TensorBoard no instalado — entrenamiento sin logs TB.")

    # ---- Validaciones previas ----
    if not os.path.isfile(args.reference):
        print(f"[Error] Archivo de referencia no encontrado: {args.reference}")
        sys.exit(1)

    if args.model and args.base_model:
        print("[Error] --model y --base-model son mutuamente excluyentes.")
        sys.exit(1)

    # ---- Crear entorno ----
    print(f"[main] Creando entorno PCARS2Env (gamepad={args.gamepad}, frame_skip={args.frame_skip}, "
          f"warmup={args.warmup_steps}, basics={args.basics}, curriculum={args.curriculum}, "
          f"speed_target={args.speed_target_kmh:.0f} km/h)...")
    raw_env   = PCARS2Env(
        reference_path=args.reference,
        gamepad_mode=args.gamepad,
        frame_skip=args.frame_skip,
        warmup_steps=args.warmup_steps,
        curriculum=args.curriculum,
        basics=args.basics,
        speed_target_kmh=args.speed_target_kmh,
        obs_schema=args.obs_schema,
        steer_comp=args.steer_comp,
        speed_ramp=not args.no_speed_ramp,
        laps_per_episode=args.laps_per_episode,
    )
    _mon_env  = Monitor(raw_env)
    _vec_env  = DummyVecEnv([lambda: _mon_env])   # SB3 requiere VecEnv para VecNormalize
    # VecNormalize: normaliza recompensas a varianza ~1 (las obs ya están en [-1,1])
    # → crítica clave para que el crítico pueda aprender (explained_variance ≠ 0)
    # Las stats se guardan en {model_dir}/vecnormalize.pkl

    # ---- Determinar combo coche+pista ----
    if args.car or args.track:
        # Override manual del usuario
        parts = [p for p in [args.car, args.track] if p]
        subdir = "__".join(parts)
        print(f"[main] Combo manual: {subdir}")
    else:
        # Auto-detección desde telemetría UDP
        detected = raw_env.wait_for_combo(timeout=90.0)
        subdir = detected if detected else "base"

    model_dir = os.path.join(args.model_dir, subdir)
    log_dir   = os.path.join(args.log_dir,   subdir)
    name_prefix = f"pcars2_{subdir}"

    os.makedirs(log_dir,   exist_ok=True)
    os.makedirs(model_dir, exist_ok=True)

    # La consola también se guarda: las líneas [Env] / [Ep n] explican cómo termina cada episodio
    from console_log import start_console_log
    start_console_log(os.path.join(log_dir, 'consola.log'))   # se cierra al salir; cada línea se vuelca al instante

    tb_log = log_dir if tb_log else None

    # ---- Crear/cargar VecNormalize (ahora que sabemos model_dir) ----
    vec_norm_path = os.path.join(model_dir, "vecnormalize.pkl")
    if os.path.isfile(vec_norm_path):
        env = VecNormalize.load(vec_norm_path, _vec_env)
        env.training    = True
        env.norm_reward = True
        print(f"[main] VecNormalize stats cargadas desde: {vec_norm_path}")
    else:
        env = VecNormalize(
            _vec_env,
            norm_obs    = False,   # obs ya normalizadas en environment.py
            norm_reward = True,    # normalizar recompensas → crítico puede aprender
            clip_reward = 5.0,     # reducido de 10 para acotar el rango del crítico
            gamma       = 0.99,
        )
        print("[main] VecNormalize creado (stats desde cero).")

    model, reset_num_timesteps = _load_or_create_model(
        args, PPO, env, tb_log, model_dir, name_prefix, subdir,
    )

    # ---- Callback: CSV logger ----
    from stable_baselines3.common.callbacks import BaseCallback

    class CSVLoggerCallback(BaseCallback):
        """Guarda métricas PPO a un CSV tras cada iteración."""
        def __init__(self, csv_path: str, track_length: float = 3567.0, raw_env=None):
            super().__init__()
            self._csv_path = csv_path
            self._raw_env = raw_env
            self._acc = MetricsAccumulator(track_length)
            self._file = None
            self._writer = None
            self._prev_steps = 0
            self._prev_time = None

        def _on_training_start(self):
            self._prev_steps = self.num_timesteps
            self._prev_time  = _time.monotonic()
            os.makedirs(os.path.dirname(self._csv_path), exist_ok=True)
            self._file = open(self._csv_path, 'w', newline='', encoding='utf-8')
            self._writer = csv.writer(self._file)
            self._writer.writerow([
                'timestamp', 'total_timesteps', 'iterations',
                'ep_rew_mean', 'ep_len_mean', 'fps',
                'explained_variance', 'value_loss', 'policy_gradient_loss',
                'entropy_loss', 'std', 'approx_kl', 'clip_fraction',
                'learning_rate', 'n_updates',
                'avg_speed_kmh', 'max_speed_kmh', 'avg_cte',
                'avg_steering', 'avg_throttle', 'avg_brake', 'dist_km',
                'ep_count', 'pct_stuck', 'pct_pit_box', 'pct_wrong_way', 'pct_no_progress', 'pct_lap_done', 'pct_timelimit',
                'udp_physics', 'pct_udp_timeout', 'pct_udp_backlog',
            ])
            if self._file:
                self._file.flush()

        def _on_step(self) -> bool:
            self._acc.add_step(
                self.locals.get('new_obs'),
                self.locals.get('actions'),
                self.locals.get('infos'),
                self.locals.get('dones'),
            )
            return True

        def _on_rollout_end(self):
            if self._writer is None:
                return
            # Guardar stats de VecNormalize en cada rollout
            if isinstance(self.training_env, VecNormalize):
                self.training_env.save(vec_norm_path)
            log = self.logger.name_to_value
            # ep_rew_mean/ep_len_mean se logean DESPUÉS de _on_rollout_end en SB3;
            # leerlos directamente del buffer del Monitor.
            ep_buf = self.model.ep_info_buffer
            ep_rew_mean = sum(ep['r'] for ep in ep_buf) / len(ep_buf) if ep_buf else 0.0
            ep_len_mean = sum(ep['l'] for ep in ep_buf) / len(ep_buf) if ep_buf else 0.0
            # FPS calculado manualmente: time/fps aún no está en el logger en _on_rollout_end
            now = _time.monotonic()
            if self._prev_time is not None and (now - self._prev_time) > 0:
                fps = (self.num_timesteps - self._prev_steps) / (now - self._prev_time)
            else:
                fps = 0.0
            self._prev_steps = self.num_timesteps
            self._prev_time  = now
            udp = {}
            if self._raw_env is not None and hasattr(self._raw_env, "udp_stats_snapshot"):
                udp = self._raw_env.udp_stats_snapshot()
            udp_physics = int(udp.get("physics_frames", 0))
            udp_timeouts = int(udp.get("timeouts", 0))
            udp_backlog = int(udp.get("backlog_dropped", 0))
            udp_attempts = udp_physics + udp_timeouts
            pct_udp_timeout = (
                round(100.0 * udp_timeouts / udp_attempts, 1) if udp_attempts > 0 else 0.0
            )
            backlog_total = udp_physics + udp_backlog
            pct_udp_backlog = (
                round(100.0 * udp_backlog / backlog_total, 1) if backlog_total > 0 else 0.0
            )
            if self._raw_env is not None and hasattr(self._raw_env, "udp_stats_reset"):
                self._raw_env.udp_stats_reset()
            self._writer.writerow([
                _time.strftime('%H:%M:%S'),
                self.num_timesteps,
                self.n_calls,
                round(ep_rew_mean, 2),
                round(ep_len_mean, 1),
                round(fps, 0),
                round(log.get('train/explained_variance', 0), 4),
                round(log.get('train/value_loss', 0), 4),
                round(log.get('train/policy_gradient_loss', 0), 6),
                round(log.get('train/entropy_loss', 0), 4),
                round(log.get('train/std', 0), 4),
                round(log.get('train/approx_kl', 0), 6),
                round(log.get('train/clip_fraction', 0), 4),
                round(log.get('train/learning_rate', 0), 6),
                int(log.get('train/n_updates', 0)),
                *self._acc.csv_values(),
                udp_physics,
                pct_udp_timeout,
                pct_udp_backlog,
            ])
            self._acc.reset()
            if self._file:
                self._file.flush()

        def _on_training_end(self):
            if self._file:
                self._file.close()

    csv_path = os.path.join(log_dir, 'metricas.csv')
    csv_cb   = CSVLoggerCallback(
        csv_path,
        track_length=raw_env._ref.track_length,
        raw_env=raw_env,
    )
    print(f"[main] Métricas CSV → {csv_path}")

    # ---- Callback: guardar checkpoints ----
    checkpoint_cb = CheckpointCallback(
        save_freq          = args.save_freq,
        save_path          = model_dir,
        name_prefix        = name_prefix,
        save_replay_buffer = False,
        verbose            = 1,
    )

    # ---- Entrenamiento ----
    tb_info = f"tensorboard --logdir {log_dir}" if tb_log else "(TensorBoard no disponible)"
    print(
        f"\n[main] Iniciando entrenamiento\n"
        f"       Combo      : {subdir}\n"
        f"       Referencia : {args.reference}\n"
        f"       Timesteps  : {args.timesteps:,}\n"
        f"       Checkpoints: cada {args.save_freq:,} pasos → {model_dir}/\n"
        f"       TensorBoard: {tb_info}\n"
    )

    from episode_log import EpisodeLogCallback
    from ppo_anchor import HoldBrakeDuringUpdateCallback
    episodes_path = os.path.join(log_dir, 'episodios.csv')
    print(f"[main] Episodios CSV -> {episodes_path}")
    callbacks = [
        HoldBrakeDuringUpdateCallback(raw_env.hold_brake, raw_env.resume_after_update),
        checkpoint_cb, csv_cb, EpisodeLogCallback(episodes_path),
    ]
    if getattr(args, "anchored_to_bc", False) and args.critic_warmup_steps > 0:
        from ppo_anchor import FreezeActorCallback
        callbacks.insert(1, FreezeActorCallback(args.critic_warmup_steps))
    if getattr(args, "anchored_to_bc", False) and args.bc_pull > 0:
        from ppo_anchor import PullToBCCallback
        callbacks.append(PullToBCCallback(args.bc_pull))

    try:
        model.learn(
            total_timesteps      = args.timesteps,
            callback             = callbacks,
            reset_num_timesteps  = reset_num_timesteps,
            progress_bar         = False,
        )
    except KeyboardInterrupt:
        print("\n[main] Entrenamiento interrumpido por el usuario.")
    finally:
        # Guardar modelo final aunque se interrumpa
        final_path = os.path.join(model_dir, f"pcars2_{subdir}_final")
        model.save(final_path)
        print(f"[main] Modelo guardado en: {final_path}.zip")
        # Guardar stats de VecNormalize (necesarias para cargar el modelo correctamente)
        if isinstance(env, VecNormalize):
            env.save(vec_norm_path)
            print(f"[main] VecNormalize stats guardadas en: {vec_norm_path}")
        env.close()


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = parse_args()
    train(args)
