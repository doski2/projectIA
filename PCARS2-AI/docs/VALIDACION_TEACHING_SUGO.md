# Validación Teaching — Sugo (pasos firmes)

**Estado:** activo · **Estilo replay:** [TSW6 session_report](https://github.com/doski2/TSW6)  
**Principio:** si aprende a girar, acelerar y frenar en línea en Sugo, las **reglas** son las mismas en cualquier pista; solo cambia la referencia local (geometría).

---

## Antes de empezar (F0 — prerrequisitos)

- [ ] PCARS2 en pista, UDP activo (puerto 5606)
- [ ] ViGEmBus + vgamepad funcionando
- [ ] Referencia Sugo grabada: `src/refs/sugo_ai.json`
- [ ] `teach.bat` o GUI Teaching Driver arranca sin error

```bat
cd PCARS2-AI
tests.bat
teach.bat --phase f1_linea
```

---

## Fases (orden fijo)

| Fase | Objetivo | Velocidad | Comando |
|------|----------|-----------|---------|
| **F1** `f1_linea` | Girar en la línea correcta | 15 km/h | `validar_f1.bat` |
| **F2** `f2_acelerar` | Acelerar de forma progresiva | 20 km/h | `validar_f2.bat` |
| **F3** `f3_frenar` | Frenar antes de curvas / overspeed | 20 km/h | `validar_f3.bat` |
| **F4** `f4_combinado` | Vuelta limpia combinando todo | 20 km/h | `validar_f4.bat` |
| **F5** (después) | Grabar dataset universal | 20 km/h | `record.bat` |

**No pasar a la siguiente fase hasta APTO en HTML.**

---

## F1 — Girar en línea

**Qué valida:** CTE, heading, steering del teacher; vuelta completa sin salirse.

**Ejecutar (≥ 1 vuelta, ~1–2 min):**

```bat
validar_f1.bat
```

Al cerrar (Ctrl+C) se genera:

- `logs/teaching/YYYYMMDDTHHMMSS_sugo_f1_linea.jsonl`
- `logs/teaching/YYYYMMDDTHHMMSS_sugo_f1_linea.html` ← **abrir este**

**Criterios APTO:**

| Check | Umbral |
|-------|--------|
| Vueltas | ≥ 1 |
| CTE medio | ≤ 6 m |
| CTE p95 | ≤ 10 m |
| % off-track | ≤ 8% |
| % stuck | ≤ 25% |

---

## F2 — Acelerar

**Qué valida:** velocidad media cerca del objetivo; intents `accel_straight` / `accel_curve_limited`.

```bat
validar_f2.bat
```

| Check | Umbral |
|-------|--------|
| Vel. media | 14–26 km/h |
| % intents aceleración | ≥ 8% |
| CTE medio | ≤ 6 m |

---

## F3 — Frenar

**Qué valida:** intents `brake_overspeed` / `recover_line`; sin atascos.

```bat
validar_f3.bat
```

| Check | Umbral |
|-------|--------|
| % intents freno | ≥ 5% |
| % stuck | ≤ 15% |
| CTE medio | ≤ 6.5 m |

---

## F4 — Combinado (vuelta limpia)

**Qué valida:** girar + acelerar + frenar en la misma sesión.

```bat
validar_f4.bat
```

| Check | Umbral |
|-------|--------|
| CTE medio | ≤ 5 m |
| % off-track | ≤ 5% |
| % stuck | ≤ 10% |
| Acel + freno | presentes en el log |

**Si APTO → listo para `record.bat` (dataset universal).**

---

## Leer el informe HTML

Inspirado en TSW6 (`V2/tsw6v2/session_report.py`):

1. **Banner verde/ámbar** — APTO / REVISAR
2. **Stat cards** — CTE, velocidad, off-track, stuck, intents
3. **Gráfico SVG** — velocidad, CTE, throttle, brake, steering vs tiempo
4. **Tabla criterios** — cada check con OK/FAIL
5. **Tabla intents** — distribución `teacher_reason` (cuándo/por qué actúa)

Regenerar HTML sin volver a conducir:

```bat
report_sesion.bat logs\teaching\tu_sesion.jsonl
```

---

## Multi-pista (después de F4 en Sugo)

El concepto **girar / acelerar / frenar** es universal. En otra pista:

1. Grabar referencia local (`reference_recorder.py`)
2. Repetir F1→F4 con esa referencia (mismas reglas)
3. Combinar datasets → `pretrain_universal.py`

---

## Qué pasar para revisión (IA / análisis)

```
@PCARS2-AI/logs/teaching/ULTIMA_SESION.html
@PCARS2-AI/logs/teaching/ULTIMA_SESION.jsonl
```

Indica la fase (`f1_linea`, etc.) y si el banner dice APTO o REVISAR.

---

## Actualización del plan

| Fecha | Cambio |
|-------|--------|
| 2026-09-18 | F1–F4 definidas; JSONL + HTML teaching; inicio Sugo |

*Actualizar esta tabla al cerrar cada fase en pista.*
