# Decisiones

> Estado al 2026-10-26. Se lee de arriba abajo: primero la línea de trabajo (qué toca y en qué orden), luego lo
> decidido, los cambios en código existente, lo descubierto, lo que falta decidir y el perfil de juego elegido.
> Los identificadores (D, X, H, P, R) no cambian de sitio aunque el documento se reordene.

## 1. Línea de trabajo (orden y estado)

| # | Paso | Estado | Depende de |
| --- | --- | --- | --- |
| 1 | Andamiaje de `experimental/`, pestaña en la GUI y reglas (D1-D5, X2, X3) | Hecho | — |
| 2 | Log ampliado y cabecera (D4, X1) e informe de C0 (D8-D10) | Hecho | 1 |
| 3 | Primera ejecución de C0 (40 km/h, 2 vueltas) y hallazgos (sección 4) | Hecho (2026-10-26) | 2 |
| 4 | X4a (`timing` por tick), pausas y sectores en el informe; segunda ejecución de C0 sin pausas | Hecho (2026-10-26) | 3 |
| 5 | Decidir lo que falta antes de tocar nada más: P8, P13, P15 y P16 (sección 5) | **Siguiente** | 4 |
| 6 | Marcar el perfil de juego en la cabecera de todas las sesiones (X5 simplificado) y, si se aprueba, la guardia de daños (P15) | Pendiente | 5 |
| 7 | **C0 corto en el perfil auténtico (RA):** comprobar que `tyre_wear`, `fuel_level`, `aero_damage` y `engine_damage` varían, **validar los offsets de X4b con el informe**, qué reinicia el botón Back (P13), qué clima hay (P21) y cuánto engordan los logs | Pendiente | 6 |
| 8 | C1: rampa 60 → 80 km/h con puerta, ya en RA y con la deuda de gas y freno resuelta o acotada (P16) (`PLAN_C_RAMPA_BC.md`) | Pendiente | 7 |
| 9 | A1: sesiones de identificación en RA (`PLAN_A_LIMITES_COCHE.md`); rehacer el rango lateral con `v · yaw_rate` (H1) | Pendiente | 8 |
| 10 | A2-A4, y B0-B2 solo si A2 sale bien (`PLAN_B_SIMULADOR.md`) | Pendiente | 9 |

El perfil R0 (todo desactivado) ya no se puede volver a medir sin revertir el juego: los 9 millones de ticks
anteriores son su único registro (D11).

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
| D11 | Juego | **Perfil de juego auténtico fijo (RA)**, decidido por el usuario el 2026-10-26: daños completos, fallos mecánicos, desgaste de neumáticos auténtico, combustible real y tiempo real. Se deja así de forma permanente (sección 6). Sustituye al plan por etapas R1-R4 | Datos y política lo más reales posible desde ya, en lugar de pasar por perfiles intermedios |
| D13 | Lluvia | **Los datos con lluvia se conservan**, también los de neumáticos de seco sobre pista mojada: para los planes A y B la cantidad de lluvia y la pérdida de agarre que provoca son información, no ruido. Se etiquetan con el evento `conditions` (X4b). Lo que no se hace es entrenar el BC seco con ellos sin filtrar | Criterio del usuario (2026-10-26). A modela el agarre en función de la humedad y B necesita ese estado; el teacher actual no sabe adaptarse al mojado, así que sus etiquetas ahí valen menos para el BC |
| D12 | Juego | Las asistencias se mantienen como están (conducción «Auténticas»: ABS alto, control de estabilidad auténtico, control de tracción alto; ayuda de bloqueo opuesto activada). Cierra P10 | Es lo que ya conducía el BC; se registran como parte del perfil RA |

## 3. Cambios mínimos en código existente (excepciones a la regla D2)

Cada uno se hace con la menor huella posible y se apunta aquí.

| # | Archivo | Cambio | Estado |
| --- | --- | --- | --- |
| X1 | `PCARS2-AI/src/session_log.py` y `learn_driver.py` | `vehicle_diag` escribe siempre, al final del bloque `vehicle`, los campos de la tanda 1 (`vehicle_extra`): `local_velocity`, `local_accel`, `ang_vel`, `position`, `orientation`, `ride_height`, `susp_travel`, `tyre_temp`, `tyre_tread_temp`, `tyre_wear`, `fuel_level`, `brake_bias`, `aero_damage`, `engine_damage`, `raw_throttle`, `raw_brake`, `clutch`. La cabecera lleva `log_schema` (2), `origin` y `experiment`. `learn_driver --experiment <nombre>` marca `origin=experimental`; sin él, `origin=main`. Tests en `tests/test_session_log_schema.py` | Hecho (2026-10-26). La pestaña lo pasa a través de `aislado.py`. Solo toca `learn_driver`; `imitation_driver` y `teaching_driver` escriben los campos nuevos pero no entienden `--experiment` |
| X2 | `PCARS2-AI/v2/gui.py` | Pestaña Experimental con importación protegida (`try/except`). Contenido en `experimental/gui_tab.py` | Hecho (2026-10-26) |
| X3 | `.gitignore` | Ignorar `experimental/data/` y `experimental/logs/`, conservando los `.gitkeep` | Hecho (2026-10-26) |
| X4a | `PCARS2-AI/src/session_log.py` y `learn_driver.py` | Guardar por tick un bloque `timing` con `sector`, `current_sector_time` y `current_time`. **No toca el parser:** `learn_driver` ya tiene el `TimingsFrame` en cada tick (variable `timings`), solo hay que pasárselo a `record_tick` como parámetro opcional | Hecho (2026-10-26): `timing_diag` en `session_log.py`, `learn_driver` lo pasa en cada tick. El informe marca las pausas del juego y añade la tabla por sectores. Tests en `test_session_log_schema.py` y `test_informe_c0.py` |
| X4b | `PCARS2-AI/src/telemetry_udp.py`, `session_log.py` | Tanda 2: leer del paquete 0 `sTyreFlags`, `sTyreHeightAboveGround`, `sSuspensionVelocity`, `sAirPressure`, `sBrakeTempCelsius`, `sBrakeDamage`, `sSuspensionDamage`, `sEngineTorque`, `sCrashState`; y guardar el paquete 4 (temperatura de pista y ambiente, lluvia, viento) en la cabecera. Verificar offsets con `pcars2_udp_data_reference.md` y probar con datos reales. **Ahora es más urgente:** con daños completos y tiempo real hacen falta los daños por rueda, la temperatura de frenos y la temperatura de pista | **Hecho (2026-10-26), pendiente de validar con el juego.** `telemetry_udp.py`: 10 campos nuevos en `TelemetryFrame` (con valor por defecto) y `parse_game_state` para el paquete 4, que `DriveSession` guarda en `game_state`. `session_log.py`: los campos van al final del bloque `vehicle` (`tyre_flags`, `tyre_height`, `brake_damage`, `susp_damage`, `brake_temp`, `susp_vel`, `air_pressure`, `engine_torque`, `crash_state`, `tick_count`, `car_flags`) y el tiempo atmosférico sale como evento `conditions` cuando cambia (se emite en `learn_driver`). Los offsets nuevos se **deducen** de la estructura de SMS y se contrastan con los 13 ya conocidos, pero no se han visto con datos reales: el informe de C0 trae comprobaciones de plausibilidad para confirmarlos. Del paquete 4 solo se interpretan los offsets 15-21 (temperaturas, lluvia, nieve, viento); los bytes 12-23 se guardan en hexadecimal por si hace falta revisarlos. `car_flags` se guarda entero: el **bit 4 es «ABS activo»**, la señal directa más barata de poco agarre al frenar. Tests en `test_telemetry_x4b.py` y `test_informe_c0.py` |
| X5 | `PCARS2-AI/src/session_log.py` | **Simplificado por D11:** como el perfil de juego ya es único, basta una constante `GAME_PROFILE = "real_2026-10-26"` escrita en la cabecera de todas las sesiones (se cambia a mano si se tocan los ajustes del juego). Distingue las sesiones nuevas de las antiguas (sin campo, perfil R0). Sustituye al bloque `conditions` y a `--conditions` de la propuesta anterior | Hecho (2026-10-27): constante `GAME_PROFILE` en `session_log.py`, escrita como `game_profile` en la cabecera (antes de `session_meta`, que puede sobrescribirla). Test en `test_session_log_schema.py` |
| X6 | `PCARS2-AI/src/learn_driver.py` | Guardia de daños y registro completo de daños (P15). `DamageWatch` (en `session_log.py`) vigila **todos** los canales: `aero_damage`, `engine_damage`, `brake_damage` y `susp_damage` por rueda y neumático arrancado (bit 0 de `tyre_flags`). Cada empeoramiento emite un evento `damage` con lo que cambió, los niveles y el contexto (velocidad, pedales, rpm, temperatura de frenos y neumáticos, `crash_state`, `car_flags`, posición en la vuelta). El evento se registra **siempre**; `--stop-on-damage` además cierra la sesión, y `aislado.py` lo activa siempre | Hecho (2026-10-27). La línea base es el primer tick, así que un coche que ya empieza dañado no dispara el evento, y una reparación no cuenta. Pendiente: que el informe de C0 liste los eventos `damage` y validar con el juego qué escala tienen los bytes de daño |

## 4. Hallazgos de C0 (2026-10-26)

Primera ejecución: log `20261026T211034Z_sugo_gp_l1_linea` (37 567 ticks, 2 vueltas completas de 3565 m, 40 km/h; vueltas
de 5:16 y 5:12). Segunda, con X4a: `20261026T215249Z_sugo_gp_l1_linea` (37 564 ticks). Informes en
`experimental/logs/`. Ordenados por importancia.

| # | Hallazgo | Consecuencia |
| --- | --- | --- |
| H1 | **Los ejes de `local_acceleration` están cruzados en el código de producción.** El eje 0 es el **lateral** (correlación 1,00 con `v · yaw_rate`; `yaw_rate` positivo = giro a la izquierda, igual que la curvatura de la referencia), el eje 1 el vertical y el eje 2 el **longitudinal**, con signo negativo al avanzar (correlación −0,98 con `dv/dt`; `local_velocity` sale negativa en el eje 2 al avanzar). `obs_universal.py` (líneas 113-114) y `obs_builder.py` (líneas 66-67) usan el eje 2 como lateral y el 0 como longitudinal, y el campo `lat_accel` de los logs es en realidad la aceleración **longitudinal** con signo invertido | (a) El BC se entrenó con esas dos entradas intercambiadas: no es un fallo visible, pero ni la normalización (`MAX_LAT_ACCEL`, `MAX_LONG_ACCEL`) ni la señal significan lo que dicen. (b) La tabla de la sección 1.2 del estudio es de aceleración longitudinal, no lateral: sus conclusiones sobre el rango cubierto hay que rehacerlas con `v · yaw_rate`, disponible en el tercio de logs que tiene el bloque `vehicle`. (c) No se toca producción ahora (P8). **Reproducido** en la segunda ejecución (eje lateral 0, correlación 1,00; campo antiguo −0,02) |
| H11 | **La documentación del juego tenía un dato equivocado:** `CONFIGURACION_JUEGO.md` dice «Ayuda de bloqueo opuesto: Desact.», pero las dos capturas del usuario (antes y después del cambio a RA) muestran **Activ.** También aparecen dos opciones que el documento no recoge: «Cámaras cinemáticas en boxes» y «Vuelta de Honor manual», ambas Desact. | La ayuda de bloqueo opuesto corrige derrapes, así que afecta a la dinámica de viraje que mide la Idea A. Se registra como una asistencia más del perfil (D12) y hay que corregir `CONFIGURACION_JUEGO.md` (P17) |
| H12 | **El juego no expone la humedad ni el mojado de la pista.** Por UDP solo llegan: densidad de lluvia y de nieve (lo que cae, no lo que hay en el suelo), temperatura de ambiente y de pista, viento, el tipo de superficie por rueda (`sTerrain`: asfalto, poco agarre, hierba, grava…, sin categoría de «mojado»), la temperatura de los neumáticos y el bit de ABS activo. No hay humedad ambiental, ni agua en el asfalto, ni charcos, ni línea seca (revisado en `pcars2_udp_data_reference.md` y `pcars2_surface.py`; el paquete de estado del tiempo, tipo 5, «no se envía actualmente») | Las situaciones intermedias (unas gotas, asfalto húmedo sin lluvia, llovizna que luego seca) **no se pueden leer directamente**: hay que estimarlas (P22). A 40 km/h el coche no llega al límite de agarre, así que ese estado casi no se ve en una conducción tranquila |
| H5 | **Tres pausas de datos** de 0,57 a 1,51 s en la vuelta 1 (ticks 5178, 5240 y 6498; `lap_distance` 962, 973 y 1212 m). Durante cada pausa `lap_distance` y la velocidad **no cambian** (962 → 962 en 1,51 s, cuando a 41 km/h habría avanzado 17 m): los datos se congelan. **Causa (confirmada por el usuario): el juego se pausa al hacer clic fuera de su ventana.** No son cruces de sector (no se repiten en la vuelta 2 y dos están a 11 m) | **Confirmado:** en la segunda ejecución, sin clics fuera del juego, hay 0 pausas y el reloj del juego avanza con el del PC. (a) No es un fallo del programa ni de la red. (b) Esos ticks no son datos del coche: un estado congelado con un `Δt` de 1,5 s **envenenaría** el análisis de A y el simulador B. El informe los marca como «pausa del juego» y los análisis posteriores deben excluirlos. (c) Durante una prueba conviene no usar el ratón fuera del juego |
| H9 | **El análisis por sectores es una buena idea** (propuesta del usuario): el juego da `sector` (1-3), `current_sector_time` y los mejores sectores personales y mundiales (paquetes 3 y 7) | Permite comparar tiempos y velocidades medias por sector entre pruebas y contra la referencia de la IA, y localizar en qué tramo se pierde o se rompe algo en la rampa C1. Hecho con X4a (P14): ver H10 |
| H10 | **Fronteras de sector en Sugo GP** (lap_distance, vuelta de 3565 m): sector 1 de 0 a 1448 m (127,0 s a 41 km/h), sector 2 de 1449 a 2383 m (81,8 s), sector 3 de 2383 a 3565 m (103,3 s). Vuelta 2 en 312,1 s; vuelta 1, 315,1 s. Artefacto conocido: antes de cruzar la línea de salida el juego aún marca sector 3 durante unos 114 ticks, y por eso el sector 1 de la vuelta 1 muestra 130,0 s de reloj del juego frente a 127,0 s de conducción | Las fronteras sirven para repartir el análisis de C1 por tramos. A 40 km/h la velocidad media es igual en los tres (41,1-41,2), por lo que la tabla será informativa cuando la velocidad objetivo suba |
| H7 | **Tamaño:** 1271 B/tick frente a 743 B/tick de un log antiguo (×1,71); con el bloque `timing` de X4a, 1345 B/tick (×1,81) | Cierra P1: los 9 millones de ticks serían unos 9 GB en vez de 5. El paso a Parquet (D6) compensa buena parte |
| H2 | `tyre_tread_temp` viene en **kelvin** (318-360 K), mientras `tyre_temp` está en °C (45-87) | Convertir al analizar. 45-87 °C cuadra con unos neumáticos que se calientan en la prueba |
| H3 | `fuel_level` = 0,5463, constante: encaja con 18 L sobre una capacidad de 33 L (0,5463 × 33 = 18,0) | Resuelve en parte la duda de `CONFIGURACION_JUEGO.md` (marcador 18 L frente a reglaje 33 L). Con el combustible real debería empezar a bajar: se comprueba en el paso 7 |
| H4 | `brake_bias` = 101 constante, que no se parece al reparto 60/40 del reglaje | La codificación es opaca («cuantizado»). Comprobar variando el reglaje; tarea de X4b |
| H6 | Cuatro sobrescrituras `safety_reverse` de 1-2 ticks a unos 2042-2044 m de la vuelta 1 (el evento de vuelta cuenta 4 `overrides`) | No se repitieron en la segunda ejecución (0 incidencias): fue un hecho aislado |
| H8 | Sin problemas: el módulo de `local_velocity` coincide con la velocidad (error 0,0 %), el recorrido de `position` coincide con `lap_distance` (cociente 1,000) y `yaw_rate` sigue a la curvatura (0,93) | Los campos de X1 son fiables |

Hasta aquí `tyre_wear`, `aero_damage` y `engine_damage` salían a cero y `fuel_level` constante porque el juego los tenía
desactivados (perfil R0). Con RA (D11) esto debe cambiar.

## 5. Por decidir (ordenado por lo que bloquea)

### 5.1 Bloquean la línea de trabajo

| # | Pregunta | Propuesta | Bloquea |
| --- | --- | --- | --- |
| P15 | Con daños completos y fallos mecánicos, ¿se para la sesión sola cuando aparece daño? | Sí: `--stop-on-damage` (X6), siempre activo en las pruebas lanzadas desde la pestaña. Una sesión desatendida con el coche dañado produce datos que ya no son del mismo coche | Paso 6 |
| P13 | ¿Qué reinicia el botón Back del entorno: restablece desgaste, combustible y **daños**, o solo la posición? | Comprobarlo en el paso 7 con una prueba corta. Si el daño persiste, hace falta reparar o reiniciar la sesión para volver a empezar | Paso 7 |
| P16 | La deuda del solape de gas y freno (`ROADMAP_CONDICIONES.md`) debía resolverse **antes** de activar los daños, y ya están activados. ¿Se resuelve antes de C1? | Sí, la primera pieza (`--pedal-exclusive`, sin reentrenar). A 40 km/h el efecto será pequeño, pero a 60-80 km/h de la rampa calentará frenos y puede provocar fade y fallos mecánicos | Paso 8 |
| P21 | Con «Clima real» habrá días con poca lluvia o ninguna y otros con más. Con la decisión D13 (los datos mojados se conservan), ¿cómo se etiquetan y se protege la sesión? | (1) **Etiquetar:** el evento `conditions` ya trae la densidad de lluvia; en el análisis de A y B se usa como variable de estado. (2) **Límite del dato:** el UDP da la lluvia que cae, **no la humedad de la pista**, que va con retraso; hace falta una variable derivada (lluvia acumulada reciente) y vigilar el agarre real (aceleración lateral frente a `v²·κ`). (3) **BC seco:** filtrar por `rain = 0` al construir su dataset, que es código de producción y va aparte. (4) **Seguridad:** con neumáticos de seco y daños completos, un trompo en mojado deja el coche dañado; mantener la guardia de daños (P15) y fijar un umbral de lluvia a partir del cual se para o se baja la velocidad objetivo | Paso 6 |
| P22 | ¿Cómo se estima el estado de humedad de la pista, ya que el juego no lo da (H12)? | **Tres escalones, de lo barato a lo fino.** (1) **Humedad derivada con memoria:** `W(t) = W(t−Δt)·exp(−Δt/τ) + k·lluvia·Δt`, de modo que tras `rain = 0` la pista sigue «húmeda» un tiempo que depende de τ (se ajusta con los datos; la temperatura de pista y el viento la acortarán). Cubre **gotas aisladas** (W casi nula, se descartan por umbral y duración) y **llovizna que luego se seca** (W sube y decae). (2) **Sondas de agarre naturales:** en cada vuelta, la zona de frenada más fuerte y sus picos de deceleración, la fracción de ticks con ABS activo (`car_flags`) y el deslizamiento de ruedas (`tyre_rps` frente a la velocidad). Detectan **asfalto húmedo sin lluvia** (humedad ambiental, rocío), que ninguna variable de lluvia ve. (3) **Sondas explícitas** en A1: la misma frenada a fondo repetida en cada estado, para medir `a_freno` frente a W. Las dos primeras se calculan al analizar, sin tocar el juego ni la producción | Paso 6 |
| P19 | ¿Cuánto combustible hay al salir y cuántas vueltas da? El marcador decía 18 L y el reglaje 33 L (47 vueltas); la carrera está en 50 | Medirlo en el paso 7: consumo por vuelta a 40 km/h y litros al salir. Si salen 18 L, la tanda queda en unas 25 vueltas (2 h). Subir la carga en el reglaje si hace falta | Paso 7 |
| P18 | ¿Se fija una fecha personalizada en vez de «Fecha actual»? | Sí: con «Fecha actual» cada día cambia la fecha y, con ella, la temperatura base. Fijada, todas las sesiones empiezan igual (misma fecha y hora) y solo se mueve la hora | Paso 7 |
| P8 | ¿Qué se hace con el eje de aceleración mal asignado en producción (H1)? | Dejarlo en `obs_universal_v1` (el BC se entrenó así) y corregirlo en `universal_v2`, que el roadmap ya prevé | Paso 9 |

### 5.2 Se resuelven dentro de su plan

| # | Pregunta | Propuesta |
| --- | --- | --- |
| P20 | ¿Se quita la ayuda de bloqueo opuesto (y, más adelante, ABS, estabilidad y tracción) para acercarse a un coche real? | **Ahora no.** Mantenerla hasta que C1 deje el BC estable y medir su efecto en A1 con y sin ella (un perfil RA2). Quitarla ya sumaría un sexto cambio a la vez que los cinco de RA y confundiría las causas | Tras C1 |
| P17 | Actualizar `PCARS2-AI/docs/CONFIGURACION_JUEGO.md` con el perfil RA, la ayuda de bloqueo opuesto (H11) y su registro de cambios | Sí; es el documento de referencia de producción. Se hace aparte, sin mezclarlo con `experimental/` |
| P6 | Preguntas de la Idea C (sección 4.6 del estudio): vueltas por escalón, paso, techo, qué es vuelta limpia, día o noche, sustituir o convivir | Se resuelven en `PLAN_C_RAMPA_BC.md` |
| P5 | Orden de trabajo | La sección 1 de este documento (sustituye al orden de la sección 6 del estudio) |
| P2 | ¿Un `.bat` por experimento o un lanzador único con subcomandos? | Lanzador único `experimental.bat <modo>` |
| P3 | ¿Se versionan los planes y el diario? | Sí; datos y salidas de análisis no |
| P4 | ¿Cuándo se promueve algo a `PCARS2-AI/src`? | Cuando cumple el criterio de éxito de su plan, tiene tests y se anota aquí |
| P7 | ¿`pyarrow` está en el entorno? Si no, añadirlo a `requirements.txt` | **No está instalado** (comprobado 2026-10-26): `pandas` y `matplotlib` sí. Instalarlo antes de D6 |

**Cerradas:** P1 (tamaño de los logs): ×1,81, ver H7. P12 (pausas de datos): el juego se pausa al perder el foco, ver H5.
P14 (análisis por sectores): hecho, ver H10. P9 (condiciones y orden): perfil único RA, ver D11. P10 (asistencias): se
mantienen, ver D12. P11 (registrar el perfil en todas las sesiones): sí, con la constante de X5.

## 6. Perfil de juego auténtico (RA)

Elegido por el usuario el 2026-10-26 y **fijo a partir de ahora** (D11). Ajustes visibles en las capturas de
Opciones → Juego → Realismo:

| Opción | Antes (R0) | Ahora (RA) |
| --- | --- | --- |
| Asistencia de dirección | No | No |
| Asistencia al frenado | No | No |
| Asistencias de conducción | Auténticas (ABS alto, estabilidad auténtico, tracción alto) | Auténticas (igual) |
| Ayuda de bloqueo opuesto | Activ. (la documentación decía Desact.; ver H11) | Activ. |
| **Tipo de daño** | Desact. | **Daños completos** |
| **Fallos mecánicos** | No | **Sí** |
| **Desgaste de los neumáticos** | Desact. | **Auténtico** |
| **Uso de combustible** | Desact. | **Real** |
| Arranque automático | Sí | Sí |
| Reglas y sanciones | Desact. | Desact. |
| Parada en boxes manual | No | No |
| Cámaras cinemáticas en boxes / Vuelta de Honor manual | Desact. | Desact. |
| **Tiempo** | Fijo (19 °C ambiente, 24 °C pista, despejado, viento 3 km/h) | **Hora y clima reales** (ver «Configuración de carrera», abajo) |

Configuración de carrera (captura del 2026-10-26):

| Opción | Valor |
| --- | --- |
| Tipo de duración / número de vueltas | Vueltas / 50 |
| Tipo de fecha | Fecha actual (26/10/2026) |
| Hora de inicio | **10:00** (antes 13:00) |
| **Progreso del tiempo** | **Tiempo real** |
| Temporada | Otoño |
| Previsión meteorológica | **Clima real** (antes, 4 estados fijados en Despejado) |
| Progresión meteorológica | Sincronizado a carrera |
| Tipo de salida | Clasificación |
| Vuelta de formación / parada en boxes obligatoria | No / No |

**Actualización (mismo día):** la captura mostraba cuatro estados fijados en «Despejado». El usuario ha cambiado después
la previsión a **«Clima real»** (el tiempo real actual de la ubicación) y la hora de inicio a **10:00**, para tener más
horas de luz. Con eso **sí puede haber condiciones adversas** (lluvia, viento, frío) según el día: es el antiguo R4
y entra sin etapa intermedia. Ver 6.2 y P21.

### 6.1 Qué cambia respecto al plan por etapas

El plan anterior (R1 desgaste y combustible → R2 daños → R3 tiempo → R4 lluvia) servía para introducir las
condiciones poco a poco. Se salta: todo entra a la vez, incluida la posibilidad de lluvia. Eso es una decisión legítima, pero quita la protección de ir
paso a paso, de modo que los riesgos pasan a mitigarse con comprobaciones y guardias (6.3).

### 6.2 Consecuencias

- **R0 no se puede volver a medir** sin revertir el juego. Los 9 millones de ticks anteriores son su único registro y
  no son comparables con los nuevos: otra masa (el combustible baja), otro agarre (el neumático se desgasta y se
  calienta) y, con tiempo real, otra temperatura de pista según la hora.
- **Los datos dejan de ser estacionarios:** el agarre depende de la hora del día, de las vueltas dadas y del combustible.
  Las pruebas de A tendrán que repetirse o ajustarse en función de esas variables (por eso el log ya trae desgaste,
  temperaturas y combustible).
- **Los daños completos hacen que un choque tenga consecuencias persistentes:** el coche queda con peor rendimiento y
  los datos siguientes ya no son del mismo coche. Un fallo mecánico puede cortar la sesión. De ahí P15 y P13.
- **La deuda de gas y freno** (P16) era requisito para activar daños y no se ha resuelto.
- **Las sesiones largas** quedan acotadas por el combustible (33 L de capacidad; unas 47 vueltas según el reglaje) y por
  el desgaste de los neumáticos. Con el reglaje y el desgaste auténtico, la rampa C1 de varias horas podría necesitar
  boxes o reinicios.
- **El tiempo real exige registrar las condiciones externas:** temperatura de pista y ambiente, lluvia y viento llegan
  en el paquete 4 (X4b). Con salida a las 10:00 y fecha actual hay
  unas 6-7 horas de luz en otoño; la temperatura de la pista sube hasta el mediodía y baja después, y el clima real
  puede traer lluvia o viento: el agarre no será estacionario. Los datos con lluvia sirven a A y B si están etiquetados (D13);
  para el BC seco hay que filtrarlos (P21).
- **Duración frente a combustible:** la carrera está en 50 vueltas (unas 4,4 horas a 40 km/h) y el combustible no da
  para tanto: P19.

### 6.3 Qué hacer para que sea seguro y analizable

1. **Marcar las sesiones** con `GAME_PROFILE` en la cabecera (X5): distingue lo grabado en RA de lo grabado en R0.
2. **Guardia de daños** (X6, P15) en las pruebas desde la pestaña.
3. **C0 corto en RA** (paso 7): comprobar que los campos de desgaste, combustible y daño varían, y qué hace Back (P13).
4. **`--pedal-exclusive`** antes de C1 (P16).
5. **Leer el paquete 4 y los daños por rueda** (X4b): hecho, falta validarlo con el juego (paso 7).

## 7. Cómo registrar una decisión nueva

Mover la fila de «Por decidir» a «Decisiones tomadas» con la fecha y el motivo, y, si implica tocar código
existente, añadirla a la sección 3. Si cambia el orden de trabajo, actualizar la sección 1.
