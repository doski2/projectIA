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
> Pendiente de la sección 3: `learn_driver.run` (resto), `imitation_driver.run`, `main.train`, `session_report.write_html_replay`
> y el bucle de `teaching_driver.run` (sin tests; requieren un entorno falso).
> Pendiente: 5.1 (commit), 1.4–1.5, 2.6, 2.9, sección 3 (refactor de `run`/`train`) y 5.2–5.6.

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
| 5.1 | P1 | Hay cambios sin commit en 9 ficheros (`auto_shift`, `lap_transition`, `learn_driver`, `pcars2_gear`, tests, `Tareas.txt`, `fix_markdownlint.py`). Commitear tras revisar. |
| 5.2 | P2 | `gemini-code-1777834144518.md` (raíz, 200 KB): volcado de una conversación, parece ajeno al proyecto. Moverlo a `docs/archivo/` o borrarlo. |
| 5.3 | P2 | `Tareas.txt` mezcla lista de fases con una nota suelta (`pendiente: l2`). Pasar a `docs/ROADMAP_CONDICIONES.md` o a issues. |
| 5.4 | P3 | `requirements.txt`: añadir `ruff` en dependencias de desarrollo y un `pyproject.toml` con su configuración (C901 en 15, ignorar PLW2901 si se prefiere). |
| 5.5 | P3 | 198 `print(` en `src`: migrar a `logging` (niveles y salida a fichero) manteniendo la salida de consola en los CLI. |
| 5.6 | P3 | Mojibake en consola Windows (`cuerpo id�ntico`): forzar `PYTHONUTF8=1` en los `.bat`. |

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
