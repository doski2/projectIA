"""
pretrain.py
Pre-entrenamiento por imitación (Behavioral Cloning) para PCARS2-AI.

Lee el JSON de referencia grabada y entrena la red neuronal del agente
por imitación supervisada, SIN necesidad de abrir el juego.

El agente aprende a imitar al piloto de referencia punto a punto usando
las MISMAS 19 observaciones que environment.py, incluyendo curvatura,
lookahead de velocidad, orientación y referencia de freno/acelerador.

Data augmentation (activado por defecto):
  Se añade ruido gaussiano a CTE y heading_err para reducir el distribution
  shift entre BC (piloto en la línea, CTE=0) y la inferencia real (CTE≠0).
  Desactivar con --no-augment si se prefiere el dataset limpio.

Uso:
    python pretrain.py --reference src/refs/reference_1778013812.json
    python pretrain.py --reference src/refs/reference_1778013812.json --epochs 100
    python pretrain.py --reference src/refs/reference_1778013812.json --output models/pretrained
    python pretrain.py --reference src/refs/reference_1778013812.json --no-augment
"""

import argparse
import math
import os
import sys

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from obs_builder import (
    MAX_ANGULAR_VEL,
    MAX_CURVATURE,
    MAX_LAT_ACCEL,
    MAX_LONG_ACCEL,
    MAX_SPEED_MS,
    MAX_TYRE_RPS,
    TYRE_RADIUS,
    encode_action,
)

MAX_GEARS = 6   # Formula Rookie tiene 6 marchas


# ---------------------------------------------------------------------------
# Construcción del dataset desde el JSON de referencia
# ---------------------------------------------------------------------------

def build_dataset(ref_path: str, augment: bool = True) -> tuple:
    """
    Lee el JSON de referencia y construye arrays (observaciones, acciones).

    Las observaciones tienen exactamente 19 floats, igual que environment._build_obs().
    Los valores no disponibles en el JSON estático usan el valor neutral correcto.

    Si augment=True, añade ruido gaussiano a CTE y heading_err para reducir el
    distribution shift entre BC (CTE=0 siempre) y la inferencia real (CTE≠0).

    Si el JSON contiene 'all_laps' (multi-vuelta), itera TODAS las vueltas para
    obtener un dataset más grande y con más variabilidad → mejor BC.
    """
    import json as _json  # noqa: F401 – reservado para uso futuro
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from reference_recorder import ReferenceLine, ReferencePoint

    ref = ReferenceLine.load(ref_path)

    # Construir lista de vueltas: todas si hay all_laps, solo la mejor si no.
    if ref.all_laps:
        all_lap_points = [
            [ReferencePoint.from_dict(p) for p in lap["points"]]
            for lap in ref.all_laps
        ]
        lap_times = [lap["lap_time"] for lap in ref.all_laps]
        total_pts  = sum(len(pts) for pts in all_lap_points)
        avg_t      = sum(lap_times) / len(lap_times)
        mins_b     = int(ref.lap_time // 60)
        secs_b     = ref.lap_time % 60
        print(
            f"[BC] Referencia: {ref.track_name}\n"
            f"     {len(ref.all_laps)} vueltas | {total_pts} puntos totales | "
            f"mejor {mins_b}:{secs_b:06.3f}s | media {avg_t:.3f}s | {ref.track_length:.0f}m"
        )
    else:
        all_lap_points = [ref.points]
        print(
            f"[BC] Referencia: {ref.track_name}\n"
            f"     {len(ref.points)} puntos | {ref.lap_time:.3f}s | {ref.track_length:.0f}m"
        )

    obs_list = []
    act_list = []

    for lap_points in all_lap_points:
      for p in lap_points:
        d        = p.lap_distance
        speed    = p.speed
        throttle = p.throttle / 255.0   # [0,1]
        brake    = p.brake    / 255.0   # [0,1]
        steering = float(p.steering) / 128.0
        steering = max(-1.0, min(1.0, steering))
        gear     = p.gear                        # entero (0=neutral,1=1ª…)

        # ── 0 · Velocidad normalizada ─────────────────────────────────
        speed_norm = float(np.clip(speed / MAX_SPEED_MS, 0.0, 1.0))

        # ── 1 · CTE — con data augmentation para reducir distribution shift ──
        # En la referencia, CTE=0 (piloto EN la línea). En inferencia real CTE≠0.
        # Añadimos ruido gaussiano para que el modelo aprenda a reaccionar a desviaciones.
        if augment:
            cte_noise = np.random.normal(0.0, 0.15)  # std ~1.2m normalizado a MAX_CTE=8
            cte_norm = float(np.clip(cte_noise, 0.0, 1.0))
        else:
            cte_norm = 0.0

        # ── 2 · Delta velocidad = 0 (velocidad igual a referencia) ───
        delta_norm = 0.0

        # ── 3-6 · Dinámicas del coche desde telemetría grabada ────────
        lvel = p.local_velocity    # (vx, vy, vz) en ejes del coche
        avel = p.angular_velocity  # (ax, ay, az)
        lacc = p.local_accel       # (long, vert, lat)

        vx_l = lvel[0]
        vz_l = lvel[2]
        slip = math.atan2(vz_l, max(abs(vx_l), 0.1))
        slip_norm = float(np.clip(slip / math.pi, -1.0, 1.0))

        yaw_norm  = float(np.clip(avel[1] / MAX_ANGULAR_VEL, -1.0, 1.0))
        lat_norm  = float(np.clip(lvel[2] / (MAX_LAT_ACCEL * 9.81), -1.0, 1.0))
        long_norm = float(np.clip(lacc[0] / MAX_LONG_ACCEL, -1.0, 1.0))

        # ── 7 · RPM desde telemetría grabada ─────────────────────────
        rpm_norm = float(np.clip(p.rpm / max(p.max_rpm, 1), 0.0, 1.0))

        # ── 8 · Marcha normalizada ────────────────────────────────────
        gear_norm = float(np.clip(gear / MAX_GEARS, 0.0, 1.0))

        # ── 9 · Heading error — con augmentation ─────────────────────
        if augment:
            heading_noise = np.random.normal(0.0, 0.1)  # std ~18° normalizado a pi
            heading_err_norm = float(np.clip(heading_noise, -1.0, 1.0))
        else:
            heading_err_norm = 0.0

        # ── 12 · Curvatura calculada desde las posiciones de referencia
        curv = ref.curvature(d)
        curv_norm = float(np.clip(curv / MAX_CURVATURE, -1.0, 1.0))

        # ── 13-14 · Lookahead de velocidad a +50m y +100m ─────────────
        spd_lk50  = float(np.clip(ref.speed_lookahead(d,  50.0) / MAX_SPEED_MS, 0.0, 1.0))
        spd_lk100 = float(np.clip(ref.speed_lookahead(d, 100.0) / MAX_SPEED_MS, 0.0, 1.0))

        # ── 15-16 · Throttle y brake de referencia ────────────────────
        ref_thr = throttle
        ref_brk = brake

        # ── 17-19 · Wheelspin/lockup desde tyre_rps grabados ─────────
        expected_rps = speed / (2.0 * math.pi * TYRE_RADIUS)
        rear_rps_avg  = (p.tyre_rps[2] + p.tyre_rps[3]) / 2.0
        front_rps_avg = (p.tyre_rps[0] + p.tyre_rps[1]) / 2.0
        wheelspin_norm    = float(np.clip((rear_rps_avg  - expected_rps) / MAX_TYRE_RPS, -1.0, 1.0))
        lockup_norm       = float(np.clip((expected_rps  - front_rps_avg) / MAX_TYRE_RPS, -1.0, 1.0))
        throttle_cur_norm = throttle

        # ── 18 · Progreso en la vuelta ────────────────────────────────
        progress = float(np.clip(d / ref.track_length, 0.0, 1.0))

        obs = np.array([
            speed_norm,        # 0
            cte_norm,          # 1
            delta_norm,        # 2
            slip_norm,         # 3
            yaw_norm,          # 4
            lat_norm,          # 5
            long_norm,         # 6
            rpm_norm,          # 7
            gear_norm,         # 8
            heading_err_norm,  # 9
            curv_norm,         # 10
            spd_lk50,          # 11
            spd_lk100,         # 12
            ref_thr,           # 13
            ref_brk,           # 14
            wheelspin_norm,    # 15
            lockup_norm,       # 16
            throttle_cur_norm, # 17
            progress,          # 18
        ], dtype=np.float32)

        act = encode_action(throttle, brake, steering)

        obs_list.append(obs)
        act_list.append(act)

    obs_array = np.array(obs_list, dtype=np.float32)
    act_array = np.array(act_list, dtype=np.float32)

    print(f"[BC] Dataset: {len(obs_array)} muestras × 19 observaciones")
    return obs_array, act_array


def build_dataset_from_jsonl(
    dataset_path: str,
    origin: str | None = None,
    min_quality: float = 0.0,
    min_confidence: float = 0.0,
) -> tuple:
    """Carga demostraciones TEACHER/DEMO/MIXED desde JSONL."""
    from dataset_recorder import load_dataset

    obs_array, act_array, meta = load_dataset(
        dataset_path,
        origin=origin,
        min_quality=min_quality,
        min_confidence=min_confidence,
    )
    if len(obs_array) == 0:
        raise ValueError(f"Dataset vacío: {dataset_path}")

    origins = {m.get("origin", "?") for m in meta}
    print(
        f"[BC] Dataset JSONL: {dataset_path}\n"
        f"     {len(obs_array)} muestras | orígenes: {', '.join(sorted(origins))}"
    )
    return obs_array, act_array


# ---------------------------------------------------------------------------
# Entrenamiento por imitación
# ---------------------------------------------------------------------------

def pretrain(
    obs_array:     np.ndarray,
    act_array:     np.ndarray,
    base_model:    str | None,
    epochs:        int,
    batch_size:    int,
    learning_rate: float,
    output_path:   str,
):
    from stable_baselines3 import PPO
    from obs_spaces import DummyEnv, LEGACY_OBS_SCHEMA
    from ppo_defaults import PPO_NET_ARCH

    # ---- Entorno ficticio con los mismos espacios que PCARS2Env ----
    env = DummyEnv(LEGACY_OBS_SCHEMA)

    # ---- Crear o cargar modelo PPO (misma arquitectura que main.py) ----
    model = None
    base_path = None
    if base_model:
        base_path = base_model if not base_model.endswith(".zip") else base_model[:-4]
        if os.path.isfile(base_path + ".zip"):
            print(f"[BC] Cargando modelo base: {base_path}.zip")
            model = PPO.load(base_path, env=env)

    if model is None:
        if base_path is not None:
            print(f"[BC] Modelo base no encontrado ({base_path}.zip) — creando desde cero.")
        else:
            print("[BC] Creando modelo PPO desde cero (net_arch=[256,256,128])...")
        model = PPO(
            policy        = "MlpPolicy",
            policy_kwargs = dict(net_arch=PPO_NET_ARCH),
            env           = env,
            learning_rate = learning_rate,
            verbose       = 0,
        )

    # ---- Extraer la red del actor ----
    policy = model.policy
    device = policy.device
    print(f"[BC] Dispositivo: {device}")

    # ---- DataLoader ----
    obs_t   = torch.tensor(obs_array, dtype=torch.float32)
    act_t   = torch.tensor(act_array, dtype=torch.float32)
    dataset = TensorDataset(obs_t, act_t)
    loader  = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    # ---- Optimizador: solo actor (policy_net + action_net) ----
    actor_params = (
        list(policy.mlp_extractor.policy_net.parameters())
        + list(policy.action_net.parameters())
    )
    optimizer = torch.optim.Adam(actor_params, lr=learning_rate)
    loss_fn   = nn.MSELoss()

    # ---- Loop de Behavioral Cloning (con early stopping) ----
    print(f"[BC] Entrenando {epochs} épocas × {len(dataset)} muestras...")
    best_loss = float("inf")
    patience = 15          # épocas sin mejora antes de parar
    patience_counter = 0
    for epoch in range(1, epochs + 1):
        total_loss = 0.0
        for batch in loader:
            obs_batch, act_batch = (t.to(device) for t in batch)
            pred, _, _ = policy.forward(obs_batch, deterministic=True)
            loss = loss_fn(pred, act_batch)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        avg_loss = total_loss / len(loader)
        if avg_loss < best_loss:
            best_loss = avg_loss
            patience_counter = 0
        else:
            patience_counter += 1
        if epoch % 10 == 0 or epoch == 1:
            print(f"  Época {epoch:>4}/{epochs}  |  loss={avg_loss:.6f}  |  mejor={best_loss:.6f}")
        if patience_counter >= patience:
            print(f"  [BC] Early stopping en época {epoch} (sin mejora en {patience} épocas)")
            break

    # ---- Anclar la std: PPO nace con 1,0 y destruiría lo imitado ----
    from ppo_anchor import anchor_log_std
    anchor_log_std(model)

    # ---- Guardar modelo ----
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    model.save(output_path)
    print(f"\n[BC] Modelo guardado: {output_path}.zip  (loss final={best_loss:.6f})")
    print(f"     Para entrenar:  python src/main.py -r <referencia> --base-model {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PCARS2-AI — Pre-entrenamiento por Behavioral Cloning (19 obs)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--reference", "-r", default=None, metavar="RUTA_JSON",
                        help="Ruta al JSON de referencia grabada.")
    parser.add_argument("--dataset", "-d", default=None, metavar="RUTA_JSONL",
                        help="Ruta al dataset JSONL (TEACHER/DEMO/MIXED).")
    parser.add_argument("--origin", default=None,
                        help="Filtrar dataset por origen (TEACHER, DEMO, MIXED).")
    parser.add_argument("--min-quality", type=float, default=0.5)
    parser.add_argument("--min-confidence", type=float, default=0.5)
    parser.add_argument("--base", "-b", default=None, metavar="RUTA_MODELO",
                        help="Modelo base existente para afinar (sin .zip).")
    parser.add_argument("--output", "-o", default="models/pretrained", metavar="RUTA_SALIDA",
                        help="Ruta de salida del modelo pre-entrenado (sin .zip).")
    parser.add_argument("--epochs", "-e", type=int, default=100, metavar="N",
                        help="Épocas de entrenamiento BC.")
    parser.add_argument("--batch-size", type=int, default=256, metavar="N")
    parser.add_argument("--lr", type=float, default=1e-3, metavar="FLOAT",
                        help="Tasa de aprendizaje.")
    parser.add_argument("--seed", type=int, default=42, metavar="N",
                        help="Semilla para reproducibilidad.")
    parser.add_argument("--no-augment", action="store_true", default=False,
                        help="Desactivar data augmentation (ruido en CTE/heading).")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if not args.reference and not args.dataset:
        print("[Error] Indica --reference o --dataset.")
        sys.exit(1)
    if args.reference and not os.path.isfile(args.reference):
        print(f"[Error] Archivo de referencia no encontrado: {args.reference}")
        sys.exit(1)
    if args.dataset and not os.path.isfile(args.dataset):
        print(f"[Error] Dataset no encontrado: {args.dataset}")
        sys.exit(1)

    # Fijar seeds para reproducibilidad
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    print(f"[BC] Seed: {args.seed}")

    if args.dataset:
        obs_array, act_array = build_dataset_from_jsonl(
            args.dataset,
            origin=args.origin,
            min_quality=args.min_quality,
            min_confidence=args.min_confidence,
        )
    else:
        obs_array, act_array = build_dataset(args.reference, augment=not args.no_augment)

    pretrain(
        obs_array     = obs_array,
        act_array     = act_array,
        base_model    = args.base,
        epochs        = args.epochs,
        batch_size    = args.batch_size,
        learning_rate = args.lr,
        output_path   = args.output,
    )
