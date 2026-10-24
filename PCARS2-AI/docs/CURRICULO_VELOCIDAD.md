# Currículo de velocidad — L1→L7 por banda

**Objetivo:** dominar línea, lógica y técnica a cada ritmo antes de subir velocidad.
No optimizar tiempo de vuelta hasta conseguir vueltas limpias en todas las bandas.

**Estado:** F5 aprendizaje online (`aprender.bat` / GUI → Aprendizaje BC)
**Actualizado:** 2026-10-10

---

## Idea en una frase

Completa **L1→L7** en la banda **20 km/h**. Prueba **Hybrid** en esa banda. Sube a **30 km/h** y
repite L1→L7. Así hasta **80 km/h**.

---

## Bandas de velocidad

| Banda   | Uso                                       |
| ------- | ----------------------------------------- |
| **20**  | Primera banda — base del teacher y del BC |
| **30**  | Ritmo intermedio                          |
| **40**  | Ritmo medio-alto                          |
| **50**  | Ritmo alto                                |
| **60**  | Ritmo muy alto                            |
| **70**  | Curvas empiezan a limitar al teacher      |
| **80**  | Máximo del currículo actual               |

La **banda** fija el objetivo del teacher (`speed_target_kmh`) durante toda la sesión L1–L7.
El buffer online guarda `learn_stage` + `speed_band_kmh` para que el fine-tune solo use datos de la
etapa y banda actuales.

---

## Etapas L1→L7 (en cada banda)

| Etapa                 | Enfoque                                        | Graduar                            |
| --------------------- | ---------------------------------------------- | ---------------------------------- |
| **L1** línea          | Trazado y CTE                                  | 2 vueltas limpias                  |
| **L2** velocidad      | Ritmo estable (vel. media escala con la banda) | 2 vueltas limpias                  |
| **L3** frenar         | Uso de freno                                   | 2 vueltas limpias                  |
| **L4** combinado      | Línea + freno + ritmo                          | 2 vueltas limpias                  |
| **L5** rápido         | Menos intervención del teacher                 | 3 vueltas limpias                  |
| **L6** sostenido      | Estabilidad en varias vueltas                  | 2 vueltas limpias                  |
| **L7** banda dominada | Validar la banda actual                        | 3 vueltas limpias → **sube banda** |

Tras dominar **L7**, el sistema reinicia en **L1** con la siguiente banda (p. ej. 20→30 km/h).

---

## Flujo operativo (hilo a seguir)

### Preparación (una vez o al cambiar referencia)

1. `record.bat` — grabar teacher **≥3 vueltas** (sin parar en meta; mismo JSONL) →

   `data/universal_teacher.jsonl`

2. **`entrenar_bc.bat`** — BC offline → `models/universal_bc.pt` (**no saltar** antes del primer

   `aprender`)

3. `eval_bc.bat` — comprobar MAE antes de pista (opcional)

Detalle record / marchas / qué entra al JSONL:
[TEACHING_MARCHAS_Y_DATASET.md](TEACHING_MARCHAS_Y_DATASET.md)

### Por cada banda (20 → 30 → 40 → 50 → 60 → 70 → 80)

1. **GUI** → pestaña *Aprendizaje (BC)*
   - Banda: p. ej. `20`
   - Etapa: `L1` (o la última guardada en `v2/user_learn_settings.json`)
2. **▶ Aprender en pista** (`aprender.bat`)
   - BC conduce, teacher corrige, fine-tune cada **N** vueltas (`learn_every` en

        `v2/user_learn_settings.json`, p. ej. **2**)

   - Cada fine-tune mezcla **`base-dataset`** completo (`universal_teacher.jsonl`) +

        `data/online_buffer.jsonl` (buffer filtrado por etapa/banda)

   - Al cruzar meta: freno corto (`settle`) y, si toca, espera mientras entrena en segundo plano
   - Avanza de etapa solo con vueltas **limpias** seguidas (mínimo **2** en L1; no basta con 2

        vueltas “contadas” si no son limpias)

3. Al completar **L7** en la banda → sube automáticamente a la siguiente banda y vuelve a **L1**
4. **Probar Hybrid** en la misma banda cuando L6–L7 estén estables (no entrena; solo valida)
5. Repetir en la siguiente banda

### Cuándo usar Hybrid / Autónomo

| Modo         | Cuándo                                | Entrena        |
| ------------ | ------------------------------------- | -------------- |
| **Aprender** | Siempre que quieras mejorar el BC     | Sí (fine-tune) |
| **Hybrid**   | Tras dominar L7 en una banda          | No             |
| **Autónomo** | Tras varias vueltas limpias en Hybrid | No             |

No dejes **Aprender** horas en L7: riesgo de sobreajuste y buffer enorme. Ciclo corto: Aprender
L6–L7 ↔ Hybrid.

---

## GUI — controles

| Control                           | Significado                                                        |
| --------------------------------- | ------------------------------------------------------------------ |
| **Banda (km/h)**                  | Velocidad objetivo del teacher en toda la sesión L1–L7             |
| **Etapa (L1→L7)**                 | Fase del currículo; se guarda entre sesiones                       |
| **Override velocidad** (avanzado) | Solo si necesitas un valor fino distinto de la banda; `0` = normal |

Persistencia: `v2/user_learn_settings.json` (`stage_id`, `speed_band_kmh`, `dataset_path`,
`model_path`, `learn_every`, referencia).

Rutas por defecto: `data/universal_teacher.jsonl`, `models/universal_bc.pt` (desde carpeta
`PCARS2-AI/`).

---

## CLI

```bat
```

| Flag             | Efecto                                        |
| ---------------- | --------------------------------------------- |
| `--stage`        | Etapa inicial (omitir = guardada)             |
| `--speed-band`   | Banda fija km/h (omitir = guardada o 20)      |
| `--speed-target` | Override fino; tiene prioridad sobre la banda |

---

## Criterio de vuelta limpia

Por etapa (ver `learning_curriculum.py`):

- CTE medio ≤ umbral de la etapa
- Pocas intervenciones del teacher (overrides)
- En L2/L6: velocidad media mínima escalada a la banda
- En L3+: uso mínimo de freno cuando aplica

El informe HTML en `logs/learning/` muestra objetivos, tiempos y progreso.

---

## ¿Cuándo sé que terminé una etapa? (ejemplo L1)

El sistema **avanza solo** cuando cumples las vueltas limpias seguidas de la etapa. No tienes que
cambiar la etapa manualmente en la GUI.

### L1 — qué cuenta como vuelta limpia

| Criterio                               | Límite en L1          |
| -------------------------------------- | --------------------- |
| CTE medio de la vuelta                 | ≤ **4,5 m**           |
| Intervenciones del teacher (overrides) | ≤ **12 %** del tiempo |
| Off-track                              | ≤ **8 %**             |
| Stuck                                  | ≤ **5 %**             |

En L1 **no** se exige freno ni velocidad media mínima (eso entra en L2 y L3).

### Cómo graduar L1

Hacen falta **2 vueltas limpias seguidas** (`clean_laps_required = 2`).

1. Primera vuelta limpia → consola: `clean_streak=1` y mensaje `Etapa l1_linea: 1/2 vueltas limpias`
2. Segunda vuelta limpia seguida → consola: `*** Graduado a l2_velocidad (L2 — Velocidad objetivo)

   ***`

3. La etapa queda guardada en `v2/user_learn_settings.json` (`stage_id` → `l2_velocidad`)

Si una vuelta **no** es limpia, verás `revisar: CTE…` o `overrides…` y `clean_streak=0` (el contador
vuelve a cero).

### Vuelta contada vs vuelta limpia

- **Contada:** al cruzar meta (incremento de `current_lap` **o** reset de `lap_distance` en UDP).

  Verás `[Learn] Vuelta N | …`.

- **Limpia:** la misma vuelta además cumple CTE, overrides, etc. Si ves `revisar: …` la vuelta **sí

  contó** pero no suma al `clean_streak`.

Si frenas en meta pero no aparece `Vuelta N`, revisa UDP; el detector usa la misma señal que el
freno de meta.

### Señales en consola (tras cada vuelta)

Al arrancar y **después de cada vuelta** se reimprime una tabla fija:

```text
```

Línea detallada de la vuelta que acaba de cerrar:

```text
```

`ovr%` / `off%` / `stk%` son **porcentaje de ticks de esa vuelta**, no contadores acumulados de
sesión.

### Señales en el HTML (`logs/learning/`)

- Cabecera con **Banda: 20 km/h** (o la banda activa)
- Tabla **Objetivos de la etapa** (CTE, overrides, vueltas limpias)
- Columna **Limpia** en tiempos por vuelta

### Vueltas limpias por etapa (todas las bandas)

| Etapa     | Vueltas limpias seguidas para graduar   |
| --------- | --------------------------------------- |
| L1–L4, L6 | **2**                                   |
| L5, L7    | **3**                                   |

L7 además puede **subir la banda** automáticamente (20→30→…→60) y reiniciar en L1.

---

## ¿Cuándo parar la sesión?

| Situación                             | Qué hacer                                                                                 |
| ------------------------------------- | ----------------------------------------------------------------------------------------- |
| **Graduaste** (mensaje `Graduado a…`) | Puedes seguir en la nueva etapa o parar (Ctrl+C); el progreso queda guardado              |
| **Sesión corta**                      | Ctrl+C cuando quieras; la próxima vez continúas donde lo dejaste                          |
| **Muchas vueltas sin limpiar**        | Tras **5–8 vueltas** sin 2 limpias seguidas en L1, para y revisa el HTML (CTE, overrides) |
| **L1 ya dominado**                    | No hace falta quedarse horas en L1; con 2 limpias basta                                   |
| **L7 dominada**                       | No entrenes horas en Aprender; prueba **Hybrid** y cicla Aprender ↔ Hybrid                |

**Regla práctica:** Aprender hace fine-tune cada `learn_every` vueltas (no necesariamente cada
vuelta). Usa sesiones orientadas a **graduar etapa** (2–3 vueltas limpias seguidas en L1), no
maratones de 50 vueltas en un solo circuito sin equilibrar el dataset base (ver
[TEACHING_MARCHAS_Y_DATASET.md](TEACHING_MARCHAS_Y_DATASET.md)).

### Empezar el currículo desde cero (si tenías otra etapa guardada)

1. GUI → Banda **20**
2. Etapa **L1** (`l1_linea`)
3. **▶ Aprender en pista**
4. Para cuando veas graduación a L2, o antes con Ctrl+C si no mejoras

---

## Archivos clave

| Archivo                         | Rol                                                 |
| ------------------------------- | --------------------------------------------------- |
| `src/learning_curriculum.py`    | Etapas L1–L7, bandas, graduación                    |
| `src/learn_driver.py`           | Bucle online + fine-tune                            |
| `src/learn_progress.py`         | Guardar etapa y banda                               |
| `data/universal_teacher.jsonl`  | Dataset base del teacher (replay en cada fine-tune) |
| `data/online_buffer.jsonl`      | Muestras con `learn_stage` + `speed_band_kmh`       |
| `models/universal_bc.pt`        | Pesos BC (se sobrescribe al entrenar/aprender)      |
| `v2/gui.py`                     | Selector banda + etapa                              |
| `scripts/analyze_jsonl_gear.py` | Diagnóstico rápido del JSONL de record              |

---

## Siguiente paso después del currículo

Cuando **80 km/h** y **L7** estén dominados:

1. Hybrid estable en 80 km/h
2. Autónomo con supervisión
3. Multi-pista: JSONL curados por circuito + `entrenar_bc` multi-dataset (ver

   [TEACHING_MARCHAS_Y_DATASET.md](TEACHING_MARCHAS_Y_DATASET.md))

4. RL fine-tune (PPO) solo si BC es estable — ver `ENTRENAMIENTO.md`

### Después (no ahora): condiciones avanzadas

Temperatura, combustible, desgaste, setup, diferenciales, etc. **solo cuando la base anterior sea
sólida**.
Plan por capas (qué viene en UDP, qué es metadata de sesión, orden de introducción):

##### [ROADMAP_CONDICIONES.md](ROADMAP_CONDICIONES.md)

---

*Ver también:* [TEACHING_MARCHAS_Y_DATASET.md](TEACHING_MARCHAS_Y_DATASET.md),
[VALIDACION_TEACHING_SUGO.md](VALIDACION_TEACHING_SUGO.md), [ENTRENAMIENTO.md](../ENTRENAMIENTO.md),
[ROADMAP_CONDICIONES.md](ROADMAP_CONDICIONES.md)
