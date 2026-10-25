"""Ancla de PPO al BC (auditoría 7.1.5)."""

import math

import torch
from stable_baselines3 import PPO

from ppo_anchor import FreezeActorCallback, anchor_log_std, _actor_params


def _model():
    return PPO("MlpPolicy", "Pendulum-v1", n_steps=32, batch_size=32, n_epochs=2,
               policy_kwargs=dict(net_arch=[16]), device="cpu", seed=0)


def test_ppo_born_with_std_one_and_anchor_lowers_it():
    m = _model()
    assert math.isclose(m.policy.log_std.exp().mean().item(), 1.0, rel_tol=1e-6)
    assert anchor_log_std(m, 0.1) is True
    assert math.isclose(m.policy.log_std.exp().mean().item(), 0.1, rel_tol=1e-5)


def test_anchor_does_not_raise_a_smaller_std():
    m = _model()
    with torch.no_grad():
        m.policy.log_std.fill_(math.log(0.05))
    assert anchor_log_std(m, 0.1) is False
    assert math.isclose(m.policy.log_std.exp().mean().item(), 0.05, rel_tol=1e-5)


def test_frozen_actor_keeps_weights_while_critic_learns():
    m = _model()
    actor0 = [p.detach().clone() for p in _actor_params(m.policy)]
    critic0 = [p.detach().clone() for p in m.policy.mlp_extractor.value_net.parameters()]
    m.learn(total_timesteps=64, callback=FreezeActorCallback(warmup_steps=10_000))
    assert all(torch.equal(a, p) for a, p in zip(actor0, _actor_params(m.policy)))
    assert any(not torch.equal(c, p) for c, p in zip(critic0, m.policy.mlp_extractor.value_net.parameters()))


def test_actor_unfreezes_after_warmup():
    m = _model()
    actor0 = [p.detach().clone() for p in _actor_params(m.policy)]
    m.learn(total_timesteps=128, callback=FreezeActorCallback(warmup_steps=32))
    assert any(not torch.equal(a, p) for a, p in zip(actor0, _actor_params(m.policy)))
    assert all(p.requires_grad for p in _actor_params(m.policy))


def test_pull_to_bc_moves_actor_toward_the_reference_but_not_the_critic():
    from ppo_anchor import PullToBCCallback

    m = _model()
    cb = PullToBCCallback(alpha=0.5)
    cb.init_callback(m)
    cb._on_training_start()
    ref = [p.detach().clone() for p in _actor_params(m.policy)]
    critic0 = [p.detach().clone() for p in m.policy.mlp_extractor.value_net.parameters()]
    with torch.no_grad():
        for p in _actor_params(m.policy):
            p.add_(1.0)
        for p in m.policy.mlp_extractor.value_net.parameters():
            p.add_(1.0)
    cb._on_rollout_start()
    for p, r in zip(_actor_params(m.policy), ref):
        assert torch.allclose(p, r + 0.5, atol=1e-6)      # la mitad del desvío recuperado
    for p, c in zip(m.policy.mlp_extractor.value_net.parameters(), critic0):
        assert torch.allclose(p, c + 1.0, atol=1e-6)      # el crítico no se toca


def test_pull_to_bc_zero_alpha_is_a_noop():
    from ppo_anchor import PullToBCCallback

    m = _model()
    cb = PullToBCCallback(alpha=0.0)
    cb.init_callback(m)
    cb._on_training_start()
    before = [p.detach().clone() for p in _actor_params(m.policy)]
    with torch.no_grad():
        for p in _actor_params(m.policy):
            p.add_(1.0)
    cb._on_rollout_start()
    assert all(torch.allclose(p, b + 1.0) for p, b in zip(_actor_params(m.policy), before))
