# Guía de entrenamiento — PCARS2-AI v2

Documentación operativa: modos, comandos, logs, revisión de sesiones y flujo supervisado.

**Última actualización:** 2026-10-25

---

## Resumen rápido

| Qué quieres                       | Cómo                                                                                                       |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Lanzar entrenamiento con GUI      | `gui.bat`                                                                                                  |
| Teaching Driver (reglas)          | `teach.bat` o GUI → Teaching Driver                                                                        |
| Validación Sugo F1–F4 + HTML      | `validar_f1.bat` … `validar_f4.bat` — [docs/VALIDACION_TEACHING_SUGO.md](docs/VALIDACION_TEACHING_SUGO.md) |
| Regenerar HTML de sesión          | `report_sesion.bat logs\teaching\sesion.jsonl`                                                             |
| Grabar demostraciones TEACHER     | `record.bat` — [docs/TEACHING_MARCHAS_Y_DATASET.md](docs/TEACHING_MARCHAS_Y_DATASET.md)                    |
| Entrenar BC universal             | `entrenar_bc.bat` → `models/universal_bc.pt`                                                               |
| Evaluar BC offline                | `eval_bc.bat`                                                                                              |
| Probar BC en pista (HTML)         | `imitar_bc.bat`                                                                                            |
| Aprender online (L1–L7 por banda) | `aprender.bat` — [docs/CURRICULO_VELOCIDAD.md](docs/CURRICULO_VELOCIDAD.md)                                |
| Hybrid / autonomía                | `imitar_hybrid.bat` / `imitar_autonomo.bat`                                                                |
| Entrenar BC clásico (PPO obs)     | `pretrain.bat` con `--dataset`                                                                             |
| BC / Hybrid / Autonomous en pista | GUI → Teaching Driver                                                                                      |
| Ver progreso en vivo              | `monitor.bat` (otra terminal)                                                                              |
| Curvas PPO                        | `tensorboard.bat`                                                                                          |
| Revisar sesión (o pedir análisis) | `logs/formula_rookie__sugo/metricas.csv`                                                                   |
| Tests                             | `tests.bat`                                                                                                |

---

## Flujo Teaching → Imitation → RL

Ruta recomendada antes de depender solo de PPO:

1. **Referencia** — grabar línea con `reference_recorder.py` (prerrequisito).
2. **Teacher** — `teach.bat` conduce a 20 km/h con reglas explicables.
3. **Record** — `record.bat` graba ≥3 vueltas limpias en `data/universal_teacher.jsonl` (puedes **no

   parar** en meta; sin límite de vueltas hasta Ctrl+C).

4. **BC universal** — **obligatorio antes de aprender en pista:**

   ```bat
   ```

   Equivale a `pretrain_universal.py` → `models/universal_bc.pt`.

5. **Eval** — comprobar MAE antes de pista:

   ```bat
   ```

6. **Aprender online** — `aprender.bat` (L1→L7 por banda; ver

   [docs/CURRICULO_VELOCIDAD.md](docs/CURRICULO_VELOCIDAD.md)).

7. **BC Drive / Hybrid** — `imitar_bc.bat` / `imitar_hybrid.bat` o GUI; teacher como fallback.
8. **Autonomous** — tras currículo estable o `imitar_autonomo.bat`.
9. **PPO fine-tune** — cuando BC sea estable. Antes: base compactada y reetiquetada sin solape de
   gas y freno, un solo eje de pedal, observación ampliada y compensación del volante en el
   entorno (prerrequisitos completos en
   [docs/ROADMAP_CONDICIONES.md](docs/ROADMAP_CONDICIONES.md), «Capa 4»):

   ```bat
   ```

### Modos Teaching Driver

| Modo         | Script                                  | Quién conduce         |
| ------------ | --------------------------------------- | --------------------- |
| `teacher`    | `teaching_driver.py`                    | Reglas puras          |
| `record`     | `teaching_driver.py --mode record`      | Reglas + JSONL        |
| `bc_drive`   | `imitation_driver.py`                   | BC + fallback teacher |
| `hybrid`     | `imitation_driver.py --mode hybrid`     | Mezcla BC/teacher     |
| `autonomous` | `imitation_driver.py --mode autonomous` | BC (emergencia solo)  |

Criterios de validación (teacher a 20 km/h): `avg_cte` < 5 m, vueltas completas,
`pct_stuck` < 20%. Para BC: MAE steering < 0.15, MAE pedales < 0.20.

---

## Política universal (multi-pista + intención)

El teacher enseña **cuándo / por qué / cómo** actuar. La política universal aprende
`obs_geométrico + intención → acción`, válido en cualquier pista con su referencia local.

### Grabar dataset universal

```bat
```

Equivale a `teaching_driver.py --mode record --universal --reference src/refs/sugo_ai.json
--speed-target 20`.

Cada muestra incluye:

- `obs_schema: universal_v1` (17 features; geometría relativa, sin “metros de vuelta” en el obs)
- `teacher_reason` + `reason_id` + `rule: { when, why, how }`
- `track_name` (p. ej. `SUGO_GP`)

**Vueltas:** `--max-laps 0` (sin tope). Recomendado **≥ 3 vueltas** continuas en el mismo JSONL.
**Off-track:** el teacher recupera en pista; esas muestras **no** entran al JSONL con safety activa
(ver [docs/TEACHING_MARCHAS_Y_DATASET.md](docs/TEACHING_MARCHAS_Y_DATASET.md)).

**Marchas:** auto-shift ON; lógica RB/LB documentada en el mismo doc (retroceso en 1ª sin RB, neutro
→ `engage_first`).

Repite en **2–3 pistas** para generalizar. Estrategia multi-pista con JSONL “limpios” por circuito:
mismo doc.

### Entrenar BC universal

```bat
```

O varios datasets (concatena por número de muestras; equilibrar pistas a mano):

```bat
```

Salida habitual: **`PCARS2-AI/models/universal_bc.pt`** (ejecutar `.bat` desde `PCARS2-AI/`).
El `.pt` **no** guarda vueltas ni referencias; solo pesos entrenados con los JSONL usados.

### Evaluar

```bat
```

### Conducir en pista nueva

Solo necesitas **referencia local** de esa pista (para CTE/curvatura). El modelo ya aprendió las
reglas.
Válido para cualquier circuito grabado con el mismo enfoque (coche/setup/condiciones similares al
dataset).

**Futuro (no implementar aún):** temperatura, combustible, desgaste, setup, diferenciales…
Plan por capas tras dominar el currículo L1→L7:
[docs/ROADMAP_CONDICIONES.md](docs/ROADMAP_CONDICIONES.md)

```bat
```

Modo `autonomous`: predice intención desde obs (sin teacher en cada frame; teacher solo en
emergencia).

---

## Fases de entrenamiento (plan actual)

### Fase 0 — Básicos (ahora)

**Objetivo:** conducir en línea a **20 km/h**, sin atascarse. Subir +5 km/h cuando mantenga el
ritmo.

| Componente | Qué aprende                                                  |
| ---------- | ------------------------------------------------------------ |
| Línea      | Penalización CTE (salir del trazado)                         |
| Velocidad  | Objetivo `--speed-target-kmh` (empieza en 20)                |
| Girar      | Penalización heading error                                   |
| Acciones   | Gas/freno/volante suaves (sin premio enorme por gas a fondo) |

**Criterios para pasar a Fase 1:**

- `avg_speed_kmh` ~18–25 km/h estable
- `avg_cte` < 8 m y bajando
- `ep_len_mean` > 120–150 y subiendo
- `pct_stuck` < 50%

### Fase 1 — Subir velocidad

Mantener modo Básicos; el objetivo sube automáticamente (+5 km/h cada 10k pasos si el promedio está
en ±10 km/h del target). O subir manualmente en la GUI (25 → 30 → 35).

### Fase 2 — Reward completa

Solo cuando mantenga **35+ km/h en línea** de forma habitual. Modo **Completo** en la GUI o quitar
`--basics`.

---

## Comandos

### Archivar sesión anterior y empezar desde 0

```bat
```

Mueve `models/formula_rookie__sugo/` y `logs/formula_rookie__sugo/` a carpetas `*_archive_FECHA/`.
También archiva `models/pretrained.zip` si existe.

### Entrenamiento — Básicos desde cero (recomendado ahora)

```bat
```

- **Sin** `--model` y con **`--fresh`** (política nueva; no carga checkpoints ni pretrained).
- En la GUI: marca **Desde cero (--fresh)**. Sin marcar y sin checkpoint → auto-reanuda (max steps →

  _final).

- **Último** desmarca “Desde cero” y rellena el checkpoint con más pasos.
- **Sin** `--curriculum` (usar `--basics`).
- En básicos, `stuck` es más permisivo: < 1.4 km/h durante ~15 s (vs 3.6 km/h / 8 s en modo

  completo).

- **100k–150k** pasos por sesión supervisada (no 500k de golpe).

### Continuar sesión Básicos (con checkpoint)

```bat
```

Sustituye `XXXXX` por el número del último `*_steps.zip` (sin `.zip` en `--model`).

### GUI (equivalente a los comandos)

```bat
```

1. Modo **Básicos — línea, velocidad, girar**
2. Velocidad objetivo: **20**
3. Pasos: **100000**
4. Checkpoint: **vacío** (primera sesión) o botón **Último**
5. **Iniciar entrenamiento** (PCARS 2 en pista antes)

La configuración se guarda en `v2/user_settings.json`.

### Monitor y TensorBoard

```bat
```

Desde la GUI: botones **Monitor** y **TensorBoard**. El monitor muestra **ETA** y barra de pasos si
indicas `--timesteps` (la GUI lo pasa automáticamente). Ver [Planificar pasos y
tiempo](#planificar-pasos-y-tiempo).

TensorBoard (opcional):

```bat
```

### Tests

```bat
```

---

## Qué cambió respecto al curriculum viejo

| Antes                                           | Ahora (Básicos)                           |
| ----------------------------------------------- | ----------------------------------------- |
| `--curriculum`                                  | `--basics`                                |
| Gas a fondo premiado (+3 throttle)              | Línea + velocidad objetivo + girar        |
| `--speed-target-kmh` no aplicaba con curriculum | **Obligatorio usar con básicos** (ej. 20) |
| Checkpoint ~970k curriculum                     | **Empezar sin `--model`**                 |
| Sesiones 500k                                   | Sesiones **100k–150k** + revisión         |

---

## Archivar modelo viejo y empezar limpio

```bat
```

Crea carpetas nuevas al entrenar. No borrar sin `move` (archivo por si hay que comparar).

---

## Logs — qué existe y dónde

| Log                   | Ruta                                           | Uso                                                           |
| --------------------- | ---------------------------------------------- | ------------------------------------------------------------- |
| **CSV principal**     | `logs/formula_rookie__sugo/metricas.csv`       | Análisis entre sesiones; **pasar este archivo para revisión** |
| TensorBoard           | `logs/formula_rookie__sugo/PPO_1/events.*`     | Curvas PPO en navegador (opcional)                            |
| Consola entrenamiento | Ventana cmd del entrenamiento                  | `fin=stuck`, `[SpeedTarget]`, errores                         |
| Config GUI            | `v2/user_settings.json`                        | Qué comando se lanzó                                          |
| Checkpoints           | `models/formula_rookie__sugo/*.zip`            | Continuar entrenamiento                                       |
| Normalización         | `models/formula_rookie__sugo/vecnormalize.pkl` | Se recrea al entrenar; no mezclar con reward distinto         |

### `metricas.csv`

- Se escribe **cada 2048 pasos** (un rollout PPO), no cada episodio.
- Al **iniciar una sesión nueva**, el archivo se **reescribe** (no se append). Archiva el CSV viejo

  antes de una fase nueva.

- Columnas detalladas: ver [METRICAS.md](METRICAS.md).

### Consola — líneas útiles

```text
```

`fin=` = razón de fin de episodio: `stuck`, `no_progress`, `wrong_way`, `lap_done`, `pit_box`,
`timelimit`.

---

## Qué log pasar para revisión (IA / análisis)

### Imprescindible

`logs/formula_rookie__sugo/metricas.csv`

En Cursor: `@PCARS2-AI/logs/formula_rookie__sugo/metricas.csv`

### Añadir en el mensaje

1. **Modo:** Básicos 20 km/h, ¿desde 0 o con checkpoint?
2. **Pasos pedidos** (ej. 100k)
3. **Impresión** (opcional): “parece que no avanza”, “veo vueltas”, etc.

### Opcional (si algo falla)

- Últimas líneas de la consola de entrenamiento
- `v2/user_settings.json`

**No hace falta** pasar TensorBoard ni checkpoints.

### Cuándo pedir revisión

| Momento        | Pasos en CSV |
| -------------- | ------------ |
| Primera mirada | ~50k–100k    |
| Fin de sesión  | 100k–150k    |

---

## Señales en modo Básicos (20 km/h)

| Métrica           | Bueno                    | Malo                    |
| ----------------- | ------------------------ | ----------------------- |
| `avg_speed_kmh`   | 18–25 km/h               | < 15 o > 40 sin control |
| `avg_cte`         | < 8 m, bajando           | > 12 m constante        |
| `ep_len_mean`     | > 120 y sube             | clavado ~80             |
| `pct_stuck`       | < 50%                    | > 70% siempre           |
| `pct_no_progress` | bajando                  | > 60% siempre           |
| `pct_lap_done`    | > 0% en algunos rollouts | 0% tras 100k            |

La recompensa (`ep_rew_mean`) en Básicos **no se compara** con la del curriculum viejo (distinta
función de reward).

---

## Estructura v2

```text
```

### Modos en `v2/config.py`

| ID                   | Label                   | Flags CLI                 |
| -------------------- | ----------------------- | ------------------------- |
| `basico`             | Básicos                 | `--basics` + speed target |
| `curriculum`         | Curriculum legacy       | `--curriculum`            |
| `completo`           | Reward completa         | —                         |
| `completo_velocidad` | Completa + speed target | `--speed-target-kmh`      |
| `personalizado`      | Manual                  | tú eliges todo            |

---

## Flujo supervisado recomendado

```text
```

---

## Flujo de datos y UDP (cuello de botella)

El entrenamiento es **síncrono** con PCARS2: PPO no avanza más rápido que el juego.

```text
```

### Qué hace el entorno (desde 2026-09-13)

1. **Drena** la cola UDP (`drain`) para no consumir paquetes viejos en ráfaga.
2. **Espera** un `CAR_PHYSICS` con posición/velocidad distinta al último frame aceptado.
3. Solo entonces incrementa `_step_count` (contadores `stuck` / `no_progress`).

Así el FPS del CSV refleja **pasos PPO reales**, no timeouts ni backlog del socket.

### Métricas UDP en `metricas.csv`

| Columna           | Interpretación                                         |
| ----------------- | ------------------------------------------------------ |
| `udp_physics`     | Frames de física aceptados en el rollout               |
| `pct_udp_timeout` | Alto → juego en pausa, menú, o sin UDP                 |
| `pct_udp_backlog` | Alto → antes había cola UDP (FPS artificialmente alto) |

### `frame_skip`

| Valor               | Efecto                                                    |
| ------------------- | --------------------------------------------------------- |
| **4** (defecto GUI) | Más estable; ~6 pasos PPO/s con juego a 25 Hz             |
| **2**               | 2× pasos/hora; volante más reactivo; prueba si CTE oscila |

### FPS esperado

No confundir con rendimiento GPU. Con `frame_skip=4` y juego a ~25 Hz:

```text
```

Si ves **FPS >> 8** con `frame_skip=4`, revisa `pct_udp_backlog` (cola UDP). Si **FPS < 3**
y `pct_udp_timeout` alto, el juego no está enviando telemetría (pausa, menú, alt-tab).

---

## Planificar pasos y tiempo

El campo **Pasos (timesteps)** en la GUI y el flag `--timesteps` de `main.py` son el **total
acumulado de SB3**, no «pasos extra de esta tanda».

| Situación                       | Qué poner en GUI                                                             |
| ------------------------------- | ---------------------------------------------------------------------------- |
| Primera sesión desde 0          | `150000` = entrena hasta 150k y para                                         |
| Continuar sin checkpoint manual | Pasos **totales** deseados (ej. `450000`); desmarca **Desde cero**           |
| Continuar con `--model`         | El contador sigue desde el checkpoint; el objetivo sigue siendo el **total** |

El monitor calcula: `restantes = objetivo − total_timesteps` del CSV y `ETA = restantes /
FPS_medio`.

### Fórmula rápida

```text
```

Usa el **FPS medio** del monitor (últimos rollouts). Con `frame_skip=4` suele ser **4–6**;
para planificar usa **5** (conservador) o mira `udp_physics` en el CSV.

### Tabla de referencia (pasos que caben en X horas)

| Horas | @ 15 FPS | @ 18 FPS | @ 20 FPS | @ 24 FPS |
| ----- | -------- | -------- | -------- | -------- |
| 2 h   | 108k     | 130k     | 144k     | 173k     |
| 6 h   | 324k     | 389k     | 432k     | 518k     |
| 8 h   | 432k     | 518k     | 576k     | 691k     |
| 10 h  | 540k     | 648k     | 720k     | 864k     |
| 15 h  | 810k     | 972k     | 1,08 M   | 1,30 M   |
| 23 h  | 1,24 M   | 1,49 M   | 1,66 M   | 1,99 M   |

### Ejemplo: revisión a las 9:00 (sesión de ~6 h)

Supón que empiezas o continúas con ~**40k** pasos y el FPS medio es ~**20**:

```text
```

| Objetivo GUI | FPS ~ | Termina ~ |
| ------------ | ----- | --------- |
| **450 000**  | 18    | 8:45–9:00 |
| **480 000**  | 20    | 9:00–9:15 |
| **400 000**  | 15    | ~8:30     |

**Recomendación habitual:** `450 000` si el monitor marca 17–22 FPS.

### Ejemplo: dejarlo toda la noche (tras revisar por la mañana)

Tras la revisión, mira el último `total_timesteps` del CSV (ej. ~450k a las 9:00). La nueva meta
es **ese número + pasos de la noche**:

| Hasta… (aprox.) | Horas desde 9:00 | Pasos extra @ 18 FPS | Si acabas en ~450k → pon |
| --------------- | ---------------- | -------------------- | ------------------------ |
| Medianoche      | 15 h             | ~972k                | **1 420 000**            |
| 07:00           | 22 h             | ~1,43 M              | **1 880 000**            |
| 08:00           | 23 h             | ~1,49 M              | **1 950 000**            |

**Recomendación nocturna (hasta ~8:00):** `2 000 000` total — redondo y con margen si baja el FPS.

### Checklist antes de dejar el PC

1. **Desde cero** desmarcado si quieres continuar (checkpoint vacío = auto-reanuda el último

   `*_steps.zip`).

2. **Pasos** = total objetivo calculado arriba (no solo los de la noche).
3. **save_freq** 10 000 (defecto GUI) → checkpoint cada ~8–10 min a 20 FPS.
4. PCARS2 en pista; **Monitor** abierto (ETA y barra de pasos).
5. Anota la hora de inicio y el objetivo para comparar al volver.

### Qué decidir en la revisión (ej. 9:00)

Mira `metricas.csv` (últimas filas) y `pct_stuck`, `avg_speed_kmh`, `ep_len_mean`:

| Señal                                                    | Acción                                                                                           |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `pct_stuck` < 50%, speed ~15–25 km/h, `ep_len_mean` sube | Seguir: nueva meta (ej. +150k o noche con `2 000 000`)                                           |
| `pct_stuck` > 80% tras 50k+ sin mejora                   | Parar: grabar IA (`reference_recorder --source ai`) + `pretrain.bat`, luego RL **sin** `--fresh` |
| Regresión clara (speed cae, stuck sube)                  | Cargar checkpoint **anterior** con mejor `avg_speed`, no el último                               |

Los criterios detallados de Fase 0 están en [Señales en modo
Básicos](#señales-en-modo-básicos-20-kmh)
y en [METRICAS.md](METRICAS.md).

---

## Referencia cruzada

- [docs/TEACHING_MARCHAS_Y_DATASET.md](docs/TEACHING_MARCHAS_Y_DATASET.md) — marchas, record, JSONL

  vs `.pt`, multi-pista

- [docs/CURRICULO_VELOCIDAD.md](docs/CURRICULO_VELOCIDAD.md) — aprender L1→L7 por banda
- [docs/VALIDACION_TEACHING_SUGO.md](docs/VALIDACION_TEACHING_SUGO.md) — validación teacher F1–F4
- [METRICAS.md](METRICAS.md) — columnas del CSV y métricas PPO
- [DEPENDENCIAS.md](DEPENDENCIAS.md) — Python, paquetes, tests
