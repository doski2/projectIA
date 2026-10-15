# Roadmap — condiciones avanzadas (futuro)

## Estado:** planificado · **No implementar aún

**Prerrequisito:** base sólida en F5 (currículo L1→L7 por banda, Hybrid/Autónomo estables).

Documento de referencia para cuando terminemos línea, ritmo y técnica básica.
Ver currículo actual: [CURRICULO_VELOCIDAD.md](CURRICULO_VELOCIDAD.md).

---

## Principio

La política **universal** actual (`obs_schema: universal_v1`, 17 features) aprende:

- Geometría relativa a la referencia local (CTE, curvatura, lookahead)
- Dinámica del coche (velocidad, slip, aceleraciones, wheelspin…)
- Intención del teacher (`teacher_reason` / `reason_id`)

**Las reglas de conducción son las mismas en cualquier pista**; solo cambia la referencia local
(`src/refs/*.json`).
Eso cubre trazado, acelerar, frenar y girar en todos los circuitos grabados, **si** coche, setup y
condiciones son similares a las del entrenamiento.

---

## Cuándo abrir esta fase

No añadir variables hasta cumplir:

| Criterio            | Señal                                                             |
| ------------------- | ----------------------------------------------------------------- |
| Currículo velocidad | L1→L7 dominado al menos en bandas 20–40 km/h (ideal: hasta 60)    |
| Validación en pista | Hybrid/Autónomo con vueltas limpias y pocos overrides             |
| Multi-pista         | Misma estabilidad en 2–3 circuitos con su referencia              |
| Dataset             | Teacher grabado con **setup y condiciones fijas** y reproducibles |

Meter muchas variables antes de dominar lo básico multiplica la combinatoria de datos y empeora el
aprendizaje.

---

## Orden de capas (no todo a la vez)

### Capa 1 — Actual (F5)

Geometría + dinámica básica + intención. Multi-pista con referencia local.

### Capa 2 — Condiciones que cambian en carrera (prioridad futura)

Disponibles en telemetría UDP (`pcars2_udp_data_reference.md`; enums en `src/pcars2_surface.py`):

**Ya en seguridad (F5):** `sTerrain[4]` → `off_surface` en `SafetyMonitor` (complementa CTE).

| Variable                                 | Campos UDP (ej.)                                             | Efecto en conducción           |
| ---------------------------------------- | ------------------------------------------------------------ | ------------------------------ |
| Temperatura neumático / pista / ambiente | `sTyreTreadTemp`, `sTrackTemperature`, `sAmbientTemperature` | Agarre, ventana de frenada     |
| Desgaste neumático                       | `sTyreWear`                                                  | Menos agarre al final de stint |
| Combustible                              | `sFuelLevel`, `sFuelCapacity`                                | Peso, balance                  |
| Daño / suspensión                        | `sSuspensionDamage`, etc.                                    | Comportamiento degradado       |

**Enfoque:** currículo por condiciones (como las bandas de velocidad): primero seco/setup base →
stint con desgaste → lluvia/frío, etc.
Grabar teacher y buffer etiquetados por condición; fine-tune filtrado igual que `learn_stage` +
`speed_band_kmh`.

### Capa 3 — Setup, diferenciales, potencia, par…

El menú de setup del juego **no** llega como valores directos en UDP (p. ej. “diferencial 60/40”).
Solo se observan **efectos** en telemetría y comportamiento.

Opciones documentadas para más adelante:

1. **Metadata de sesión** en JSONL (`car`, `setup_id`, `compound`, `track`) — contexto fijo por

   grabación

2. **Condiciones fijas** al inicio: un setup, un compuesto, sesiones cortas
3. **Currículo de condiciones** explícito antes de mezclar setups

### Capa 4 — RL (PPO)

Optimización de tiempo, gestión de stint, adaptación fina. Solo cuando BC sea estable en las capas
anteriores.

---

## Multi-pista: qué sí y qué no transfiere

| Aspecto                            | ¿Transfiere con `universal_v1`?                             |
| ---------------------------------- | ----------------------------------------------------------- |
| Trazado / geometría                | Sí, con referencia local por pista                          |
| Lógica acelerar / frenar / girar   | Sí, vía teacher + `teacher_reason`                          |
| Mismo coche y setup similar        | Mejor generalización                                        |
| Lluvia, frío, desgaste, otro setup | No hasta grabar/aprender en esas condiciones                |
| Ampliar observación                | Requiere nuevo schema (p. ej. `universal_v2`) y re-entrenar |

Recomendación: grabar teacher en **2–3 pistas** con el **mismo protocolo** (setup fijo, banda baja,
vueltas limpias) antes de abrir condiciones.

---

## Impacto técnico (cuando se implemente)

- Nuevo `obs_schema` (p. ej. `universal_v2`) — no mezclar con `universal_v1` en el mismo `.pt` sin

  migración

- Campos extra en JSONL del buffer (`session_context`, condiciones…)
- Extensión del teacher si hace falta lógica explícita (p. ej. neumático frío)
- Currículo F6 análogo a bandas de velocidad — ver

  [VALIDACION_TEACHING_SUGO.md](VALIDACION_TEACHING_SUGO.md)

---

## Resumen en una línea

**Ahora:** dominar L1→L7 y multi-pista con lo universal.
**Después:** temperatura, combustible, desgaste (UDP en vivo).
**Más tarde:** setup/diferenciales como contexto de sesión.
**Al final:** RL para rendimiento.

---

*Ver también:* [CURRICULO_VELOCIDAD.md](CURRICULO_VELOCIDAD.md),
[VALIDACION_TEACHING_SUGO.md](VALIDACION_TEACHING_SUGO.md), [ENTRENAMIENTO.md](../ENTRENAMIENTO.md),
[pcars2_udp_data_reference.md](../../pcars2_udp_data_reference.md)
