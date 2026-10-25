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
| Temperatura y daño de frenos             | `sBrakeTempCelsius[4]`, `sBrakeDamage[4]` (hoy no se leen en `TelemetryFrame`) | Fade, avería, distancia de frenada |

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
anteriores. **Sí se va a usar**: el BC no puede aprender a ir más rápido que su teacher; PPO es lo
que lo permite. Ver «Secuencia hacia la carrera» abajo.

**Por qué después del BC y no antes:** PPO desde cero necesita millones de pasos y el juego no se
acelera (una vuelta son ~3,5 min reales). Partiendo de un BC que ya conduce limpio, esas muestras
se emplean en ganar ritmo y no en aprender a no salirse; sin esa base, además, se sale
constantemente y, con daños activos, acaba en averías.

**Prerrequisitos (ninguno hecho todavía):**

1. BC estable: Hybrid y Autónomo con vueltas limpias en la banda más alta del currículo.
2. Base de datos compactada y reetiquetada sin solape de gas y freno (ver
   «Deuda de conducción» más abajo).
3. Un solo eje de pedal en la acción (negativo = freno), con penalización de temperatura de frenos.
4. Observación ampliada con la física del coche (`universal_v2`, reentrenar el BC).
5. Compensación de la curva del volante activa también en el entorno de PPO
   (`DS4Controller(steer_comp=True)`; hoy `environment.py` no la aplica).
6. Anclar la política al BC (penalización KL o tasa de aprendizaje muy baja al principio) para no
   perder lo aprendido.

**Primera prueba de PPO (2026-10-25, a petición, saltando Hybrid 60 y las bandas 70/80):** es una
prueba de humo para ver si el PPO arranca y mantiene la conducción, **no** el PPO final: los
prerrequisitos 2, 3 y 4 siguen sin hacerse. Lo que se cerró para poder probarla:

- Entorno con la observación `universal_v1` (CTE con signo), `--steer-comp` y velocidad objetivo.
- `ppo_bootstrap.py` destila el BC a un modelo PPO (`models/ppo_universal_base.zip`): error medio
  0,018 frente al BC y 0,071 frente al profesor (el BC: 0,068). Se entrena con la base más el buffer
  curado, que incluye la banda 60.
- Ancla al BC: desviación inicial 0,1 y actor congelado 8192 pasos mientras el crítico aprende.
- Frenado durante la actualización de la red: el juego no se pausa, y sin esto el coche seguía varios
  segundos con el último mando y el episodio continuaba con datos corruptos.
- GUI: pestaña *RL (PPO)* -> modo **Anclado al BC (universal)** (mismos flags que el `.bat`; los demás modos usan la observación antigua, `frame_skip` 4 y, según los ajustes guardados, `--fresh`).
- Logs en `logs/formula_rookie__sugo/`: `metricas.csv` (medias por rollout; botón *Monitor*) y `episodios.csv`, una fila por episodio con el motivo de fin, los metros recorridos al terminar, el CTE, la velocidad, el tiempo de vuelta (solo si acaba en `lap_done`) y la recompensa. Esa es la tabla para comparar con el BC y con la referencia de 213,9 s. TensorBoard con su botón y checkpoints en `models/formula_rookie__sugo/`. No hay informe HTML por vuelta.
- Actualizaciones suaves al partir del BC (`--anchor-lr` 3e-5, `--anchor-epochs` 4, `--anchor-target-kl` 0,02): en la primera prueba (50 000 pasos) `clip_fraction` rondaba 0,3 y `approx_kl` 0,03-0,05 con desviación 0,1, y el CTE medio subió de ~0,85 a ~1,05 m. Esa prueba también mostró 2 de ~5 episodios en `stuck` con CTE ~5 m: es la línea base del modelo destilado sin profesor ni amortiguación de volante.
- Lanzador: `ppo_probar.bat` (50 000 pasos, objetivo 60 km/h; el entorno sube la velocidad objetivo
  +5 km/h cada 10 000 pasos si la media está en banda).

Qué mirar: `pct_lap_done` y `avg_cte` en `metricas.csv` (no deben empeorar respecto al BC),
`pct_stuck` / `pct_wrong_way`, y la `std` de la política, que debe subir despacio. Una vuelta son
~12 600 pasos a 60 Hz, así que 50 000 pasos son unas 4 vueltas de experiencia (~15 min de juego,
más las pausas de actualización): sirve para detectar problemas, no para batir al reloj.

**Estado del código:** existe `main.train` + `environment.py` (observación `obs_builder` y pedales
independientes, **no** la observación universal). **Nunca se ha probado con el modelo actual**
(confirmado 2026-10-25): el primer paso de la fase PPO es comprobar que arranca, qué observación
usa y si coincide con la del BC, antes de planificar nada sobre él.
La revisión de código del 2026-10-25 encontró fallos que hay que resolver antes (el entorno no
detecta un coche parado, los tiempos están calculados a 25 Hz cuando el juego va a 60, el CTE de
la observación no tiene signo y no hay ancla al BC): ver
[AUDITORIA_CODIGO.md](AUDITORIA_CODIGO.md), sección 7.

## Secuencia hacia la carrera

Meta final: correr contra otros coches (adelantar y defender), con box, estrategia y reglaje
para optimizar el tiempo.

| Paso | Qué                                                              | Estado |
| ---- | ---------------------------------------------------------------- | ------ |
| 1    | Currículo L1→L7 por banda (20 → 80 km/h) con compensación del volante | En curso (55 km/h) |
| 2    | Hybrid y Autónomo estables en Sugo en la banda máxima            | Pendiente |
| 3    | Compactar y reetiquetar la base; pedal único; `universal_v2`     | Pendiente |
| 4    | Segunda pista con el mismo coche ([PLAN_NUEVAS_PISTAS_Y_COCHES.md](PLAN_NUEVAS_PISTAS_Y_COCHES.md)) | Pendiente |
| 5    | PPO en solitario hasta ser competitivo contra el reloj (referencia IA: 213,9 s en Sugo) | Pendiente |
| 6    | Reglaje por bucle externo (el setup no llega por UDP)            | Pendiente |
| 7    | Condiciones: temperatura, desgaste, combustible, daños (capa 2)  | Pendiente |
| 8    | Rivales: seguir sin chocar → adelantar y defender                | Pendiente |
| 9    | Box y estrategia                                                 | Pendiente |

Los pasos 3 y 4 pueden invertirse si la segunda pista se quiere antes: en ese caso la compactación
se hace antes de mezclar datos de dos pistas.

---

## Deuda de conducción: solape de gas y freno (resolver antes de activar daños)

**Estado:** documentado 2026-10-25, **sin implementar**. Decisión: por ahora solo se documenta.

**Qué pasa.** El coche acelera y frena a la vez durante transiciones y en parte de la conducción de
crucero. No es trail-braking intencionado.

- **Origen en el teacher.** `TeachingController` suaviza gas y freno por separado con límites de
  tasa (`_smooth`, `throttle_rate` / `brake_rate`). Al pasar de acelerar a frenar, un pedal baja
  mientras el otro sube y durante la transición hay los dos pulsados.
- **Medido en las etiquetas del teacher** (acción decodificada, gas y freno > 0,05 a la vez):

  | Dataset                                      | Solape | Por situación |
  | -------------------------------------------- | -----: | ------------- |
  | `data/universal_teacher.jsonl` (base)        |   64 % | `brake_overspeed` 94 %, `maintain_speed` 54 %, `accel_straight` 8 % |
  | `data/online_buffer.jsonl` (400 000 primeras) |  3,8 % | `brake_overspeed` 32 %, `maintain_speed` 2 % |

  Nunca con ambos pedales por encima de 0,2: son solapes pequeños pero constantes.
- **El BC lo hereda y lo amplifica.** Al ser una regresión sobre intenciones distintas, promedia y
  a menudo devuelve gas y freno bajos a la vez: 14-52 % de los ticks del BC a más de 40 km/h en las
  sesiones de aprendizaje del 2026-10-24 y 25.
- **El pedal se aplica fielmente.** `vehicle.game_throttle` y `game_brake` coinciden con lo
  enviado, así que el coche recibe ese solape tal cual.
- **No es (con estos datos) la causa del zigzag del volante.** El solape no sube de forma
  consistente justo antes de las salidas de línea, y en el trompo de 60 km/h el freno estaba a 0.

**Por qué hay que corregirlo.** Hoy se ejecuta con daños, desgaste y averías desactivados (ver
[CONFIGURACION_JUEGO.md](CONFIGURACION_JUEGO.md): *Tipo de daño*, *Fallos mecánicos*, *Desgaste de
los neumáticos* y *Uso de combustible* en «Desact.»). Con esas opciones activas, frenar con gas
pisado:

- calienta los frenos (`sBrakeTempCelsius`) y provoca **fade**: peor distancia de frenada
  (`sBrakeDamage` también),
- desgasta antes frenos y neumáticos y aumenta el riesgo de averías mecánicas,
- gasta combustible y energía sin avanzar, y empeora el rendimiento de frenada que optimizaría
  un PPO.

El agente se ha entrenado hasta aquí sin esos costes, así que no tiene ninguna presión para
evitar el hábito.

**Plan (en este orden, nada hecho):**

1. **Exclusión de pedales al actuar** (interruptor tipo `--pedal-exclusive`): si un pedal pasa de
   ~0,05, el otro va a 0, con un margen para no vibrar entre ambos. Se puede probar sin reentrenar.
2. **Corregir el teacher:** suavizar un único eje de pedal (gas − freno) para que la transición
   pase por cero. Las etiquetas nuevas saldrán sin solape.
3. **Reetiquetar el dataset existente** al reentrenar o compactar la base: en cada fila, poner a 0
   el pedal menor. Evita que el BC siga aprendiendo el hábito de los datos antiguos. (La compactación
   de `online_buffer.jsonl`, 1,45 GB y 49 % de filas casi idénticas a la anterior, está pendiente
   por separado.)
4. **PPO:** espacio de acción con **un solo eje de pedal** en [-1, 1] (negativo = freno), de modo
   que el solape sea imposible por construcción, y penalización explícita por temperatura de
   frenos.
5. **Leer la telemetría de frenos:** añadir `sBrakeTempCelsius[4]` y `sBrakeDamage[4]` a
   `TelemetryFrame` (están en [pcars2_udp_data_reference.md](../../pcars2_udp_data_reference.md))
   y registrarlos en el log de ticks, para medir el efecto antes y después de los cambios.

**Criterio de «hecho»:** solape inferior al 2 % de los ticks del BC a más de 40 km/h con
`--pedal-exclusive` activo o con el teacher corregido, sin empeorar CTE ni tiempo de vuelta, y
temperatura de frenos legible en el log.

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

**Ahora:** dominar L1→L7 por banda (en 55 km/h) con la compensación del volante activa.
**Después:** Hybrid/Autónomo estables, base compactada sin solape de pedales y segunda pista.
**Luego:** PPO anclado al BC para ser competitivo contra el reloj.
**Más tarde:** reglaje, condiciones (temperatura, combustible, desgaste, daños) y rivales.
**Al final:** adelantar y defender posición, box y estrategia.

---

*Ver también:* [CURRICULO_VELOCIDAD.md](CURRICULO_VELOCIDAD.md),
[VALIDACION_TEACHING_SUGO.md](VALIDACION_TEACHING_SUGO.md), [ENTRENAMIENTO.md](../ENTRENAMIENTO.md),
[pcars2_udp_data_reference.md](../../pcars2_udp_data_reference.md)
