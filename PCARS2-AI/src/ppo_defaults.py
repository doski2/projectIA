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

# Al continuar una tirada anterior (--resume-ppo) el ancla se afloja para que la política pueda aprender.
RESUME_BC_PULL = 0.01

# Puerta de velocidad (ppo_guard.py): una sola fuente para main, ppo_guard, ppo_progress y la GUI.
SPEED_STEP_KMH = 2.5      # subida de la velocidad objetivo tras validar la actual
SPEED_MAX_KMH = 80.0      # techo: el máximo del currículo de velocidad
GATE_CLEAN_CTE_M = 1.2    # CTE medio de un episodio limpio
GATE_FAIL_CTE_M = 1.6     # CTE medio a partir del cual una vuelta cuenta como fallo
