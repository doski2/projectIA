"""
ppo_bootstrap.py
Destila el BC universal (obs + intención -> acción) a un modelo PPO de stable-baselines3 que
solo ve la observación `universal_v1`, para que PPO parta de un conductor competente.

    python src/ppo_bootstrap.py --bc models/universal_bc.pt --out models/ppo_universal_base

Los objetivos son las salidas del propio BC con la intención real del profesor (lo que conduce
en Hybrid), no las etiquetas crudas. El crítico queda aleatorio: `main.py` congela el actor unos
pasos (`--critic-warmup-steps`) y ancla la desviación (`--bc-std`) al cargarlo con --base-model.
"""

from __future__ import annotations

import argparse
import os

import gymnasium as gym
import numpy as np
import torch
from gymnasium import spaces
from stable_baselines3 import PPO

from curate_dataset import load_curated
from dataset_recorder import load_universal_dataset
from environment import observation_space_for
from obs_universal import OBS_SCHEMA
from ppo_anchor import DEFAULT_BC_STD, anchor_log_std
from teacher_intents import NUM_REASONS
from universal_policy import UniversalPolicy, load_universal_policy

NET_ARCH = [256, 256, 128]


class _DummyEnv(gym.Env):
    def __init__(self):
        self.observation_space = observation_space_for(OBS_SCHEMA)
        self.action_space = spaces.Box(-1.0, 1.0, shape=(3,), dtype=np.float32)

    def reset(self, **kwargs):
        return np.zeros(self.observation_space.shape, dtype=np.float32), {}

    def step(self, action):
        return np.zeros(self.observation_space.shape, dtype=np.float32), 0.0, False, False, {}


def bc_targets(bc: UniversalPolicy, obs: np.ndarray, reason_ids: np.ndarray) -> np.ndarray:
    """Acción del BC con la intención real, en lotes."""
    out = []
    bc.eval()
    with torch.no_grad():
        for i in range(0, len(obs), 8192):
            o = torch.tensor(obs[i:i + 8192])
            rid = torch.tensor(reason_ids[i:i + 8192]).clamp(0, NUM_REASONS - 1)
            onehot = torch.nn.functional.one_hot(rid, NUM_REASONS).float()
            out.append(bc(o, onehot).numpy())
    return np.concatenate(out)


def _actor_mean(policy, obs: torch.Tensor) -> torch.Tensor:
    latent_pi = policy.mlp_extractor.forward_actor(policy.extract_features(obs))
    return policy.action_net(latent_pi)


def distill(
    bc: UniversalPolicy,
    obs: np.ndarray,
    act: np.ndarray,
    reason_ids: np.ndarray,
    out_path: str,
    epochs: int = 30,
    batch_size: int = 512,
    lr: float = 1e-3,
    val_frac: float = 0.05,
    seed: int = 0,
    bc_std: float = DEFAULT_BC_STD,
) -> dict:
    """Entrena el actor de un PPO nuevo para imitar al BC. Guarda `out_path`(.zip)."""
    rng = np.random.default_rng(seed)
    torch.manual_seed(seed)
    targets = bc_targets(bc, obs, reason_ids)
    perm = rng.permutation(len(obs))
    n_val = max(1, int(len(obs) * val_frac))
    val, tr = perm[:n_val], perm[n_val:]

    model = PPO(
        "MlpPolicy", _DummyEnv(), policy_kwargs=dict(net_arch=NET_ARCH),
        device="cpu", seed=seed, verbose=0,
    )
    policy = model.policy
    params = (
        list(policy.mlp_extractor.policy_net.parameters()) + list(policy.action_net.parameters())
    )
    opt = torch.optim.Adam(params, lr=lr)
    x = torch.tensor(obs)
    y = torch.tensor(targets)
    best, bad, history = float("inf"), 0, []
    for _ in range(epochs):
        order = rng.permutation(tr)
        for i in range(0, len(order), batch_size):
            idx = torch.tensor(order[i:i + batch_size])
            loss = torch.nn.functional.mse_loss(_actor_mean(policy, x[idx]), y[idx])
            opt.zero_grad()
            loss.backward()
            opt.step()
        with torch.no_grad():
            v = torch.nn.functional.mse_loss(_actor_mean(policy, x[val]), y[val]).item()
        history.append(v)
        if v < best - 1e-7:
            best, bad = v, 0
        else:
            bad += 1
            if bad >= 5:
                break

    with torch.no_grad():
        pred = _actor_mean(policy, x[val]).numpy()
    anchor_log_std(model, bc_std)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    model.save(out_path)
    return {
        "epochs": len(history),
        "val_mae_to_bc": float(np.abs(pred - targets[val]).mean()),
        "val_mae_to_teacher": float(np.abs(pred - act[val]).mean()),
        "val_mae_per_dim_to_bc": np.abs(pred - targets[val]).mean(axis=0).tolist(),
        "bc_mae_to_teacher": float(np.abs(targets[val] - act[val]).mean()),
        "samples": int(len(obs)),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bc", default="models/universal_bc.pt")
    p.add_argument("--base-dataset", default="data/universal_teacher.jsonl")
    p.add_argument("--curated", default="data/curated_buffer.npz")
    p.add_argument("--out", default="models/ppo_universal_base")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--bc-std", type=float, default=DEFAULT_BC_STD)
    args = p.parse_args()

    chunks = []
    if os.path.isfile(args.base_dataset):
        chunks.append(load_universal_dataset(args.base_dataset, min_quality=0.5))
    if os.path.isfile(args.curated):
        chunks.append(load_curated(args.curated))
    chunks = [c for c in chunks if len(c[0])]
    if not chunks:
        print("[Bootstrap] Sin datos: genera el curado (curate_dataset.py) o indica --base-dataset.")
        return 1
    obs = np.concatenate([c[0] for c in chunks])
    act = np.concatenate([c[1] for c in chunks])
    rid = np.concatenate([c[2] for c in chunks])
    print(f"[Bootstrap] {len(obs):,} muestras; destilando {args.bc} -> {args.out}.zip")
    stats = distill(load_universal_policy(args.bc), obs, act, rid, args.out,
                    epochs=args.epochs, bc_std=args.bc_std)
    print(f"[Bootstrap] {stats['epochs']} épocas | error medio vs BC {stats['val_mae_to_bc']:.3f} "
          f"(gas/freno/volante {[round(v, 3) for v in stats['val_mae_per_dim_to_bc']]}) | "
          f"vs profesor {stats['val_mae_to_teacher']:.3f} (el BC: {stats['bc_mae_to_teacher']:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
