# Auditoría de código — fallos, duplicados y mejoras

> **Sprint 1 completado (2026-10-16):** 1.1 (se conserva la copia de la raíz), 2.1 (`off_track` muerto eliminado),
> 2.2, 2.3, 2.7, 2.8 y 2.10 resueltos. `SPEED_BANDS_KMH` en `v2/config.py` es un re-export usado por tests y se mantiene con `noqa`.
>
> **Sprint 2 completado (2026-10-16):** 1.2 (`telemetry_udp.apply_packet` compartido por `DriveSession` y `PCARS2Env`),
> 1.3 (`reference_recorder.slugify` único), 2.4 (`zip(strict=True)`), 2.5 (los dos `except Exception` acotados a
> `OSError` / `OSError, ValueError, KeyError`). Sección 4: nuevo `tests/test_shared_helpers.py` (10 tests de humo:
> `driver_cli`, `drive_actions`, `eval_*`/`pretrain_universal`, `apply_packet`, `slugify`). Total: 209 tests.
> **Sprint 3 (parcial, 2026-10-16):** `environment._check_done` dividido en `_check_pit_box`, `_check_stuck`,
> `_check_no_progress` y `_check_wrong_way` (mismo orden y semántica; 4 tests nuevos en `test_environment_done_checks.py`).
> Corregido el aviso de pyright en `drive_session.sync_physics_frame` (tipo de `packet`). Total: 213 tests.
> Además: `auto_shift.shift` (extraído `_shift_toward_first`), `safety_monitor.update` (cuatro `_check_*`, mismo orden)
> y `teaching_driver.run` (extraídos `_print_banner`, `_open_dataset_recorder`, `_finish`; complejidad 16→12; el bucle no se tocó).
> `learn_driver.run`: estado del currículo extraído a `LearnProgress` + `advance_progress` + `announce_autonomy`
> (5 tests en `test_learn_progress_state.py`; complejidad 40→35, el bucle sigue en `run`). Total: 218 tests.
> `imitation_driver.run`: extraídos `select_bc_action` y `mix_drive_action` (+`DriveMix`); complejidad 26→20,
> 6 tests en `test_imitation_mix.py`. Total: 224 tests.
> `main.train`: callback de métricas movido a `MetricsAccumulator` (módulo, testable, `_on_step` 15→trivial) y
> selección de modelo a `_load_or_create_model`; complejidad 41→21; 9 tests en `test_main_metrics.py`. Total: 232 tests.
> **Higiene (2026-10-16):** 5.2 (`gemini-code-….md` movido a `docs/archivo/`), 5.4 (`ruff.toml` con F/E9/B y `ruff` en
> `requirements.txt`; `ruff check src v2 scripts tests` limpio), 5.6 (`set PYTHONUTF8=1` en los 21 `.bat`).
> Siguen abiertos 5.3 (`Tareas.txt`) y 5.5 (`print` → `logging`).
> **Continuación (2026-10-19):** 1.4 (un único `_on_learn_settings_change` en `v2/gui.py`), 1.5 (`pct` único en
> `safety_monitor`, reutilizado por `validation_phases`; `launcher` importa `settings_to_dict` de `config`),
> 2.6 (ya sin avisos de ruff), 2.9 (sin `PLW2901` en `bc_training`, `pretrain`, `dataset_recorder` ni
> `analyze_session_deviation`). 241 tests, ruff limpio.
> **Estado a 2026-10-24 (244 tests, ruff limpio):** abiertos solo la sección 3 (13 funciones con C901 > 10:
> `learn_driver.run` 29, `imitation_driver.run` 22, `main.train` 21, `session_report.write_html_replay` 19 y
> ocho entre 11 y 13), la sección 4 (`teaching_driver` y `teaching_diag` sin tests; `imitation_driver`,
> `session_report` y `eval_driver` con uno) y 5.3 (`Tareas.txt`) y 5.5 (199 `print` → `logging`).
> 5.1 resuelto con el commit del fix de marchas: `LapTransitionGuard` con timeout de engrane,
> `AutoShifter.neutral_retry_s` (opt-in en learn/imitation) y `shift_event` en el log de ticks.
> Los bucles de `run` se refactorizan cuando acabe el currículo (no tocar un bucle que funciona).

Fecha: 2026-10-15. Alcance: `PCARS2-AI/src`, `v2`, `scripts`, `tests` y scripts de la raíz.
Método: análisis AST (nombres/cuerpos duplicados), `ruff` (F, B, PLW, C901) y `pytest`.

Estado base: **199 tests pasan** (3 s). Ruff: 55 avisos (25 autocorregibles).

Leyenda de prioridad: **P1** hacer ya · **P2** próxima iteración · **P3** cuando haya tiempo.

---

## 1. Duplicados de código

### 1.1 `fix_markdownlint.py` existe dos veces (P1)

- `fix_markdownlint.py` (raíz, 1079 líneas) y `PCARS2-AI/fix_markdownlint.py` (565 líneas).
- ~30 funciones idénticas (`fix_tables`, `wrap_line_md013`, `process_file`, `main`…).
- Las cabeceras ya divergen (reglas auto-fix distintas: MD004/MD034/MD037 solo en la raíz;
  MD001 solo en la de `PCARS2-AI`).
- La copia de la raíz contiene además funciones duplicadas internamente
  (p. ej. `fix_fenced_code_language_v2`).

**Acción:** quedarse con una sola versión (la raíz es la más completa y es la que tiene
cambios sin commit), borrar la otra y ajustar rutas en `.bat`/documentación si las referencian.

### 1.2 `_apply_packet` duplicado (P1)

- [src/drive_session.py:57](../src/drive_session.py#L57) y
  [src/environment.py:727](../src/environment.py#L727): mismo cuerpo, solo cambian
  los nombres de atributo (`last_telem` vs `_last_telem`).
- Riesgo: añadir un tipo de paquete nuevo y olvidar una de las copias.

**Acción:** extraer a una función/clase de estado en `telemetry_udp.py`
(p. ej. `TelemetryState.apply(ptype, packet)`) y usarla en ambos sitios.

### 1.3 `_slugify` duplicado (P2)

- [src/environment.py:815](../src/environment.py#L815) y
  [src/reference_recorder.py:67](../src/reference_recorder.py#L67): cuerpo idéntico.

**Acción:** mover a un módulo común (`paths.py` o `reference_recorder`) e importar.

### 1.4 Handlers de GUI idénticos (P3)

- [v2/gui.py:506](../v2/gui.py#L506) `_on_learn_stage_change` y `_on_learn_settings_change`
  tienen exactamente el mismo cuerpo; además `_on_learn_speed_change` solo delega.

**Acción:** dejar un único handler y apuntar los tres `command=` a él.

### 1.5 Helpers menores repetidos (P3)

| Función | Ubicaciones | Nota |
| --- | --- | --- |
| `_pct` | `safety_monitor.py:241`, `validation_phases.py:137` | `learning_curriculum.py` la importa sin usarla |
| `settings_to_dict` | `v2/config.py:190`, `v2/launcher.py:72` | unificar en `config.py` |
| `signed_lateral_error` | `obs_universal.py:42`, `teacher_controller.py:113` | el segundo es un wrapper de método; aceptable |
| `press_button` / `apply_action` | `auto_shift.py` (Protocol), `controller.py` | el Protocol es correcto; sin acción |

### 1.6 Estructura repetida en los drivers (P2)

`imitation_driver.run` (270 líneas), `learn_driver.run` (381), `teaching_driver.run` (214) y
`main.train` (~200) comparten el mismo esqueleto: parseo de args → env → sesión/log →
bucle de pasos → informe. Ver sección 3.

---

## 2. Posibles fallos y código muerto

| # | Prioridad | Dónde | Problema |
| --- | --- | --- | --- |
| 2.1 | P1 | [src/validation_phases.py:410](../src/validation_phases.py#L410) | `off_track` se calcula y nunca se usa. Verificar si el criterio de la fase debería usarlo (posible regla de validación no aplicada) o eliminar. |
| 2.2 | P2 | [src/session_report.py:431](../src/session_report.py#L431) | `phase_id` leído y no usado: `--force` regenera el HTML sin pasar la fase. Comprobar si `write_html_replay` debería recibirla. |
| 2.3 | P2 | [v2/launcher.py:195](../v2/launcher.py#L195) | `mode = get_teaching_mode(...)` no usado en `build_teaching_argv`; si el modo no existe, ¿debía fallar aquí? |
| 2.4 | P2 | [src/track_deviation.py:71](../src/track_deviation.py#L71) | `zip()` sin `strict=`: si las listas difieren de longitud se trunca en silencio. |
| 2.5 | P2 | `src` (2 casos) | `except Exception` / `except:` demasiado amplios; revisar que no oculten errores de UDP o I/O. |
| 2.6 | P3 | `src/environment.py:48-57` | 6 constantes importadas de `obs_builder` sin usar (¿re-export intencionado? si no, borrar). |
| 2.7 | P3 | `src/universal_policy.py:19` | `build_conditioned_obs` importado sin usar; `json` también. |
| 2.8 | P3 | `__summarize_tb.py` (raíz) | Empieza con BOM (U+FEFF) y `ast.parse` falla; guardar como UTF-8 sin BOM. |
| 2.9 | P3 | `src/*` | `PLW2901`: variables de bucle reasignadas (`line`, `obs_b`…) en `bc_training`, `pretrain`, `dataset_recorder`. Funciona, pero es propenso a errores. |

### 2.10 Imports sin usar (P3, autocorregible)

Ejecutar `ruff check src v2 scripts --select F401,F841 --fix` elimina: `Path` (bc_training),
`field` (dataset_recorder, validation_phases), `Optional/Any/Dict/List/Tuple`
(obs_builder, safety_monitor, session_log, session_report, teacher_intents, v2/config),
`math` (session_report), `SPEED_BANDS_KMH` (v2/config), `get_learn_stage` (v2/gui),
`format_lap_time` y `_pct` (learning_curriculum).

---

## 3. Complejidad (candidatos a refactor)

Funciones con complejidad ciclomática muy por encima de 10 (ruff C901):

| Función | Complejidad | Líneas |
| --- | --- | --- |
| `learn_driver.run` | 40 | 381 |
| `main.train` | 41 | ~200 |
| `imitation_driver.run` | 26 | 270 |
| `session_report.write_html_replay` | 19 | — |
| `teaching_driver.run` | 16 | 214 |
| `environment._check_done` | 16 | — |
| `auto_shift.shift` | 15 | — |
| `main._on_step` | 15 | — |
| `safety_monitor.update` | 14 | — |

**Propuesta (P2):** partir los `run` en fases (`_setup`, `_loop_step`, `_finalize`) y crear
un `BaseDriver`/helpers compartidos en `driver_cli.py` / `drive_session.py` (ya existen y
están infrautilizados). `environment._check_done` y `auto_shift.shift` se pueden dividir
en predicados con nombre (uno por condición de fin / de cambio), lo que también facilita
los tests.

---

## 4. Cobertura de tests

Módulos **sin ningún test** que los referencie:
`imitation_driver`, `teaching_driver`, `driver_cli`, `eval_driver`, `eval_universal`,
`pretrain_universal`, `drive_actions`, `teaching_diag`.

- **P2:** tests de humo para `driver_cli`/`eval_*` (parseo de argumentos, `--help`) y para
  `drive_actions`. Son baratos y protegen los `.bat`.
- **P2:** al partir los `run` (sección 3) añadir tests de las fases extraídas con un env falso.
- `session_report` solo tiene 1 test frente a ~440 líneas.

---

## 5. Higiene del repositorio y documentación

| # | Prioridad | Tema |
| --- | --- | --- |
| 5.1 | P1 | (resuelto 2026-10-24) Había cambios sin commit en 9 ficheros (`auto_shift`, `lap_transition`, `learn_driver`, `pcars2_gear`, tests, `Tareas.txt`, `fix_markdownlint.py`). Commitear tras revisar. |
| 5.2 | P2 | (resuelto) `gemini-code-1777834144518.md` (raíz, 200 KB): volcado de una conversación, parece ajeno al proyecto. Moverlo a `docs/archivo/` o borrarlo. |
| 5.3 | P2 | `Tareas.txt` mezcla lista de fases con una nota suelta (`pendiente: l2`). Pasar a `docs/ROADMAP_CONDICIONES.md` o a issues. |
| 5.4 | P3 | (resuelto) `requirements.txt`: añadir `ruff` en dependencias de desarrollo y un `pyproject.toml` con su configuración (C901 en 15, ignorar PLW2901 si se prefiere). |
| 5.5 | P3 | 198 `print(` en `src`: migrar a `logging` (niveles y salida a fichero) manteniendo la salida de consola en los CLI. |
| 5.6 | P3 | (resuelto) Mojibake en consola Windows (`cuerpo id�ntico`): forzar `PYTHONUTF8=1` en los `.bat`. |

---

## 6. Plan de trabajo sugerido

1. **Sprint 1 (rápido, bajo riesgo):** 1.1, 2.1, 2.10 (`ruff --fix`), 5.1, 2.8.
2. **Sprint 2:** 1.2 y 1.3 (extraer duplicados), 2.2–2.5, tests de humo (sección 4).
3. **Sprint 3:** refactor de `run`/`train` (sección 3) con los tests nuevos como red de seguridad.
4. **Continuo:** 5.2–5.6.

Comandos de verificación:

```bash
cd PCARS2-AI
python -m pytest -q
python -m ruff check src v2 scripts --select F,E9,B,PLW,C901 --output-format concise
```

> Los avisos de ruff se obtuvieron con reglas ampliadas (B, PLW, C901) que el proyecto no
> tiene configuradas todavía; no son errores en la configuración actual.

---

## 7. Revisión del camino PPO (2026-10-25)

Alcance: `src/main.py`, `src/environment.py`, `src/obs_builder.py`, `src/pretrain.py`,
`src/checkpoints.py`, `src/eval_driver.py`, `src/drive_session.py`. **Solo revisión; **corregidos 7.1.1-7.1.3
(2026-10-25, tests en `test_environment_sync.py`)**, el resto sigue pendiente. El PPO nunca se ha probado con el modelo actual (ver
[ROADMAP_CONDICIONES.md](ROADMAP_CONDICIONES.md), capa 4). Los puntos marcados «verificado» se
comprobaron con un script o con los logs; los marcados «probable» salen de leer el código.

### 7.1 Fallos de lógica

| # | Prio | Dónde | Problema |
| --- | --- | --- | --- |
| 7.1.1 ✅ | P1 | `environment.py:_physics_key` y `_sync_physics_frame` | **Verificado (sintético).** La clave de «frame nuevo» redondea velocidad (0,01) y posición (0,1 m). Un coche parado produce **una sola clave** (60 frames reales distintos → 1 clave), y a 1 m/s solo se aceptan 21 de 120 frames. `DriveSession.physics_key` usa floats completos y no tiene el problema (en los logs de aprendizaje el coche parado sigue generando ticks a 60 Hz). En el entorno de PPO, un coche parado hace que `_sync_physics_frame` expire (0,1 s) en cada paso. |
| 7.1.2 ✅ | P1 | `environment.py:step` | (Corregido: `MAX_SYNC_FAILURES` pasos seguidos sin frame trunca con `udp_timeout`; la clave usa `DriveSession.physics_key`.) Consecuencia de 7.1.1: si la sincronización falla, el bucle hace `break` **antes** de `_check_done`, así que `stuck`, `no_progress` y `wrong_way` no avanzan. Un coche parado contra el muro **no termina nunca el episodio** (no hay `TimeLimit` en `main.py`, solo `Monitor`). Probable, depende de 7.1.1. |
| 7.1.3 ✅ | P1 | `environment.py:GAME_FPS = 25` (y `safety_monitor.py`) | El juego emite a **60 Hz** (`t_s` avanza 0,016 s por tick en los logs), no a 25. Todos los umbrales «en segundos» son 2,4 veces más cortos de lo que dicen: stuck 8 s → 3,3 s reales, no_progress 12 s → 5 s, y también `SustainedCteGuard` (2 s → 0,83 s). Verificado con los logs; la constante estaba duplicada en los dos módulos. (Corregido: `GAME_FPS = 60` definido en `safety_monitor` e importado por `environment`; los umbrales en segundos ahora son segundos reales, también en `SustainedCteGuard`/`StuckOffTrackAbort`.) |
| 7.1.4 ✅ (opt-in) | P1 | `obs_builder.py:build_obs` (19 dim) | El **CTE va sin signo** (`cte_norm` en [0, 1]). La política no puede saber de qué lado de la línea está y por tanto hacia dónde corregir; `obs_universal` sí usa CTE con signo. Es un problema de observabilidad del PPO actual y del BC legado de 19 dim. (Corregido de forma opcional: `PCARS2Env(obs_schema="universal_v1")` / `main.py --obs-schema universal_v1` usa `obs_universal` con CTE con signo; el defecto sigue siendo `legacy_19` para no romper modelos guardados. Falta que `pretrain.py` genere el dataset en `universal_v1`: va con 7.1.5.) |
| 7.1.5 ✅ (parcial) | P1 | `main.py:_load_or_create_model`, `pretrain.py` | **Sin ancla al BC.** `PPO` nace con `log_std = 0` (desviación 1,0 sobre acciones en [−1, 1]). Con `--base-model` no se toca `log_std`, así que la política arranca con ruido enorme y pierde lo aprendido; `_reset_log_std` solo actúa en `--model`/continuar y deja 0,85. Además `pretrain.py` solo entrena el actor: el crítico queda aleatorio y las primeras actualizaciones de PPO usan ventajas basura. Necesita `log_std` pequeño (≈ log 0,1), calentamiento del crítico y/o penalización KL contra el BC. (Corregido: `ppo_anchor.py` + `--bc-std` 0,1 en las ramas que parten de un modelo base/BC y en `pretrain.py`, y `--critic-warmup-steps` 8192 con el actor congelado. Pendiente: penalización KL. El modelo base en `universal_v1` se genera ahora con `ppo_bootstrap.py` (destila el BC), no con `pretrain.py`.) Además: `main.py --steer-comp`, y `HoldBrakeDuringUpdateCallback` frena el coche mientras PPO actualiza la red (el juego no se pausa). |
| 7.1.6 | P2 | `environment.py:reset` | `_prev_lap_dist = 0.0`. Si el juego reposiciona al coche lejos de la meta, el primer paso calcula `progreso = lap_distance − 0` (hasta 3567 m × 0,02 = 71 de recompensa en un solo paso) y contamina la normalización de `VecNormalize`. Probable: depende de dónde coloque el juego al coche. |
| 7.1.7 | P2 | `environment.py:step` | Con `frame_skip > 1` cada frame interno recalcula el coste de volante con el mismo `_prev_steering`, así que la penalización por cambio se aplica N veces. |
| 7.1.8 | P2 | `obs_builder.py` / `obs_universal.py` | `gear_norm = gear / num_gears` recortado a 1: la marcha atrás (15) sale igual que la marcha más alta. `pretrain.py` normaliza con `MAX_GEARS = 6` (comentario: «Formula Rookie tiene 6 marchas») y el coche tiene 4 (`num_gears` = 4): la observación del pre-entrenamiento no coincide con la de conducción. |
| 7.1.9 | P2 | `environment.py:_compute_reward` (modo básicos) | `r_actions = 0.15·gas − 0.25·freno` premia el gas y penaliza el freno siempre, lo que choca con frenar antes de las curvas, y no hay ninguna penalización por solape de gas y freno (ver el roadmap). |
| 7.1.10 | P3 | `main.py` | `--car` y `--track` tienen valor por defecto («formula_rookie», «sugo»), así que la auto-detección de combo (`wait_for_combo`) **no se ejecuta nunca** salvo que se vacíen los dos argumentos. |
| 7.1.11 | P3 | `main.py` | Las semillas se fijan en NumPy y PyTorch, pero no en `PPO(seed=...)` ni en el entorno: no es reproducible. |
| 7.1.12 | P3 | `eval_universal.py` | Evalúa con el `reason` **verdadero** del teacher como entrada (también así conduce el BC en `learn_driver`). En modo `autonomous` el `reason` lo tiene que predecir la red, y ese camino no se evalúa. |

### 7.2 Duplicados

| # | Prio | Dónde | Qué se repite |
| --- | --- | --- | --- |
| 7.2.1 | P1 | `environment.py` y `drive_session.py` | Mismo bloque de sincronización UDP (`ingest_pending`, `recv_blocking`, `sync_physics_frame`, estadísticas, ancla). Son ~100 líneas que ya divergieron (la clave de 7.1.1). Unificar en una sola clase de sesión. |
| 7.2.2 ✅ (parcial: las constantes con el mismo valor ya tienen una sola fuente; `STUCK_*` y `NO_PROGRESS_TIME_S` difieren a propósito) | P1 | `environment.py` y `safety_monitor.py` | Constantes de terminación duplicadas (`GAME_FPS`, `NO_PROGRESS_*`, `STUCK_*`, `WRONGWAY_*`, `PIT_ZONE_MARGIN_M`, `GRACE_STEPS`); el comentario dice «alineados con environment.py». Una sola fuente. |
| 7.2.3 | P2 | `pretrain.py:build_dataset` | Reimplementa `build_obs` entera a partir de los puntos de la referencia, en vez de reutilizarla (origen de 7.1.8). |
| 7.2.4 | P2 | `obs_universal.py` y `obs_builder.py` | Pendiente, deslizamiento, guiñada, aceleraciones, patinaje, bloqueo, gas, rpm y marcha se calculan dos veces con el mismo código. |
| 7.2.5 | P2 | `main.py:_load_or_create_model` | Tres bloques `PPO.load(...)` casi idénticos con números mágicos (`learning_rate` 1e-4, `clip_range` 0,15 / 0,2, `ent_coef` 0,007 / 0,01, `vf_coef` 1,0 / 1,5). Las ramas `--model` y «continuar» son idénticas, y las de transferencia fijan parámetros distintos entre sí (`--base-model` pone `ent_coef` y no `vf_coef`; la automática, al revés). |
| 7.2.6 | P3 | `main.py`, `pretrain.py`, `environment.py` | El espacio de observación de 19 dim (`_low`), `net_arch=[256, 256, 128]` y el entorno ficticio se copian en tres sitios. |
| 7.2.7 | P3 | `eval_driver.py` y `eval_universal.py` | Dos `evaluate` con el mismo cálculo de MAE; además, `eval_driver` llama a `predict` fila a fila en vez de por lotes. |

### 7.3 Antes de usar PPO

Orden mínimo: 7.1.1–7.1.3 (el entorno no detecta atascos y los tiempos son falsos), 7.1.4
(observación con signo, probablemente pasando a `universal_v2`), 7.1.5 (ancla al BC) y 7.2.1/7.2.2
(para no volver a divergir). Cubrir cada punto con un test antes de arreglarlo.


---

## 8. Hallazgos de la sesión L7 / 55 km/h (2026-10-25)

Origen: `logs/learning/20261025T094900Z_sugo_gp_l7_banda.jsonl` (8 vueltas, ninguna graduada).

### 8.1 La parada del fine-tune se contaba como atasco (corregido)

La vuelta 1 salió limpia (0,1 % de overrides, 0 % de stuck, CTE medio 0,31 m, 242,8 s). De la 2 a la 8
el modelo conducía igual de bien, pero cada vuelta marcaba ~5 % de overrides (umbral de «limpia») y
~5 % de stuck, y tardaba ~300 s en vez de ~242 s. Reconstruido tick a tick:

1. Al cruzar meta arranca el fine-tune y `LapTransitionGuard` frena a propósito (`HOLD_BRAKE` 0,7).
   El coche queda parado en d ≈ 11 m unos 45 s.
2. `SafetyMonitor` cuenta esa parada: a los 15 s dispara `safety_stuck`, y al acabar el fine-tune el
   profesor sigue al volante unos 13 s (~800 ticks, el «5 %» de cada vuelta) hasta que los contadores
   se rearman.

**Arreglo:** `SafetyMonitor.hold(timings)` pone a cero los contadores de atasco, falta de progreso y
sentido contrario; `learn_driver` lo llama en cada tick mientras `lap_guard.active`. Test:
`test_hold_keeps_deliberate_stop_from_counting_as_stuck`. Falta confirmarlo en pista: la siguiente
vuelta tras un fine-tune debería salir con ~0 % de override.

### 8.2 Estado de la base de datos (medido)

`data/online_buffer.jsonl`: 1,8 GB, 2.109.853 filas, todas `universal_v1`, `SUGO_GP`, origen `TEACHER`.

| Dato | Valor |
| --- | --- |
| `maintain_speed` | 1.784.498 filas (**85 %**) |
| `brake_overspeed` | 226.586 (11 %) |
| `accel_straight` | 76.146 (3,6 %) |
| `recover_line` / `accel_curve_limited` / `engage_first` | 19.986 / 2.369 / 268 (< 1 % entre las tres) |
| Calidad | 0,8–1,0 en el 99,9 % de las filas |
| Filas por etapa y banda | 29 mil – 115 mil (L7/55: 114.928) |

Problemas:

- **Redundancia:** ticks a 60 Hz casi idénticos entre sí (no medido aquí; el currículo ya estima un
  ~49 % de filas casi iguales a la anterior).
- **Lentitud:** cada fine-tune relee y filtra el JSONL entero (`load_universal_dataset` además guarda la
  fila completa en `meta`), lo que alarga los ~45 s de parada.
- **Olvido entre bandas:** el filtro es etapa **y** banda exactas, y no hay ninguna comprobación de
  que las bandas ya dominadas sigan conduciendo bien tras cada fine-tune.

### 8.3 Dataset curado (puntos 1 y 2 hechos; 3 y 4 pendientes)

**Hecho (2026-10-25):** `src/curate_dataset.py` compacta el buffer en `data/curated_buffer.npz`:
calidad >= 0,9, descarta filas que apenas cambian respecto a la última conservada de su
(pista, etapa, banda) y limita `maintain_speed` al 40 %, conservando todas las razones raras.
`learn_driver` lo carga con `--curated` (por defecto `data/curated_buffer.npz`), con el mismo filtro
de etapa, banda y pista que el buffer, y le suma el `online_buffer.jsonl` nuevo.

| | Antes | Después |
| --- | --- | --- |
| Buffer | 1,8 GB, 2.153.182 filas | 9,2 MB, 159.135 filas (95.481 no-`maintain_speed`) |
| Carga para L7/55 | 27,3 s, 242.130 muestras | 1,7 s, 103.779 muestras |
| Carga para L1/60 | n/d | 1,6 s, 87.506 muestras (83.873 de la base + 3.633 curadas) |

El JSONL original se movió a `data/archive/online_buffer_raw_20261025.jsonl` (en `.gitignore`) para no
contarlo dos veces. Para volver a compactar más adelante: cerrar la sesión, `python
src/curate_dataset.py --src data/online_buffer.jsonl --out data/curated_<fecha>.npz --archive-raw` y
pasar ese fichero con `--curated` (o fusionarlo con el anterior). El script no sobrescribe una salida
existente.

Propuesta pendiente:

1. **Dataset curado compacto** (`.npz`, pocos MB) generado de una vez desde el buffer; el fine-tune lo
   carga en segundos. Es lo que más reduce el tiempo parado.
2. **Limpieza al generarlo:** submuestrear ticks casi idénticos, limitar `maintain_speed` a una
   proporción fija, conservar todas las razones raras y subir la calidad mínima a ≥ 0,9.
3. **Equilibrar por banda de velocidad y tramo de pista.** `target_speed_norm` ya es una entrada de la
   red, así que un único modelo puede cubrir 20–80 km/h si ve todas las bandas con el mismo peso; el
   filtro por etapa y banda deja de hacer falta.
4. **Calibración automática:** tras cada fine-tune, error en una vuelta de validación **por banda**;
   si una banda dominada empeora, repetir con más peso en ella.

Orden sugerido: 1 y 2 ahora; 3 y 4 cuando 55 y 60 estén estables. Cerrar la sesión de aprendizaje
antes de generar el dataset, porque el buffer sigue escribiéndose mientras corre.
