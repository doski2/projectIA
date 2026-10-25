"""Una sola fuente para los valores de PPO y el espacio de observación (auditoría 7.2.6)."""

import inspect

import main as m
import obs_spaces
import ppo_anchor
import ppo_bootstrap
import ppo_defaults
import pretrain
from environment import PCARS2Env, observation_space_for
from obs_universal import OBS_UNIVERSAL_DIM


def test_observation_space_has_a_single_definition():
    assert observation_space_for is obs_spaces.observation_space_for
    assert obs_spaces.observation_space_for("legacy_19").shape == (19,)
    assert obs_spaces.observation_space_for("universal_v1").shape == (OBS_UNIVERSAL_DIM,)


def test_dummy_env_matches_the_real_observation_space():
    env = obs_spaces.DummyEnv("universal_v1")
    obs, _ = env.reset()
    assert obs.shape == (OBS_UNIVERSAL_DIM,) and env.observation_space.contains(obs)
    assert obs_spaces.DummyEnv("legacy_19").reset()[0].shape == (19,)


def test_ppo_defaults_are_shared_not_copied():
    assert ppo_anchor.DEFAULT_BC_STD is ppo_defaults.DEFAULT_BC_STD
    assert ppo_bootstrap.NET_ARCH is ppo_defaults.PPO_NET_ARCH
    assert ppo_defaults.PPO_NET_ARCH == [256, 256, 128]
    src = inspect.getsource(m.parse_args)
    for name in ("DEFAULT_BC_STD", "ANCHOR_LR", "ANCHOR_EPOCHS", "ANCHOR_TARGET_KL", "CRITIC_WARMUP_STEPS"):
        assert name in src, name


def test_pretrain_uses_the_shared_net_arch_and_dummy_env():
    src = inspect.getsource(pretrain.pretrain)
    assert "PPO_NET_ARCH" in src and "DummyEnv" in src and "_low" not in src


def test_reposition_is_a_single_helper():
    src = inspect.getsource(PCARS2Env)
    assert src.count("press_button('back')") == 1
