# Guía de entrenamiento — PCARS2-AI v2

Documentación operativa: modos, comandos, logs, revisión de sesiones y flujo supervisado.

**Última actualización:** 2026-08-13

---

## Resumen rápido

| Qué quieres                       | Cómo                                     |
| --------------------------------- | ---------------------------------------- |
| Lanzar entrenamiento con GUI      | `gui.bat`                                |
| Ver progreso en vivo              | `monitor.bat` (otra terminal)            |
| Curvas PPO                        | `tensorboard.bat`                        |
| Revisar sesión (o pedir análisis) | `logs/formula_rookie__sugo/metricas.csv` |
| Tests                             | `tests.bat`                              |

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

### Entrenamiento — Básicos desde cero (recomendado ahora)

```bat
entrenar.bat src\refs\sugo_ai.json 150000 --frame-skip 4 --warmup-steps 30 --basics --speed-target-kmh 20
```

- **Sin** `--model` (política nueva; no cargar checkpoints de curriculum).
- **Sin** `--curriculum` (usar `--basics`).
- En básicos, `stuck` es más permisivo: < 1.4 km/h durante ~15 s (vs 3.6 km/h / 8 s en modo completo).
- **100k–150k** pasos por sesión supervisada (no 500k de golpe).

### Continuar sesión Básicos (con checkpoint)

```bat
entrenar.bat src\refs\sugo_ai.json 100000 --frame-skip 4 --warmup-steps 30 --basics --speed-target-kmh 20 --model models\formula_rookie__sugo\pcars2_formula_rookie__sugo_XXXXX_steps
```

Sustituye `XXXXX` por el número del último `*_steps.zip` (sin `.zip` en `--model`).

### GUI (equivalente a los comandos)

```bat
gui.bat
```

1. Modo **Básicos — línea, velocidad, girar**
2. Velocidad objetivo: **20**
3. Pasos: **100000**
4. Checkpoint: **vacío** (primera sesión) o botón **Último**
5. **Iniciar entrenamiento** (PCARS 2 en pista antes)

La configuración se guarda en `v2/user_settings.json`.

### Monitor y TensorBoard

```bat
monitor.bat
```

Desde la GUI: botones **Monitor** y **TensorBoard**.

TensorBoard (opcional):

```bat
..\.venv\Scripts\python.exe -m tensorboard.main --logdir logs\formula_rookie__sugo
```

### Tests

```bat
tests.bat
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
move models\formula_rookie__sugo models\formula_rookie__sugo_backup_%DATE:~-4%%DATE:~3,2%%DATE:~0,2%
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
Ep 42 | rew=... | len=... | fin=stuck
[SpeedTarget] ✓ avg=22.1 km/h ≈ objetivo 20.0 km/h → nuevo objetivo: 25.0 km/h
[Env] Modo BÁSICOS: línea + velocidad objetivo + girar + acciones suaves.
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
PCARS2-AI/
  gui.bat                 ← GUI
  entrenar.bat            ← CLI (igual que antes, nuevos flags)
  monitor.bat
  tensorboard.bat
  tests.bat
  v2/
    config.py             ← modos y presets (ampliar aquí)
    launcher.py           ← construye comando y lanza procesos
    gui.py
    user_settings.json    ← se crea al entrenar
  logs/formula_rookie__sugo/
    metricas.csv
  models/formula_rookie__sugo/
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
1. Archivar modelo/CSV curriculum (si aplica)
2. gui.bat → Básicos, 20 km/h, 100k, sin checkpoint
3. monitor.bat en otra ventana
4. Al terminar: revisar metricas.csv
5. Decidir: +100k | subir a 25 km/h | ajustar código
```

---

## Referencia cruzada

- [METRICAS.md](METRICAS.md) — columnas del CSV y métricas PPO
- [DEPENDENCIAS.md](DEPENDENCIAS.md) — Python, paquetes, tests
