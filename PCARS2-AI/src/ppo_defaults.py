"""
ppo_defaults.py
Valores de PPO compartidos por main.py, ppo_anchor.py, ppo_bootstrap.py y pretrain.py.
Sin dependencias pesadas, para que `main.py --help` siga siendo rápido.
"""

# Arquitectura del actor/crítico de SB3 (la del BC universal es la misma salvo la entrada).
PPO_NET_ARCH = [256, 256, 128]

# Al partir de un modelo BC/base: PPO nace con desviación 1,0 y destruiría lo imitado.
DEFAULT_BC_STD = 0.1
ANCHOR_LR = 3e-5
ANCHOR_EPOCHS = 4
ANCHOR_TARGET_KL = 0.02
BC_PULL = 0.05          # fracción del desvío del actor que se recupera tras cada actualización
CRITIC_WARMUP_STEPS = 8192
