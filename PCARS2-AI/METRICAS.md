# Guía de métricas PPO — PCARS2-AI

Referencia rápida para interpretar el CSV y la tabla del CMD.

---

## rollout/ — Lo que hizo el agente en el juego

| Métrica | Qué significa | ¿Bueno o malo? |
|---|---|---|
| `ep_len_mean` | Promedio de pasos por episodio (~10 ms cada uno). 6000 = TimeLimit completo. | Cuanto más alto mejor. 6000 = completó el tiempo sin salirse. |
| `ep_rew_mean` | Recompensa promedio por episodio. Negativo = más castigos que premios. | Debe subir hacia 0 con el tiempo. |

---

## time/ — Velocidad del entrenamiento

| Métrica | Qué significa |
|---|---|
| `fps` | Pasos por segundo. Depende del juego y la CPU. |
| `iterations` | Veces que el agente recogió datos (cada una = 2048 pasos). |
| `total_timesteps` | Pasos totales acumulados desde el inicio. |

---

## train/ — Lo que aprende la red neuronal

| Métrica | Qué significa | Rango saludable |
|---|---|---|
| `explained_variance` | Qué tan bien predice el crítico. 0=nada, 1=perfecto, negativo=peor que adivinar. | > 0.5 idealmente |
| `value_loss` | Error del crítico al predecir recompensas futuras. | Bajando con el tiempo |
| `policy_gradient_loss` | Pérdida del actor. Negativo = la política mejora. | Cercano a 0, negativo |
| `entropy_loss` | Entropía de la política. Más negativo = más exploración. | -3 a -6 |
| `std` | Aleatoriedad de las acciones. 1.0=aleatorio, 0.3=determinista. | Baja de 1.0 al madurar |
| `approx_kl` | Cuánto cambia la política entre updates. Si sube mucho = inestable. | < 0.02 |
| `clip_fraction` | % de veces que PPO recortó el gradiente. | 5–20% |
| `learning_rate` | Velocidad de aprendizaje (fija en 1e-4). | — |
| `n_updates` | Actualizaciones totales de la red. | Contador |

---

## Diagnóstico del estado actual (~1.38M pasos, 17 mayo 2026)

```
ep_rew_mean   +3599   → Positivo estable antes del incidente del box.
ep_len_mean    302    → Episodios algo más cortos que sesión anterior.
std            1.43   → Subió ligeramente (exploración activa).
avg_speed      0.3    → DEGRADADO por incidente: coche en box 271 min sin aprender.
dist_km        0.175  → Idem: distancia media/episodio muy baja.
```

**Incidente detectado (17 mayo):**  
El coche chocó en pista, giró 180° y entró al box en sentido contrario.  
La IA del juego tomó el control dentro del box. El episodio no terminaba  
(speed > 1 m/s, pero lap_distance no avanzaba) → 271 minutos perdidos.  

**Fixes aplicados:**
- `no_progress`: termina si `lap_distance` no crece +10m en 12s (cubre box + atasco lento)
- `wrong_way`: termina si heading >160° respecto al trazado durante 2s (cubre giro 180°)
- Ambos activos junto al detector previo `stuck` (speed < 1 m/s, 8s)

**Estado:** reentrenando con los fixes aplicados desde checkpoint.

---

## Historial de fases de entrenamiento

| Fase | Steps aprox. | Configuración | Resultado |
|---|---|---|---|
| Fase 0 — BC pretrain | — | `pretrain.bat` | Actor inicializado con datos de referencia |
| Fase 1 — Curriculum | ~200k | `--warmup-steps 30 --curriculum` | `avg_speed` hasta 70.9 km/h |
| Fase 2 — Reward completa | ~100k | `--warmup-steps 30` | Consolidación en pista |
| Fase 3 — Long run | ~500k+ | `--warmup-steps 30 --curriculum` | `ep_rew_mean` de -3507 a +3599 |
| Fase 3b — Bug/fix | ~500k | igual | Incidente box (271 min). Fixes: `no_progress` + `wrong_way` |
| Fase 3c — Reentrenamiento | en curso | igual + fixes | Objetivo: `avg_speed` estable >40 km/h |

---

## Comandos activos (configuración estable)

```bat
:: Entrenamiento principal (sesión larga)
:: Referencia: sugo_ai.json (15 vueltas grabadas de la IA del juego; el antiguo
:: formula_rookie__sugo__gpyf.json solo tenía 1 vuelta). Misma pista (SUGO_GP, 3567 m).
.\entrenar.bat src\refs\sugo_ai.json 500000 --frame-skip 4 --warmup-steps 30 --curriculum

:: Monitor en tiempo real (otra terminal)
python src\monitor.py --refresh 20

:: TensorBoard (opcional)
tensorboard --logdir logs/formula_rookie__sugo
```

---

## Detectores de terminación de episodio

| Detector | Condición | Tiempo | `fin=` en log |
|---|---|---|---|
| `stuck` | speed < 1 m/s | 8s | `stuck` |
| `no_progress` | lap_dist no crece +10m | 12s | `no_progress` |
| `wrong_way` | heading >160° + speed >2 m/s | 2s | `wrong_way` |
| `lap_done` | vuelta completada | — | `lap_done` |
| `timelimit` | TimeLimit wrapper externo | — | `timelimit` |

---

## Señales de progreso

| Señal | Qué significa |
|---|---|
| `ep_rew_mean` sube y se mantiene positivo | ✅ Conseguido (max +3599) |
| `std` baja de 1.0 | ⚠️ Subió a 1.43 tras bug, debe volver a bajar |
| `explained_variance` > 0.5 estable | ⚠️ Oscila, normal con reward positiva |
| `ep_len_mean` > 300 constante | ⚠️ En progreso (302) |
| `avg_speed` > 40 km/h estable | ❌ Degradado por bug. Objetivo tras reentrenamiento |
| `fin=wrong_way` o `fin=no_progress` en log | Detector activo, episodio cortado correctamente |

---

## Próximos pasos recomendados

1. **Seguir entrenando** con la configuración actual hasta ~1M pasos totales
2. Cuando `avg_speed` suba de forma estable, quitar `--curriculum` (phase 4)
3. Si `ep_rew_mean` se estanca >50k steps, bajar `learning_rate` a `5e-5`
4. Transfer a nueva pista: grabar referencia nueva + `pretrain.bat` + `entrenar.bat` con `--model`
