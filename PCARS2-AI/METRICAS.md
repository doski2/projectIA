# Guía de métricas PPO — PCARS2-AI

Referencia para interpretar `metricas.csv` y el monitor en consola.

**Operativa (comandos, GUI, qué log pasar):** [ENTRENAMIENTO.md](ENTRENAMIENTO.md)

---

## Archivo principal

`logs/{combo}/metricas.csv` — por defecto `logs/formula_rookie__sugo/metricas.csv`

- Una fila **cada 2048 pasos** de entrenamiento (rollout PPO).
- Se **reescribe** al iniciar cada sesión de `main.py` (no acumula sesiones en el mismo archivo).

---

## Columnas del CSV

### Agente en el juego

| Columna                      | Qué significa                                           | En modo Básicos                                   |
| ---------------------------- | ------------------------------------------------------- | ------------------------------------------------- |
| `ep_rew_mean`                | Recompensa media por episodio                           | Escala distinta al curriculum; buscar tendencia ↑ |
| `ep_len_mean`                | Pasos agente por episodio (× frame_skip ≈ frames juego) | ↑ = aguanta más en pista                          |
| `avg_speed_kmh`              | Velocidad media del rollout                             | Objetivo ~20 km/h (±5) en Fase 0                  |
| `max_speed_kmh`              | Pico de velocidad en el rollout                         | —                                                 |
| `avg_cte`                    | Desviación media de línea (m)                           | < 8 m ideal                                       |
| `avg_steering`               | Volante medio (− izq, + der)                            | —                                                 |
| `avg_throttle` / `avg_brake` | Acciones medias                                         | —                                                 |
| `dist_km`                    | Distancia acumulada en el rollout                       | —                                                 |

### Terminaciones (porcentaje de episodios en el rollout)

| Columna           | Condición                                            | `fin=` en consola |
| ----------------- | ---------------------------------------------------- | ----------------- |
| `pct_stuck`       | speed < umbral durante 8 s / 15 s (básicos) a 25 fps de juego | `stuck`           |
| `pct_no_progress` | lap_dist no crece +10 m en 12 s / 30 s (básicos) a 25 fps     | `no_progress`     |
| `pct_wrong_way`   | heading > 160° ~2 s                                  | `wrong_way`       |
| `pct_pit_box`     | CTE absurda cerca de meta                            | `pit_box`         |
| `pct_lap_done`    | Vuelta completada                                    | `lap_done`        |
| `pct_timelimit`   | TimeLimit externo                                    | `timelimit`       |

### PPO / red

| Columna                | Qué significa                   | Rango saludable                    |
| ---------------------- | ------------------------------- | ---------------------------------- |
| `explained_variance`   | Calidad del crítico             | > 0.5                              |
| `value_loss`           | Error del crítico               | Baja con el tiempo                 |
| `policy_gradient_loss` | Pérdida actor                   | Cercano a 0, negativo              |
| `entropy_loss`         | Exploración                     | ~−3 a −6                           |
| `std`                  | Aleatoriedad acciones           | ~0.8–0.9 en curso; baja al madurar |
| `approx_kl`            | Cambio de política              | < 0.02 ideal                       |
| `clip_fraction`        | % recortes PPO                  | 5–20%                              |
| `fps`                  | Pasos agente / segundo          | Con `frame_skip=4` y juego ~25 Hz: **~4–6** estable |
| `total_timesteps`      | Pasos acumulados (contador SB3) | —                                  |
| `udp_physics`          | Frames CAR_PHYSICS aceptados en el rollout | ≈ `2048 × frame_skip` si sin timeouts |
| `pct_udp_timeout`      | % esperas UDP sin frame nuevo   | **< 5%** ideal; alto = juego pausado o desync |
| `pct_udp_backlog`      | % física descartada por cola UDP | **< 10%** ideal; alto = ráfagas irreales (FPS inflado) |

---

## Monitor en vivo (`monitor.bat`)

Actualiza cada ~20 s. Muestra tendencias ▲▼ respecto al rollout anterior.

Métricas destacadas: recompensa, duración, velocidad, distancia, terminaciones, salud PPO.

**Tiempo estimado:** barra de **pasos** (timesteps SB3) + ETA según FPS medio de los últimos rollouts.
El objetivo se toma de `--timesteps`, de `v2/user_settings.json` o de la GUI (botón Monitor).

La línea inferior es solo **tendencia visual** de `ep_rew_mean` (no un % de entrenamiento).

```bat
monitor.bat --timesteps 450000
```

Con **`frame_skip=4`**, el techo teórico es ~**6 pasos/s** (juego 25 Hz ÷ 4). El FPS del CSV no es
uso de GPU.

| FPS medio | 150k pasos (desde 0) | 450k pasos (desde ~40k) |
| --------- | -------------------- | ----------------------- |
| 4         | ~10 h                | ~28 h                   |
| 6         | ~7 h                 | ~19 h                   |
| 8         | ~5 h                 | ~14 h                   |

Si ETA > 8 h, el monitor avisa «dejar toda la noche».

**Planificar cuántos pasos poner** (mañana, noche, fórmula): ver
[ENTRENAMIENTO.md — Planificar pasos y tiempo](ENTRENAMIENTO.md#planificar-pasos-y-tiempo).

---

## TensorBoard

```bat
```

→ http://localhost:6006 — curvas `rollout/` y `train/` de SB3.

---

## Señales de progreso — Fase Básicos (20 km/h)

| Señal           | Objetivo                               |
| --------------- | -------------------------------------- |
| `avg_speed_kmh` | 18–25 km/h estable                     |
| `avg_cte`       | < 8 m, bajando                         |
| `ep_len_mean`   | > 120, luego > 150                     |
| `pct_stuck`     | < 50%                                  |
| `pct_lap_done`  | Aparece en algunos rollouts tras 100k+ |

No comparar `ep_rew_mean` con sesiones curriculum antiguas (función de reward distinta).

---

## Historial de fases (referencia)

| Fase                | Período    | Config                           | Notas                                                   |
| ------------------- | ---------- | -------------------------------- | ------------------------------------------------------- |
| 0 — BC pretrain     | —          | `pretrain.bat`                   | Actor desde referencia                                  |
| 1 — Curriculum      | ~200k–970k | `--curriculum`                   | Reward gas; archivado en `*_archive_curriculum`         |
| 2 — Básicos v2      | actual     | `--basics --speed-target-kmh 20` | Línea + velocidad + girar; sesiones cortas supervisadas |
| 3 — Subir velocidad | pendiente  | Básicos + auto speed-target      | 25 → 35 km/h                                            |
| 4 — Reward completa | pendiente  | sin `--basics`                   | Cuando conduzca bien en línea                           |

---

## Detectores de terminación (código)

Contadores en **frames de juego** (25 fps); independientes de `frame_skip`.

| Regla | Modo completo | Básicos | Curriculum |
| ----- | ------------- | ------- | ---------- |
| `stuck` (speed < umbral) | < 3.6 km/h, 8 s (200 fr) | < 1.4 km/h, 15 s (375 fr) | igual que completo |
| `no_progress` (+10 m) | 12 s (300 fr) | 30 s (750 fr) | 30 s (750 fr) |
| `wrong_way` | heading > 160°, ~2 s | igual | igual |
| `pit_box` | CTE > 20 m cerca meta | igual | igual |

`GRACE_STEPS = 250` al inicio de episodio (sin cortes por stuck/no_progress/wrong_way).

No hay terminación dura por CTE > 8 m: solo penalización en la reward.

---

## Documentación relacionada

- [ENTRENAMIENTO.md](ENTRENAMIENTO.md) — comandos, GUI v2, logs, revisión de sesiones
- [DEPENDENCIAS.md](DEPENDENCIAS.md) — entorno Python y paquetes
