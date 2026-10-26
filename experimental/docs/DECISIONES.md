# Decisiones

> Estado al 2026-10-26. Se lee de arriba abajo: primero la línea de trabajo (qué toca y en qué orden), luego lo
> decidido, los cambios en código existente, lo descubierto, lo que falta decidir y la discusión de realismo.
> Los identificadores (D, X, H, P, R) no cambian de sitio aunque el documento se reordene.

## 1. Línea de trabajo (orden y estado)

| # | Paso | Estado | Depende de |
| --- | --- | --- | --- |
| 1 | Andamiaje de `experimental/`, pestaña en la GUI y reglas (D1-D5, X2, X3) | Hecho | — |
| 2 | Log ampliado y cabecera (D4, X1) e informe de C0 (D8-D10) | Hecho | 1 |
| 3 | Primera ejecución de C0 (40 km/h, 2 vueltas) y hallazgos (sección 4) | Hecho (2026-10-26) | 2 |
| 4 | **X4a (hecho):** registrar `sector`, `current_sector_time` y `current_time` por tick, marcar en el informe las pausas del juego (H5) y añadir el análisis por sectores (H9). **Repetir C0 con ello** | Siguiente: lanzar C0 | 3 |
| 5 | Decidir lo que bloquea C1 y R1: P8, P10, P11, P13 (sección 5) | Pendiente | 3 |
| 6 | C1: rampa 60 → 80 km/h con puerta, en el perfil R0 (`PLAN_C_RAMPA_BC.md`) | Pendiente | 4, 5 |
| 7 | Activar R1 (desgaste y combustible) y registrar el perfil de condiciones (X5, sección 6) | Pendiente | 5, 6 |
| 8 | A1: sesiones de identificación en R1 (`PLAN_A_LIMITES_COCHE.md`); rehacer el rango lateral con `v · yaw_rate` (H1) | Pendiente | 7 |
| 9 | A2-A4, y B0-B2 solo si A2 sale bien (`PLAN_B_SIMULADOR.md`) | Pendiente | 8 |

C0 vuelve a ejecutarse antes de C1 porque es barato (unos 10 minutos) y deja fuera dudas sobre el reloj y los sectores.

## 2. Decisiones tomadas

| # | Tema | Decisión | Motivo |
| --- | --- | --- | --- |
| D1 | Estructura | La carpeta `experimental/` está en la raíz del repositorio (`projectIA/`), al lado de `PCARS2-AI/` | Es transversal: no pertenece a la GUI ni a `src` |
| D2 | Estructura | `experimental/` puede importar de `PCARS2-AI/src`; al revés, nunca | Borrar la carpeta no rompe nada |
| D5 | Estructura | Tests de esta carpeta en `experimental/tests/`, fuera de la suite principal | La suite principal no se ensucia ni se ralentiza |
| D3 | Logs | Los logs de sesión **no se separan por carpeta**: todos van a `PCARS2-AI/logs/` como hasta ahora. Se distinguen por la cabecera (D4) | Un solo sitio y un solo formato; la separación es de logística, no de ubicación |
| D4 | Logs | El log es **siempre completo**: los campos nuevos se añaden al final del bloque `vehicle` en todas las sesiones. La **cabecera** de la sesión (primera línea del JSONL) lleva `log_schema` (versión del esquema), `origin` (`main` o `experimental`) y `experiment` (p. ej. `rampa_bc`) | Saber qué sesiones tienen datos completos y de dónde vienen sin abrir los ticks; los lectores actuales no se rompen al añadir claves al final |
| D6 | Logs | Formato de grabación: **JSONL** (sin cambios). Para analizar y archivar, un paso aparte convierte a **Parquet** (en `experimental/common/`), con la cabecera como metadatos | JSONL aguanta cortes a mitad de sesión; Parquet es mucho más pequeño y rápido de leer |
| D7 | Lanzamiento | Las pruebas se lanzan **aisladas** desde la pestaña Experimental (`experimental/common/aislado.py`): copia del modelo y buffer propio en `experimental/data/`, `--learn-every 99` (sin fine-tune) y restauración del progreso de aprendizaje (`user_learn_settings.json`) al terminar, incluso si falla. No se lanzan a la vez que una sesión normal de aprendizaje | `learn_driver` modifica por defecto modelo, buffer y progreso de producción |
| D8 | Informe | Cada prueba C0 genera un **informe** (`experimental/common/informe_c0.py`) en `experimental/logs/informe_<log>.html` y `.json`, y se abre solo al terminar. Contiene comprobaciones automáticas (cabecera, presencia y variación de cada campo nuevo, coherencia de ejes y unidades, reloj, tamaño por tick frente a un log antiguo), gráficas por vuelta y línea de tiempo de incidencias | Revisar a ojo lo que ningún test detecta y localizar en qué punto de la pista pasó algo. El JSON permite comparar pruebas entre sí y reutilizar el informe en C1 |
| D9 | Informe | Los umbrales del informe son márgenes razonables, no igualdades: un aviso no siempre es un fallo del log. Las gráficas son la comprobación final | La IA no sigue la línea exacta y las correlaciones nunca son perfectas |
| D10 | Informe | El informe detecta solo el eje lateral y longitudinal de `local_accel`, lista dónde hay saltos de reloj y dibuja a 170 dpi | Primera ejecución real de C0 (ver sección 4) |

## 3. Cambios mínimos en código existente (excepciones a la regla D2)

Cada uno se hace con la menor huella posible y se apunta aquí.

| # | Archivo | Cambio | Estado |
| --- | --- | --- | --- |
| X1 | `PCARS2-AI/src/session_log.py` y `learn_driver.py` | `vehicle_diag` escribe siempre, al final del bloque `vehicle`, los campos de la tanda 1 (`vehicle_extra`): `local_velocity`, `local_accel`, `ang_vel`, `position`, `orientation`, `ride_height`, `susp_travel`, `tyre_temp`, `tyre_tread_temp`, `tyre_wear`, `fuel_level`, `brake_bias`, `aero_damage`, `engine_damage`, `raw_throttle`, `raw_brake`, `clutch`. La cabecera lleva `log_schema` (2), `origin` y `experiment`. `learn_driver --experiment <nombre>` marca `origin=experimental`; sin él, `origin=main`. Tests en `tests/test_session_log_schema.py` | Hecho (2026-10-26). La pestaña lo pasa a través de `aislado.py`. Solo toca `learn_driver`; `imitation_driver` y `teaching_driver` escriben los campos nuevos pero no entienden `--experiment` |
| X2 | `PCARS2-AI/v2/gui.py` | Pestaña Experimental con importación protegida (`try/except`). Contenido en `experimental/gui_tab.py` | Hecho (2026-10-26) |
| X3 | `.gitignore` | Ignorar `experimental/data/` y `experimental/logs/`, conservando los `.gitkeep` | Hecho (2026-10-26) |
| X4a | `PCARS2-AI/src/session_log.py` y `learn_driver.py` | Guardar por tick un bloque `timing` con `sector`, `current_sector_time` y `current_time`. **No toca el parser:** `learn_driver` ya tiene el `TimingsFrame` en cada tick (variable `timings`), solo hay que pasárselo a `record_tick` como parámetro opcional | Hecho (2026-10-26): `timing_diag` en `session_log.py`, `learn_driver` lo pasa en cada tick. El informe marca las pausas del juego y añade la tabla por sectores. Tests en `test_session_log_schema.py` y `test_informe_c0.py` |
| X4b | `PCARS2-AI/src/telemetry_udp.py`, `session_log.py` | Tanda 2: leer del paquete 0 `sTyreFlags`, `sTyreHeightAboveGround`, `sSuspensionVelocity`, `sAirPressure`, `sBrakeTempCelsius`, `sBrakeDamage`, `sSuspensionDamage`, `sEngineTorque`, `sCrashState`; y guardar el paquete 4 (temperatura de pista y ambiente, lluvia, viento) en la cabecera. Verificar offsets con `pcars2_udp_data_reference.md` y probar con datos reales. Es el que necesita R1 (desgaste y daños) y A1 (par motor, frenos) | Pendiente (antes del paso 7) |
| X5 | `PCARS2-AI/src/session_log.py` y `learn_driver.py` | Bloque `conditions` en la cabecera de **todas** las sesiones (`conditions_id` y los ajustes del juego que no llegan por UDP) con `--conditions <id>`. Perfiles en `experimental/conditions/*.json`. Ver sección 6 | Propuesta, sin decidir |

## 4. Hallazgos de la primera prueba C0 (2026-10-26)

Log `20261026T211034Z_sugo_gp_l1_linea` (37 567 ticks, 2 vueltas completas de 3565 m, 40 km/h; vueltas de 5:16 y
5:12). Informe en `experimental/logs/informe_20261026T211034Z_sugo_gp_l1_linea.html`. Ordenados por importancia.

| # | Hallazgo | Consecuencia |
| --- | --- | --- |
| H1 | **Los ejes de `local_acceleration` están cruzados en el código de producción.** El eje 0 es el **lateral** (correlación 1,00 con `v · yaw_rate`; `yaw_rate` positivo = giro a la izquierda, igual que la curvatura de la referencia), el eje 1 el vertical y el eje 2 el **longitudinal**, con signo negativo al avanzar (correlación −0,98 con `dv/dt`; `local_velocity` sale negativa en el eje 2 al avanzar). `obs_universal.py` (líneas 113-114) y `obs_builder.py` (líneas 66-67) usan el eje 2 como lateral y el 0 como longitudinal, y el campo `lat_accel` de los logs es en realidad la aceleración **longitudinal** con signo invertido | (a) El BC se entrenó con esas dos entradas intercambiadas: no es un fallo visible, pero ni la normalización (`MAX_LAT_ACCEL`, `MAX_LONG_ACCEL`) ni la señal significan lo que dicen. (b) La tabla de la sección 1.2 del estudio es de aceleración longitudinal, no lateral: sus conclusiones sobre el rango cubierto hay que rehacerlas con `v · yaw_rate`, disponible en el tercio de logs que tiene el bloque `vehicle`. (c) No se toca producción ahora (P8) |
| H5 | **Tres pausas de datos** de 0,57 a 1,51 s en la vuelta 1 (ticks 5178, 5240 y 6498; `lap_distance` 962, 973 y 1212 m). Durante cada pausa `lap_distance` y la velocidad **no cambian** (962 → 962 en 1,51 s, cuando a 41 km/h habría avanzado 17 m): los datos se congelan. **Causa (confirmada por el usuario): el juego se pausa al hacer clic fuera de su ventana.** No son cruces de sector (no se repiten en la vuelta 2 y dos están a 11 m) | (a) No es un fallo del programa ni de la red. (b) Esos ticks no son datos del coche: un estado congelado con un `Δt` de 1,5 s **envenenaría** el análisis de A y el simulador B. El informe debe marcarlos como «pausa del juego» y los análisis posteriores deben excluirlos (paso 4). (c) Durante una prueba conviene no usar el ratón fuera del juego |
| H9 | **El análisis por sectores es una buena idea** (propuesta del usuario): el juego da `sector` (1-3), `current_sector_time` y los mejores sectores personales y mundiales (paquetes 3 y 7) | Permite comparar tiempos y velocidades medias por sector entre pruebas y contra la referencia de la IA, y localizar en qué tramo se pierde o se rompe algo en la rampa C1. Va con X4a (P14) |
| H7 | **Tamaño:** 1271 B/tick frente a 743 B/tick de un log antiguo (×1,71) | Cierra P1: los 9 millones de ticks serían unos 8,6 GB en vez de 5. El paso a Parquet (D6) compensa buena parte |
| H2 | `tyre_tread_temp` viene en **kelvin** (318-360 K), mientras `tyre_temp` está en °C (45-87) | Convertir al analizar. 45-87 °C cuadra con unos neumáticos que se calientan en la prueba |
| H3 | `fuel_level` = 0,5463, constante: encaja con 18 L sobre una capacidad de 33 L (0,5463 × 33 = 18,0) | Resuelve en parte la duda de `CONFIGURACION_JUEGO.md` (marcador 18 L frente a reglaje 33 L). Falta confirmarlo con el consumo activado |
| H4 | `brake_bias` = 101 constante, que no se parece al reparto 60/40 del reglaje | La codificación es opaca («cuantizado»). Comprobar variando el reglaje; tarea de X4b |
| H6 | Cuatro sobrescrituras `safety_reverse` de 1-2 ticks a unos 2042-2044 m de la vuelta 1 (el evento de vuelta cuenta 4 `overrides`) | Gravedad baja; vigilar si se repiten en el mismo punto |
| H8 | Sin problemas: `|local_velocity|` coincide con la velocidad (error 0,0 %), el recorrido de `position` coincide con `lap_distance` (cociente 1,000) y `yaw_rate` sigue a la curvatura (0,93) | Los campos de X1 son fiables |

`tyre_wear`, `aero_damage` y `engine_damage` salen a cero, y `fuel_level` constante, porque el juego los tiene
desactivados (sección 6).

## 5. Por decidir (ordenado por lo que bloquea)

### 5.1 Bloquean los pasos 4-7 de la línea de trabajo

| # | Pregunta | Propuesta | Bloquea |
| --- | --- | --- | --- |
| P14 | ¿Se añade el análisis por sectores al informe (H9)? | Sí, en cuanto el log traiga `sector` (X4a): tiempo, velocidad media y pausas por sector | Paso 4 |
| P8 | ¿Qué se hace con el eje de aceleración mal asignado en producción (H1)? | Dejarlo en `obs_universal_v1` (el BC se entrenó así) y corregirlo en `universal_v2`, que el roadmap ya prevé | Paso 8 |
| P10 | ¿Se mantienen las asistencias (ABS alto, control de estabilidad auténtico, control de tracción alto) o se quitan? | Mantenerlas ahora y registrarlas; si se quitan, es otro perfil de condiciones y hay que remedir A | Paso 7 |
| P11 | ¿Se registra el perfil de condiciones en todas las sesiones, no solo en las experimentales? | Sí: el ajuste del juego es global y afecta también a la pestaña de aprendizaje (X5) | Paso 7 |
| P13 | ¿Qué reinicia el botón Back del entorno: restablece desgaste y combustible o solo la posición? | Comprobarlo antes de R1 | Paso 7 |
| P9 | ¿Qué condiciones activamos y en qué orden? (sección 6) | R0 base → R1 desgaste y combustible → R2 daños → R3 hora y temperatura → R4 lluvia | Paso 7 |

### 5.2 Se resuelven dentro de su plan

| # | Pregunta | Propuesta |
| --- | --- | --- |
| P6 | Preguntas de la Idea C (sección 4.6 del estudio): vueltas por escalón, paso, techo, qué es vuelta limpia, día o noche, sustituir o convivir | Se resuelven en `PLAN_C_RAMPA_BC.md` |
| P5 | Orden de trabajo | La sección 1 de este documento (sustituye al orden de la sección 6 del estudio) |
| P2 | ¿Un `.bat` por experimento o un lanzador único con subcomandos? | Lanzador único `experimental.bat <modo>` |
| P3 | ¿Se versionan los planes y el diario? | Sí; datos y salidas de análisis no |
| P4 | ¿Cuándo se promueve algo a `PCARS2-AI/src`? | Cuando cumple el criterio de éxito de su plan, tiene tests y se anota aquí |
| P7 | ¿`pyarrow` está en el entorno? Si no, añadirlo a `requirements.txt` | Comprobar antes de D6 |

**Cerradas:** P1 (tamaño de los logs): ×1,71, ver H7. P12 (pausas de datos): el juego se pausa al perder el foco, ver H5.

## 6. Realismo del juego: condiciones activadas (propuesta a debatir)

Hoy está todo en modo prueba: daños, fallos mecánicos, desgaste de neumáticos y consumo de combustible
desactivados, y un clima fijo (19 °C de ambiente, 24 °C de pista, despejado, viento de 3 km/h). Está
documentado en `PCARS2-AI/docs/CONFIGURACION_JUEGO.md` (tabla «Juego → Realismo»). El plan de condiciones
(capa 2, paso 7) está en `PCARS2-AI/docs/ROADMAP_CONDICIONES.md`; allí figura como «Pendiente», y avisa de que
la deuda del solape de gas y freno debe resolverse antes de activar los daños.

### 6.1 Por qué hacerlo

- Los parámetros de la Idea A dejan de ser constantes: el agarre depende de la temperatura y del desgaste
  del neumático, y la masa baja al gastar combustible. Medirlo con las condiciones reales es lo que el
  estudio (sección 2.4) llamaba el riesgo principal.
- La Idea B necesita ese estado (desgaste, combustible, temperaturas) si el simulador va a servir en
  tandas largas. X1 ya lo registra: hoy sale constante y con el juego real empezaría a variar.
- Es lo que haría falta de todos modos para el PPO competitivo y la carrera completa (pasos 5 y 7 del roadmap).

### 6.2 Costes y riesgos

- **Se pierde comparabilidad** con los 9 millones de ticks actuales, grabados con todo desactivado.
- **El ajuste del juego es global:** al activarlo, también cambia lo que ocurre en la pestaña Aprendizaje (BC).
  Por eso el perfil de condiciones debe quedar en la cabecera de **todas** las sesiones (P11).
- **Los daños y los fallos mecánicos pueden acabar una sesión desatendida.** El roadmap exige resolver
  antes el solape de gas y freno: con daños activos, frenar con gas pisado calienta los frenos y provoca fade.
- **Combustible y neumáticos limitan la duración** de una tanda (33 L ≈ 47 vueltas) y hay que saber qué
  restablece el botón Back (P13).
- **Las asistencias** (ABS alto, control de estabilidad auténtico y control de tracción alto, según la
  documentación) alteran los límites que se quieren medir: el ABS limita la frenada, el control de
  tracción la aceleración y el de estabilidad el viraje. Para A, el sistema que se mide es «coche más asistencias».
  Quitarlas es una decisión de condiciones aparte (P10).

### 6.3 Orden propuesto (cada perfil con su `conditions_id`)

| Perfil | Qué activa | Cuándo |
| --- | --- | --- |
| R0 `base_2026-10-25` | Lo de hoy: sin desgaste, combustible ni daños; 19/24 °C, despejado | C1 (rampa del BC), para seguir comparando con el histórico |
| R1 | Desgaste de neumáticos y consumo de combustible, clima fijo | Antes de las sesiones de identificación A1: son cambios graduales y predecibles |
| R2 | Tipo de daño y fallos mecánicos | Solo con el solape de gas y freno resuelto y sesiones vigiladas |
| R3 | Hora del día y temperatura variables (progresión del tiempo, si el juego la permite; comprobar) | Cuando R1 sea estable |
| R4 | Lluvia y clima dinámico | Último y con su propio plan: es otro régimen de agarre |

Las reglas y sanciones se dejarían desactivadas, porque no aportan a la conducción y pueden forzar una
parada en boxes. «Parada en boxes manual» seguiría en No hasta que haya estrategia de box (paso 9 del roadmap).

### 6.4 Qué registrar (X5)

El ajuste del juego no llega por UDP (el roadmap lo dice en la capa 3), así que se anota. La cabecera de cada
sesión llevaría un bloque `conditions` con: `id`, desgaste, carga de combustible, tipo de daño, fallos
mecánicos, asistencias, temperatura de ambiente y de pista, clima, progresión del tiempo y presiones. El perfil
se elegiría en la pestaña Experimental, se guardaría como un fichero en `experimental/conditions/` y
`learn_driver` recibiría `--conditions <id>`, igual que `--experiment`. Cuando X4b parsee el paquete 4 del juego
(clima y temperaturas), los valores reales se guardarían además de los declarados, para detectar
discrepancias.

### 6.5 Qué decidir

P9 (orden), P10 (asistencias), P11 (registrar el perfil en todas las sesiones) y P13 (qué reinicia Back). Antes
de activar R1, una prueba corta que confirme que `tyre_wear` y `fuel_level` pasan a variar en el log.

## 7. Cómo registrar una decisión nueva

Mover la fila de «Por decidir» a «Decisiones tomadas» con la fecha y el motivo, y, si implica tocar código
existente, añadirla a la sección 3. Si cambia el orden de trabajo, actualizar la sección 1.
