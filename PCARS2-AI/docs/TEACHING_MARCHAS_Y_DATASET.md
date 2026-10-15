# Teaching — marchas, recuperación y datasets

**Estado:** alineado con `pcars2_gear.py`, `auto_shift.py`, `teacher_controller.py` (2026-10).

Documenta el comportamiento en **`record.bat`** / **`teach.bat`** y cómo afecta al JSONL y al BC.

---

## Semántica PCARS2 (manual)

| Botón            | Efecto en marchas de avance   |
| ---------------- | ----------------------------- |
| **RB**           | Subir marcha                  |
| **LB**           | Bajar marcha                  |
| **RB en neutro** | Enganchar **1ª** (con gas)    |

Por eso la lógica del proyecto **no** usa RB para “bajar a 1ª” desde 2ª–6ª.

---

## Capas de lógica (sin duplicar responsabilidades)

| Función / módulo                | Quién la usa   | Rol                                                                  |
| ------------------------------- | -------------- | -------------------------------------------------------------------- |
| `should_rb_to_first`            | `auto_shift`   | Solo **neutro** o marcha UDP **inválida** → RB                       |
| `should_downshift_toward_first` | `auto_shift`   | Marcha **> 1** a velocidad teaching → **LB**                         |
| `backward_allows_rb_shift`      | `auto_shift`   | Retroceso longitudinal: RB **solo** si no hay 1..N enganchada        |
| `needs_gear_engagement`         | **teacher**    | Etiqueta y pedales `engage_first` hasta `gear == 1`                  |
| `throttle_for_shift`            | `auto_shift`   | En neutro, gas mínimo para RB aunque el reason no sea `engage_first` |

### Retroceso sin marcha atrás real

Si `local_velocity` va hacia atrás pero UDP sigue en **1ª..N**, pulsar RB **subía** marcha
(1→2→…→neutro).
**Corrección:** en retroceso con marcha de avance el teacher solo **frena** (`safety_reverse`);
`auto_shift` **no** pulsa RB/LB.

### Neutro

- Teacher: **`engage_first`** (gas ~0,45, freno 0) mientras `gear <= 0`.
- No se “suelta” `engage_first` por velocidad en neutro (evita quedar en N con `accel_straight` y

  poco gas).

---

## `record.bat` — vueltas y paradas

| Pregunta          | Respuesta                                                                     |
| ----------------- | ----------------------------------------------------------------------------- |
| ¿Cuántas vueltas? | **Sin límite** (`--max-laps 0`). Recomendado **≥ 3 vueltas limpias** para BC. |
| ¿Parar en meta?   | **No hace falta.** Puedes seguir; cada línea del JSONL lleva `lap_distance`.  |
| ¿Auto-shift?      | **ON** por defecto (`--auto-shift`).                                          |

Salida por defecto: `data/universal_teacher.jsonl`
Modelo BC (tras entrenar): `PCARS2-AI/models/universal_bc.pt` (ruta relativa al cwd de los `.bat`).

---

## Recuperación off-track y el JSONL

Cuando una rueda sale a césped/gravel (UDP `sTerrain`) o el CTE supera umbral, activa **safety** y
el teacher **recupera** (frena, corrige).

| Efecto                | Dataset `universal_teacher.jsonl`                                 | Log de sesión (`logs/teaching/`)   |
| --------------------- | ----------------------------------------------------------------- | ---------------------------------- |
| Safety activa         | **No se graba** (`quality` 0, &lt; `min_quality` 0,3 al escribir) | Sí (off_track, eventos)            |
| Tramo en pista normal | Sí, con `quality` según CTE                                       | Sí                                 |

**Conclusión:** la recuperación sirve para **completar vueltas** y **evaluar** “vuelta limpia” en el
informe; **no** entrena al BC con frenazos en hierba. Lo que importa para BC es circular **bien** en
asfalto.

---

## Qué aprende el agente (obs universal)

- **General:** CTE, heading, curvatura y lookahead, dinámica (slip, wheelspin), objetivo de

  velocidad, marcha/RPM.

- **Por pista:** la **referencia** (`src/refs/*.json`) aporta geometría local; el modelo **no**

  memoriza GPS ni “curva 7”.

- **Desnivel:** no hay canal explícito de pendiente en `universal_v1`; entra de forma indirecta.

Ver [ENTRENAMIENTO.md](../ENTRENAMIENTO.md) — *Política universal*.

---

## Modelo `.pt` vs archivos de datos

| Archivo                        | Contiene                                                                                        |
| ------------------------------ | ----------------------------------------------------------------------------------------------- |
| `models/universal_bc.pt`       | **Solo pesos** del BC (+ metadatos). Comportamiento “bueno y malo” mezclado según lo entrenado. |
| `data/universal_teacher.jsonl` | Demostraciones del teacher (filtradas al escribir).                                             |
| `data/online_buffer.jsonl`     | Correcciones de **`aprender.bat`** (filtradas por etapa + banda).                               |
| `src/refs/sugo_ai.json`        | Línea de referencia (no está dentro del `.pt`).                                                 |

El fine-tune de aprender **vuelve a cargar todo** el `base-dataset` + buffer en cada ciclo (no
equilibra por pista automáticamente).

---

## Multi-pista — datasets “solo lo bueno” (recomendado)

Teoría operativa (manual hasta tener script de filtro):

1. Por circuito: `record.bat` → filtrar mentalmente o por métricas de sesión →

   `data/sugo_clean.jsonl`, `data/otra_clean.jsonl`, …

2. Criterios típicos: vueltas con informe **limpia**, `quality` ≥ 0,5, poco `safety_reverse` /

   `engage_first` espurio.

3. `entrenar_bc.bat` con **varios** `--dataset` (o `pretrain_universal.py -d … -d …`).
4. **Equilibrar volumen:** si SUGO tiene 90 vueltas y otra pista 5, el BC se **sesga** a SUGO.

   Submuestrear o grabar vueltas parecidas por pista.

5. **Copias de seguridad** del `.pt` antes de muchas vueltas de aprender en un solo circuito.

No se “filtra” comportamiento dentro del `.pt`; se **curan los JSONL** antes de entrenar.

---

## Análisis rápido del JSONL

```bat
```

Muestra % neutro, reasons, tramos problemáticos por `lap_distance`.

---

## Aprender / imitar (BC conduce)

`engage_first` **no** activa `safety_override`. Si solo se sustituyen pedales en safety,
el BC puede mandar gas/freno distintos en **neutro** mientras el log dice `engage_first`
→ N sin engranar (mismo síntoma que en `record` antiguo).

**Corrección:** `choose_bc_drive_pedals()` (usa `needs_gear_engagement`) — pedales del
teacher (`teacher:gear` en consola) + `auto_shift` con `throttle_for_shift` si hiciera falta.

---

## Flujo enlazado

```text
```

---

*Ver también:* [CURRICULO_VELOCIDAD.md](CURRICULO_VELOCIDAD.md),
[ENTRENAMIENTO.md](../ENTRENAMIENTO.md), [VALIDACION_TEACHING_SUGO.md](VALIDACION_TEACHING_SUGO.md)
