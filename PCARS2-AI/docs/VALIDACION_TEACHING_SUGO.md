# Validación Teaching — Sugo (pasos firmes)

**Estado:** F1–F4 APTO · **Siguiente:** F5 `record.bat` (dataset + BC)  
**Estilo replay:** [TSW6 session_report](https://github.com/doski2/TSW6)  
**Principio:** si gira, acelera y frena en línea en Sugo, las **reglas** son las mismas en cualquier pista; solo cambia la referencia local (geometría).

> **Importante:** `validar_f*.bat` = **reglas** (teacher), no entrenamiento de red.  
> El aprendizaje (BC) empieza en **F5** con `record.bat` → `pretrain_universal.py`.

---

## Progreso en pista

| Fase | Estado | Sesión | Métricas clave |
|------|--------|--------|----------------|
| **F0** Prerrequisitos | OK | — | UDP, vgamepad, `sugo_ai.json` |
| **F1** `f1_linea` | **APTO** | `20260918T174337Z_sugo_gp_f1_linea` | 3 vueltas · CTE 2.36 m · stuck 0% |
| **F2** `f2_acelerar` | **APTO** | `20260918T182344Z_sugo_gp_f2_acelerar` | 4 vueltas · vel 23.7 km/h · CTE 2.41 m |
| **F3** `f3_frenar` | **APTO** | `20260918T190548Z_sugo_gp_f3_frenar` | 10 vueltas · freno 35.8% · CTE 2.44 m |
| **F4** `f4_combinado` | **APTO** | `20260918T210105Z_sugo_gp_f4_combinado` | 1 vuelta · CTE 2.33 m · acel 62.8% · freno 37.2% |
| **F5** `record.bat` | **siguiente** | — | grabar dataset → `pretrain_universal.py` |

*Actualizar esta tabla al cerrar cada fase (banner verde en HTML).*

**Resumen acumulado (F1–F4):** CTE medio estable ~2.3–2.4 m · 0% stuck · 0% off-track · acel ~63% / freno ~37% en F4.

---

## Antes de empezar (F0 — prerrequisitos)

- [x] PCARS2 en pista, UDP activo (puerto 5606)
- [x] ViGEmBus + vgamepad funcionando
- [x] Referencia Sugo grabada: `src/refs/sugo_ai.json`
- [x] `validar_f1.bat` → APTO
- [x] `validar_f2.bat` → APTO
- [x] `validar_f3.bat` → APTO
- [x] `validar_f4.bat` → APTO
- [x] Cambios **manuales** activados (auto-shift RB/LB)

```bat
cd PCARS2-AI
tests.bat
```

---

## Fases (orden fijo)

| Fase | Objetivo | Velocidad | Comando |
|------|----------|-----------|---------|
| **F1** `f1_linea` | Girar en la línea correcta | 15 km/h | `validar_f1.bat` |
| **F2** `f2_acelerar` | Acelerar y mantener objetivo | 20 km/h | `validar_f2.bat` |
| **F3** `f3_frenar` | Frenar antes de curvas / overspeed | 20 km/h | `validar_f3.bat` |
| **F4** `f4_combinado` | Vuelta limpia combinando todo | 20 km/h | `validar_f4.bat` |
| **F5** (después) | Grabar dataset universal | 20 km/h | `record.bat` |

**No pasar a la siguiente fase hasta APTO en HTML.**

---

## F1 — Girar en línea ✅ APTO

**Qué valida:** CTE, heading, steering del teacher; vuelta completa sin salirse.

**Sesión de referencia (2026-09-18):**

- Log: `logs/teaching/20260918T174337Z_sugo_gp_f1_linea.jsonl`
- HTML: `logs/teaching/20260918T174337Z_sugo_gp_f1_linea.html`
- Duración: ~34 min · **3 vueltas** · gear 1 estable

| Check | Resultado | Umbral |
|-------|-----------|--------|
| Vueltas | 3 | ≥ 1 |
| CTE medio | 2.36 m | ≤ 6 m |
| CTE p95 | 3.68 m | ≤ 10 m |
| % off-track | 0% | ≤ 8% |
| % stuck | 0% | ≤ 25% |
| % safety override | 0% | ≤ 30% |

**Nota:** velocidad media 19.2 km/h (por encima del objetivo 15 de F1). No invalida F1.

---

## F2 — Acelerar ✅ APTO

**Qué valida:** velocidad media cerca de **20 km/h**; intents de aceleración; CTE controlado.

**Sesión de referencia (2026-09-18):**

- Log: `logs/teaching/20260918T182344Z_sugo_gp_f2_acelerar.jsonl`
- HTML: `logs/teaching/20260918T182344Z_sugo_gp_f2_acelerar.html`
- Duración: ~38 min · **4 vueltas**

| Check | Resultado | Umbral |
|-------|-----------|--------|
| Vueltas | 4 | ≥ 1 |
| Vel. media | 23.7 km/h | 14–26 km/h |
| % intents aceleración | 63.2% | ≥ 8% |
| CTE medio | 2.41 m | ≤ 6 m |
| % stuck | 0% | ≤ 20% |

---

## F3 — Frenar ✅ APTO

**Qué valida:** intents `brake_overspeed` / `recover_line`; sin atascos; CTE controlado.

**Sesión de referencia (2026-09-18):**

- Log: `logs/teaching/20260918T190548Z_sugo_gp_f3_frenar.jsonl`
- HTML: `logs/teaching/20260918T190548Z_sugo_gp_f3_frenar.html`
- Duración: ~99 min · **10 vueltas**

| Check | Resultado | Umbral |
|-------|-----------|--------|
| Vueltas | 10 | ≥ 1 |
| % intents freno | 35.8% | ≥ 5% |
| CTE medio | 2.44 m | ≤ 6.5 m |
| % stuck | 0% | ≤ 15% |
| % safety override | 0% | ≤ 25% |
| Vel. media | 23.7 km/h | — |

**Intents dominantes:** `maintain_speed`, `brake_overspeed` — acelerar y frenar presentes en la misma sesión.

**Confirmación (misma fase, 2026-09-18 tarde):**

- Log: `logs/teaching/20260918T205006Z_sugo_gp_f3_frenar.jsonl`
- HTML: `logs/teaching/20260918T205006Z_sugo_gp_f3_frenar.html`
- Duración: ~9 min · **1 vuelta** · APTO (todos los checks OK)

| Check | Resultado | Umbral |
|-------|-----------|--------|
| Vueltas | 1 | ≥ 1 |
| % intents freno | 37.1% | ≥ 5% |
| CTE medio | 2.36 m | ≤ 6.5 m |
| % stuck | 0% | ≤ 15% |
| Vel. media | 23.8 km/h | — |

Métricas alineadas con la sesión larga (`190548Z`); basta **1 vuelta** para APTO en F3.

---

## F4 — Combinado (vuelta limpia) ✅ APTO

**Qué valida:** girar + acelerar + frenar juntos en vuelta limpia (criterios más estrictos que F1–F3).

**Sesión de referencia (2026-09-18):**

- Log: `logs/teaching/20260918T210105Z_sugo_gp_f4_combinado.jsonl`
- HTML: `logs/teaching/20260918T210105Z_sugo_gp_f4_combinado.html`
- Duración: ~9 min · **1 vuelta**

| Check | Resultado | Umbral |
|-------|-----------|--------|
| Vueltas | 1 | ≥ 1 |
| CTE medio | 2.33 m | ≤ 5 m |
| CTE p95 | 3.71 m | ≤ 8 m |
| % off-track | 0% | ≤ 5% |
| % stuck | 0% | ≤ 10% |
| Vel. media | 23.8 km/h | 15–25 km/h |
| % aceleración | 62.8% | ≥ 5% |
| % freno | 37.2% | ≥ 3% |
| % safety override | 0% | ≤ 15% |

**Intents dominantes:** `maintain_speed`, `brake_overspeed` — misma mezcla acel/freno que F2–F3, con CTE ligeramente mejor que F1–F3.

---

## F5 — Aprendizaje ← **AHORA**

| Paso | `.bat` | Salida |
|------|--------|--------|
| 1. Grabar teacher | `record.bat` | `data/universal_teacher.jsonl` |
| 2. Entrenar BC (offline) | `entrenar_bc.bat` | `models/universal_bc.pt` |
| 3. Evaluar offline | `eval_bc.bat` | MAE en consola |
| 4. Probar red (sin aprender) | `imitar_bc.bat` | HTML en `logs/imitation/` |
| 5. **Aprender en pista** | `aprender.bat` | fine-tune cada vuelta + HTML en `logs/learning/` |
| 6. Hybrid / autonomía | `imitar_hybrid.bat` → `imitar_autonomo.bat` | cuando L5 o vueltas limpias |

F1–F4 = **reglas**. F5 = la red aprende del teacher.

### Currículo online (`aprender.bat`)

| Etapa | Objetivo | Velocidad | Graduar |
|-------|----------|-----------|---------|
| **L1** línea | Trazado, lógica básica | 15 km/h | 2 vueltas limpias |
| **L2** velocidad | Mantener ritmo | 20 km/h | 2 vueltas limpias |
| **L3** frenar | Física de frenada | 20 km/h | 2 vueltas limpias |
| **L4** combinado | Todo junto | 25 km/h | 2 vueltas limpias |
| **L5** rápido | Sin límites artificiales | 35 km/h | 3 vueltas → **autonomía** |

Cada vuelta: BC conduce, teacher corrige → buffer → **fine-tune** del modelo.  
Autonomía total solo cuando domine varias condiciones (`imitar_autonomo.bat`).

El **HTML** (`logs/learning/`) muestra:
- **Objetivos** de la etapa (CTE, freno, vueltas limpias…)
- **Tiempos por vuelta** (seguimiento; la red no optimiza tiempo aún)
- Referencia teacher vs tu mejor vuelta

### Ejecutar (primera vez)

```bat
record.bat          rem ≥3 vueltas, Ctrl+C
entrenar_bc.bat
eval_bc.bat
aprender.bat        rem aprende vuelta a vuelta, abre HTML al salir
```

---

## Glosario rápido

| Término | Significado |
|---------|-------------|
| **CTE / cte_avg** | Distancia media (m) a la línea de referencia. Menor = mejor trazado. |
| **CTE p95** | 95% del tiempo por debajo de este CTE (picos malos). |
| **teacher_reason** | Por qué actuó el teacher (`accel_straight`, `brake_overspeed`, etc.). |
| **APTO / REVISAR** | Pass/fail de la fase según umbrales en `validation_phases.py`. |

---

## Leer el informe HTML

1. **Banner verde/ámbar** — APTO / REVISAR
2. **Stat cards** — CTE, velocidad, off-track, stuck, intents
3. **Gráfico SVG** — velocidad, CTE, throttle, brake, steering vs tiempo
4. **Tabla criterios** — cada check con OK/FAIL
5. **Tabla intents** — distribución `teacher_reason`

Regenerar HTML sin volver a conducir:

```bat
report_sesion.bat logs\teaching\tu_sesion.jsonl
```

---

## Multi-pista (después de F4 en Sugo)

1. Grabar referencia local (`reference_recorder.py`)
2. Repetir F1→F4 con esa referencia (mismas reglas)
3. Combinar datasets → `pretrain_universal.py`

---

## Qué pasar para revisión (IA / análisis)

```
@PCARS2-AI/logs/teaching/ULTIMA_SESION.html
@PCARS2-AI/logs/teaching/ULTIMA_SESION.jsonl
```

Indica la fase y si el banner dice APTO o REVISAR.

---

## Historial de cambios

| Fecha | Cambio |
|-------|--------|
| 2026-09-18 | F1–F4 definidas; JSONL + HTML teaching; inicio Sugo |
| 2026-09-18 | F1 APTO (`174337Z`): 3 vueltas, CTE 2.36 m, fixes steering + auto-shift |
| 2026-09-18 | F2 APTO (`182344Z`): 4 vueltas, vel 23.7 km/h, CTE 2.41 m |
| 2026-09-18 | F3 APTO (`190548Z`): 10 vueltas, freno 35.8%, CTE 2.44 m |
| 2026-09-18 | F3 confirmación (`205006Z`): 1 vuelta, freno 37.1%, CTE 2.36 m |
| 2026-09-18 | Documentado F4 como siguiente; glosario CTE; F0 checklist completo |
| 2026-09-18 | F4 APTO (`210105Z`): 1 vuelta, CTE 2.33 m, acel 62.8%, freno 37.2% |
