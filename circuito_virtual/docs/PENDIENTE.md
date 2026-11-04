# Pendiente de circuito_virtual

Estado al cierre de la jornada del **2026-11-03** (V1-V86). Lo que no es del circuito (rampa del BC, PPO, daño
de motor P26, controles de seco, reentreno v2) está en `experimental/docs/PENDIENTE.md`. El plan está
en `docs/PLAN.md`, las decisiones en `docs/DECISIONES.md` y la historia en `docs/DIARIO.md`.

**Qué significan las «V»:** cada Vnn es una entrada del registro de decisiones (hoy V1-V86), no una
versión del software. La versión del software es el commit de git, que cada sesión guarda en la
cabecera de su log. Este documento recoge solo el estado actual y lo que sigue; las cifras de sesiones
anteriores son referencia (están en `DECISIONES.md`) y cada sesión nueva se juzga contra el criterio de
volante de más abajo, no contra la anterior.

## Dónde estamos

- **Estado del código:** Último commit de código `5af3bf2` (umbral de prominencia del recorte, V82; antes `c5606c9`: recorte de picos, V79, y grabador manual de D1b, V77). Documentos: V80-V83 en `f1c276a`, V84-V85 en `18dda11` y V86 en el commit siguiente. Los logs de la próxima sesión llevarán en la cabecera el hash de `HEAD` de ese momento.
- **Tests en verde:** `circuito_virtual` 78, `experimental` 113, `PCARS2-AI` 552 (ruff limpio salvo los avisos antiguos de `resumen_sesion.py` y `test_resumen_sesion.py`). Se lanzan con
  `pytest` dentro de cada carpeta.
- **Teacher** (`teacher_controller.py`, `learn_driver.py`): cada opción es opt-in y su valor por
  defecto es el de producción.
- **Archivos locales no versionados** (4,5 MB cada uno): `circuito_virtual/pistas/sugo_gp/` con
  `sugo_smooth.json`, `sugo_optima_a1mu9.json`, `sugo_optima_a1mu9b.json`, `sugo_optima_a1mu9c15.json` y
  `sugo_optima_a1mu9c12.json`. Cómo regenerarlos, en «Comandos vigentes».

## Próxima sesión: prueba de banda 135 km/h con la línea óptima (V86)

**Receta vigente confirmada (V85-V86): línea óptima `a1mu9c12` a 125 km/h con la técnica de pedales, `--lat-accel-limit 9.5`, `--lat-gain-v0-kmh 70`, `--profile-peak-min-m 60` y `--profile-peak-min-kmh 8`.** Seis vueltas (`230452Z`): 118,6-118,7 s estables, parejas 3-4, 4-5 y 5-6 cumplen V19, C3 / C8 / C9 se estabilizan (1,36 / 0,74 / 0,54 m), 17 ticks con rueda fuera (piano de C4) y ninguno en la hierba, neumáticos de 74 a 51 (delanteros) y 38 (traseros) sin romper nada. Comando en «Comandos vigentes».

**Una variable respecto a la receta vigente: `--speed-band 135`** (es la prueba de banda del punto 3 de «Siguiente»; ya con el volante limpio, ahora toca la velocidad). El solver (μ 9, tablas de A1) prevé para esta línea **115,3 s a 135 km/h** (118,4 a 125, medido 118,6; 114,1 a 140; 112,2 a 150). El perfil de consigna no depende de la banda, así que el recorte y el umbral 8 valen tal cual. El 70 ya está puesto, que es lo que pide por encima de 135 (V42). Ctrl+C a mano, en seco y delante del juego, y atento en la primera vuelta: la recta tras C8 (1445-1490 m) tocaba hierba a 124 km/h con la línea suavizada, la frenada a C9 pasa de 126 a 68 km/h y la última recta (3113-3567 m) es donde más se gana.

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --teacher-only --speed-band 135 --max-gear 3 --lat-accel-limit 9.5 --steer-ff-gain 0.003 --steer-ff-v0-kmh 0 --steer-ff-cap-kmh 100 --steer-preview-s 0.3 --steer-slip-gain 5 --lat-gain-v0-kmh 70 --throttle-max 1.0 --brake-decel-straight 10 --brake-overspeed-straight-ms 2.5 --brake-slip-limit 0.25 --brake-slip-hold 0.85 --pedal-technique --brake-profile --brake-circle 10 --exit-circle 14.6 --profile-peak-min-m 60 --profile-peak-min-kmh 8 --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_optima_a1mu9c12.json --experiment a2_optA1mu9c12_135_g3_lat95_slip5_v70_ff0_cap100_pv03_gas1_fr10_perfil_c10_slip_exit146_pico60_prom8_l4 --laps 4
```

**Comprobado sin lanzar (2026-11-03):** `a2_error` devuelve `None` para esta combinación (el techo de la 3.ª es 150 km/h) y `build_argv` pasa `--speed-band 135` a `learn_driver.py`. **Antes de lanzar:** `git status` limpio (el log llevará el hash de `HEAD`; el `.svg` suelto de la raíz no cuenta), el usuario delante del juego, en seco y con Ctrl+C a mano.

**Éxito (exploratorio, se juzga contra V19):** tiempo ≈ 115,3-116,5 s; una pareja de vueltas que cumpla V19; 0 ticks en la hierba (mirar 1444-1470 m); sin ruedas paradas ni bloqueo al frenar (razón traseras/delanteras ≥ 0,9; la frenada fuerte está validada hasta 150 km/h con el limitador); cambios de marcha limpios (3.ª desde ≈ 115 km/h). Mirar la tabla por curva (C9, C10, C11 y C12-C14 primero: las más rápidas) y el perfil de las rectas (CTE y volante). **Si rompe** (oscila, se sale o pasa de 1,8 m en zonas rápidas): Ctrl+C, apuntar dónde y volver a 125; **si funciona,** repetir 140 y, con el usuario atento, 150 (techo de la 3.ª).

**Qué mirar en el informe de 135 (además de los cinco pasos de «Cómo analizar el informe»):**

1. **Tiempo:** contra la previsión del solver, 115,3 s (a 125 km/h el solver acertó con +0,2 s; una diferencia de hasta ≈ 1 % es normal). Vueltas 2-4; la 1.ª lleva la salida parada.
2. **Velocidad en curva:** como el perfil no depende de la banda, la v mín. de cada curva debería salir igual que en la base (± 1 km/h). Si baja o sube más, algo cambió en la llegada a la curva (frenada tardía o corta): mirar el pedal y la distancia de frenada de esa curva.
3. **Rectas:** velocidad máxima de cada recta (¿llega a 135 km/h?), \|CTE\| y volante en 2555-2655 m y 3113-3567 m, y si el gas llega a fondo; el cambio a 3.ª (≈ 115 km/h) debe quedar antes de las rectas rápidas.
4. **Frenadas desde 135:** deceleración (`pedales_sesion.py`), pedal máximo (≈ 0,95 con el limitador) y bloqueo medido en las delanteras y en las traseras por separado (regla de «Reglas de la sesión»), no solo con la razón traseras/delanteras. Referencia: 11,0-11,4 m/s² desde 140 km/h con el limitador (V55).
5. **Hierba y piano:** separar el terreno 48 de la hierba (7); mirar sobre todo 1444-1470 m (tras C8) y la salida de C9.
6. **Neumáticos:** a más velocidad se enfrían igual o más; mirar `tyre_temp` por vuelta si alguna curva sube por vuelta, como en V86.

**Si funciona y cumple V19:** misma sesión con `--speed-band 140` (solo cambia la banda y el nombre del experimento, `…_140_…`); el solver prevé 114,1 s y el techo de la 3.ª está limpio hasta 140 km/h (V43). Después, 150 km/h (prevé 112,2 s) **solo con el usuario atento**: está fuera de las tablas del solver (llegan a 140) y la aceleración por encima de 140 con el volante tranquilo no está validada. **Si no cumple V19 pero no es peligroso:** apuntar qué curva o recta falla y por cuánto, y decidir una variable aparte (ganancia, tope del gas, frenada) antes de repetir; no subir de banda con el volante sucio.

**Pendiente aparte (no mezclar):** inversiones del gas en C12-C14 (6-9 por vuelta), freno en C12-C13, deriva de C6 (3,1-3,6°) y C11 de la vuelta 2 (1,60-1,85 m según la sesión).

**Cómo analizar el informe** (el usuario pasa el HTML; el log está en `PCARS2-AI\logs\learning\`; anteponer `PYTHONIOENCODING=utf-8`):

1. `experimental\common\resumen_sesion.py <log>` (sin `--previsto`: comparar con la base de abajo, no con una previsión puesta a mano). V19 por parejas.
2. Tabla por curva del JSON del informe (`experimental/logs/informe_<ts>_sugo_gp_l1_linea.json`, clave `curvas`: `v_min`, `cte_max`, `lat_max`, `freno_max` por vuelta), sobre todo C5, C6, C9, C10, C11 y C12-C14.
3. `experimental\common\pedales_sesion.py <log> --vueltas 2,3,4`: inversiones del gas en curva y rebotes del gas.
4. Perfil de la vuelta 3 en 860-950 m (C5-C6) y 2650-3120 m (C12-C14): gas, freno y velocidad cada 10-25 m.
5. Ruedas fuera: separar el terreno 48 (pintura sobre hormigón, el piano de C4, probablemente legal) de la hierba (terreno 7, recta tras C8).

**Base para comparar** (receta vigente de la línea óptima, 6 vueltas: `230452Z`, V86; 4 vueltas: `225202Z`, V85): vueltas 2-6 de 118,6 / 118,6 / 118,7 / 118,7 / 118,7 s; \|CTE\| máx. 1,85 / 1,56 / 1,65 / 1,61 / 1,57 m; deriva máx. 3,1 / 3,3 / 3,4 / 3,6 / 3,2° (C6 la más alta); lateral máx. 13,4-14,1 m/s²; parejas 3-4, 4-5 y 5-6 cumplen V19 (la 1-2 y la 2-3 solo fallan por C11 en las vueltas 1-2, 1,84 y 1,85 m); 12-13 frenadas por vuelta, 26-27 inversiones del gas en curva y rebotes del gas en 747 y 1286-1287 m; 17 ticks con rueda fuera (terreno 48, piano de C4, vuelta 4), 0 en la hierba; por curva (vueltas 2-6): C2 1,10-1,12 m, C3 1,04 → 1,36 m, C8 0,60 → 0,74 m, C9 0,45-0,65 m, C11 1,85 / 1,56 / 1,65 / 1,55 / 1,48 m, C12-C13 0,83-0,91 m; C5-C6 sin freno; neumáticos de 74 / 71 °C en la vuelta 1 a 51 / 38 en la 6. Con `--lat-gain-v0-kmh 60`: `223851Z`, V84. Línea suavizada: `221745Z`, V83; anteriores en V76 y V80-V81. Solver (V86) para esta línea: 118,4 s a 125 km/h, 115,3 a 135, 114,1 a 140, 112,2 a 150.

## Seco y mojado: no se mezclan

Todo lo de este documento (receta, base de comparación, V19, solver μ 9, previsiones) es **en seco**. Las sesiones en mojado son exploratorias, van aparte y nunca se comparan con la base ni se juzgan con V19.

- **Cómo se distinguen:** el registro `conditions` del log trae `rain` (0 en seco; 153 el 2026-11-04) y las temperaturas. El informe `informe_lineas_teacher.py` los separa por ese campo (tabla en seco y tabla en mojado), no por el nombre. Aun así, el experimento lleva `a2_mojado_` en el nombre.
- **Los datos de seco no se tocan:** los buffers de BC (`c0_log`, `teacher_<banda>`) no incluyen los `a2_*`, y las tablas de A1 / `parametros_a1.json` salen de logs concretos.
- **Primera sesión en mojado** (2026-11-04, `213459Z`, banda 100, límite lateral 6, sin recorte de picos, 2 vueltas): 146,55 / 146,58 s, sin bloqueo ni ABS; la vuelta 1 limpia (|CTE| 0,78 m, deriva 1,2°), la 2 con un patinazo en C5-C6 (|CTE| 4,66 m, deriva 8,3°, hierba y franja a 930-950 m) y salidas en C8 y C10-C11. Hipótesis sin comprobar: sin el recorte el coche acelera entre C5 y C6 y entra en C6 pasado. Si se repite, una variable: añadir `--profile-peak-min-m 60` (el umbral de 8 km/h está calibrado para 9,5, no para 6).
- **Segunda sesión mojada** (`220304Z`, con `--profile-peak-min-m 60 --profile-peak-min-kmh 8`): el recorte arregló C5-C6 (|CTE| de 4,66 a 2,00 m con las gomas igual de frías), pero la vuelta 2 siguió sin quedar limpia por el bamboleo de la recta C6→C7 (|CTE| 2,6 m, deriva 5,6°).
- **`--lat-adapt` (límite lateral por curva, `PCARS2-AI/src/lat_adapt.py`, opt-in):** cada curva (C1-C14) tiene un multiplicador sobre `--lat-accel-limit` que se ajusta al cerrar cada vuelta (el cambio se nota en la vuelta siguiente; la vuelta 1 no cuenta): limpia con margen (|CTE| ≤ 1,2 m, deriva ≤ 3°, 0 ruedas fuera) sube un 4 %; fuera de V19 baja un 8 % y se congela 2 vueltas; topes 0,7 a `--lat-adapt-max-scale` (1,15) y `--lat-adapt-cap` (10 m/s²). El log guarda un evento `lat_adapt` por vuelta. Recalcular el perfil cuesta ≈ 0,06 s.
- **Primera sesión con `--lat-adapt`** (`223106Z`, mojado, límite base 6, máx. 1,4, 6 vueltas): las vueltas 2-4 salieron sucias (|CTE| 2,65-2,86 m, deriva hasta 9,2°) y las 5-6 mucho mejor (1,49 y 1,37 m; 2,4° de deriva; 143,9 y 143,4 s; 104 y 38 ticks fuera). C4, C6 y C8 bajaron a ×0,85 y C1-C3 y C10-C14 subieron hasta ×1,22. **No es una prueba limpia:** la vuelta 4 ya tenía C6 al mismo ×0,85 que la 5 y seguía mal, y las gomas se estabilizaron en ≈ 20 °C. Falta el **control**: las mismas 6 vueltas sin `--lat-adapt`. En la recta C6→C7 el bamboleo nace de salir de C6 con 1,6 m de error, no del gas (razón traseras/delanteras 1,00-1,09); en la vuelta 6 la banda de 100 km/h ya manda (gas 0,56, `maintain_speed`).
- **Control sin `--lat-adapt`** (`225613Z`, mismo comando, mismas condiciones: `rain` 153, pista 13 °C, gomas 19-22 °C en las vueltas 5-6): se queda sucio hasta el final. Vueltas 5-6 con ajuste frente al control: |CTE| máx. 1,49 / 1,37 frente a 2,64 / 2,73 m; deriva 4,2 / 2,4° frente a 7,0 / 6,0°; ticks con rueda fuera 104 / 38 frente a 265 / 301; tiempo 143,9 / 143,4 frente a 145,0 / 145,6 s. En las vueltas 2-4 el ajuste no gana (está aprendiendo). **El ajuste funciona, con una réplica por lado:** conviene repetirlo una vez más antes de darlo por cerrado.
- **Herramienta nueva `experimental/common/estadisticas_vueltas.py <log>...`:** mínimo / media / máximo por vuelta de velocidad, |CTE|, deriva, lateral y longitudinal, gas, freno, |volante|, gomas, frenos y presión, más tiempo, ticks con rueda fuera y la lluvia y temperaturas al empezar cada vuelta. Con ella se ve que **las condiciones empeoran en las 4 primeras vueltas y luego se estabilizan**: gomas (media) 57 → 27 → 22 → 21 → 20 → 19 °C, frenos 274 → 139 °C, presión 1,51 → 1,39 bar. El control llegó a volante 1,00 (tope) en la vuelta 4; con el ajuste, 0,85 en la 3 y 0,27-0,32 en las 5-6.
- **Apuntado: lo mismo para freno, gas y volante** (mismo esquema que `--lat-adapt`: medir cada zona al cerrar la vuelta y ajustar en la siguiente, con topes y opt-in): (a) **freno:** la deceleración `--brake-decel-straight` por zona de frenada, a partir de la actividad del limitador de deslizamiento y de la razón traseras/delanteras; (b) **gas:** control de tracción (reducir el gas con la razón traseras/delanteras o la deriva), aunque en la recta C6→C7 mojada la razón fue de 1,00-1,09 y no habría ayudado ahí, y el tope de salida por zona; (c) **volante:** ganancia dependiente del agarre estimado (hoy solo hay contravolante por deriva y ganancia por velocidad); no antes de ver si el ajuste lateral deja limpias las rectas. Idea del usuario: en seco y con buena temperatura, el ajuste vuelta a vuelta apuraría cada curva y el calor de conducir mantendría las gomas dentro de su ventana; falta medir esa ventana (tabla temperatura de gomas → lateral máximo limpio, de los logs de seco y mojado).
- **Siguiente con `--lat-adapt`:** (1) repetir la pareja ajuste / control una vez; (2) guardar los multiplicadores entre sesiones (aporta poco hasta que el ajuste esté validado); (3) 8-10 vueltas para ver si convergen; (4) la banda 110 en mojado, en otra sesión; (5) en seco, con la receta vigente, después de la banda 135.
- **Próxima en seco:** la prueba de banda 135 sigue como está.

## Estado por tema

| Tema | Estado | Qué falta |
| --- | --- | --- |
| A2.0 a 125 km/h con la línea suavizada | Superada por la línea óptima (V85). Mejor resultado con ella: `221745Z` (V83), 119,5 / 119,4 / 119,5 s, pareja 3-4 cumple V19 (la 1-2 y la 2-3 fallan por C11 en la vuelta 2, 1,85 m). Sin el umbral de prominencia (V80-V81) 119,5-119,7 s sin pareja por la deriva de C4. Historia: V76 (`220205Z`, sin recorte) 119,8 s con la pareja 2-3; límite 9 (V73) 120,8 s; límite 10 (V74-V75) 118,8 s sin pareja; sin la técnica 120,5 s (`124357Z`) | Solo como referencia |
| A2.0 con la línea óptima | **Receta vigente confirmada con 6 vueltas (V85-V86, `225202Z` y `230452Z`, con `--lat-gain-v0-kmh 70`): 118,6-118,7 s estables, parejas 3-4, 4-5 y 5-6 (y las tres de la sesión de 4 vueltas) cumplen V19, 17-30 ticks con rueda fuera y ninguno en la hierba en 6 vueltas.** Con 60 (V84, `223851Z`): 118,5-118,6 s, sin pareja solo por C11 (1,67-1,97 m). Con la receta antigua (V58-V64) la S de C2-C3 fallaba (2,4-2,5 m); con la nueva queda en 1,1-1,3 m. | Prueba de banda 135 (próxima sesión, V86), D1b (el ancho real mejoraría la línea) |
| Techo en 3.ª (G2) | **Limpio hasta 140 km/h** (volante ±0,01, CTE ≤ 0,16 m por encima de 128 km/h). El motor llega a 149,9 km/h (112 N·m a 6756 rpm) | Repetir 150 km/h con la ganancia por velocidad |
| Frenadas fuertes | Con pedal ≤ 0,84 (teacher de A2) no hay bloqueo; con pedal 1,0 (A1) se bloquean las delanteras. **Limitador por deslizamiento cerrado** con objetivo 0,25 y memoria 0,85 (V44-V55): 11,4-11,8 m/s² desde 150 km/h y 11,0-11,4 desde 140, 0 ruedas paradas, CTE ≤ 0,56 m | Decidir qué tabla de frenada usa el solver (V55, punto 4); revisar los cambios de marcha durante la frenada; luego 140 km/h y el techo a 150 km/h |
| Técnica de pedales y frenada (`--pedal-technique`, `--brake-profile`, `--exit-circle`, `--profile-peak-min-m`; V65-V86) | **Terminada y en la receta vigente**, salvo el recorte de picos (V79-V80), **en la receta vigente con el umbral de prominencia (V83-V85)**: quita la frenada de C5-C6 y deja intacto el pico de 735-746 m junto a C4. Frenada: deceleración mediana 6,6-7,1 m/s², 27-28 % del tiempo ≥ 10 m/s², pedal 0,93, tiempo muerto 0,02 s, 46 % del freno girando, consigna sin saltos. Gas de salida con tope por el círculo (C11 de 2,2 a 1,4-1,7 m). Queda el gas, freno y gas en C5-C6, C9, C10 y C12-C14 (32-33 inversiones del gas por vuelta) | Gas de mantenimiento en C5-C6 y filas F10-F13 de `TECNICA_CONDUCCION.md` |
| Curvas numeradas (V70) | `circuito_virtual/pistas/sugo_gp/curvas.json` (C1-C14, tabla en `TECNICA_CONDUCCION.md` §9); el informe HTML, `resumen_sesion.py` y `pedales_sesion.py` las usan. C12-C14 son un solo viraje largo a la derecha (2656-3113 m), no una chicane (V78) | Regenerar con `python circuito_virtual/src/curvas.py` si cambia el mapa |
| Registro de sesión | `log_schema` 3 desde V67: `lat_accel` lateral real y `long_accel`; los logs anteriores tienen `lat_accel` = longitudinal | Leer cualquier log con `session_log.tick_accels` |
| Modelo del volante | `experimental/common/modelo_volante.py` acierta a más de 108 km/h y no ve las entradas en curva cerrada | Reajustarlo con cada log nuevo |
| Bordes de la pista | Pasillo comprobado por las ruedas (mediana 5,4 m); el usuario declara 10-12,5 m reales (V78, sin verificar; otra fuente da 10 m). Ni el UDP ni la shared memory traen el ancho. Terreno 48 = pintura sobre hormigón (probablemente legal) y fuera de la lista de carrera | D1b en pausa (V78); comprobar qué ids hay al cruzar la línea blanca y decidir el 48 |
| Grabador manual de D1b (V77) | `circuito_virtual/src/sesion_manual.py`: escucha el UDP, no envía mandos y graba una conducción del usuario en `PCARS2-AI/logs/manual/`; 7 tests, sin ejecutar contra el juego | Sesiones del usuario (en pausa) y un extractor de bordes con ventana |

## Comandos vigentes

Los lanza el usuario (en seco, delante del juego, Ctrl+C si el coche oscila o se sale). Siempre con
la ruta absoluta del Python del proyecto.

**A2.0, RECETA VIGENTE (confirmada con 6 vueltas, V85-V86): línea óptima `a1mu9c12` a 125 km/h con todo lo de la técnica, `--lat-accel-limit 9.5`, `--lat-gain-v0-kmh 70`, `--profile-peak-min-m 60` y `--profile-peak-min-kmh 8`; las parejas de vueltas cumplen V19, ≈ 118,6 s.** Cada opción está explicada en la tabla de «Receta del teacher». Las sesiones se hacen cambiando **una** opción de este comando y un nombre de experimento nuevo (acabado en `_l4`, `_l4b`…; la sesión de referencia usó `…_v70_…_l4b`). El 8 y el recorte dependen de la línea y del límite 9,5:

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --teacher-only --speed-band 125 --max-gear 3 --lat-accel-limit 9.5 --steer-ff-gain 0.003 --steer-ff-v0-kmh 0 --steer-ff-cap-kmh 100 --steer-preview-s 0.3 --steer-slip-gain 5 --lat-gain-v0-kmh 70 --throttle-max 1.0 --brake-decel-straight 10 --brake-overspeed-straight-ms 2.5 --brake-slip-limit 0.25 --brake-slip-hold 0.85 --pedal-technique --brake-profile --brake-circle 10 --exit-circle 14.6 --profile-peak-min-m 60 --profile-peak-min-kmh 8 --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_optima_a1mu9c12.json --experiment a2_optA1mu9c12_125_g3_lat95_slip5_v70_ff0_cap100_pv03_gas1_fr10_perfil_c10_slip_exit146_pico60_prom8_l4c --laps 4
```

**Línea suavizada, receta de V83 (superada en V85, sirve de comparación):** la misma con `--lat-gain-v0-kmh 60` y `--reference …\sugo_smooth.json`; comando completo en el historial de git de este archivo (commit `f1c276a`).

Las recetas históricas de A2.0 (base sin técnica `124357Z`, técnica de pedales `140704Z`, línea óptima `a1mu9b` con tope 100) están descritas en `DECISIONES.md` (V31-V32, V58, V65); sus comandos completos siguen en el historial de git de este archivo, antes de V79.

**A1, aceleración hasta el techo.** Por encima de 135 km/h hace falta `--lat-gain-v0-kmh 70`; sin
él el volante oscila (V42). Con el pedal 1,0 de la frenada final se bloquean las delanteras, por eso el
techo se queda en 140 km/h salvo con el limitador de frenada (V44):

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --ident acel --speed-band 60 --ident-cap-kmh 140 --max-gear 3 --lat-gain-v0-kmh 70 --ident-straights 1 --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_smooth.json --experiment a1_acel_g3_lg70_140_60 --laps 3
```

**Frenada con el limitador: serie cerrada (V43-V55).** Ajuste: `--brake-slip-limit 0.25 --brake-slip-hold 0.85`.
Con él, desde 150 km/h con banda 100 y la receta de A2.0 (`--lat-accel-limit 9 --steer-ff-gain 0.003
--steer-ff-v0-kmh 0 --steer-preview-s 0.3 --steer-slip-gain 5 --lat-gain-v0-kmh 70 --throttle-max 1.0
--brake-decel-straight 8 --brake-overspeed-straight-ms 2.5`): vueltas de ≈ 135 s que cumplen V19, frenada de
3437 a 3511 m, 0 ruedas paradas, CTE ≤ 0,40 m, 11,4-11,8 m/s² (V55). Solo cambia `--ident-caps` (140 o 150, la
aceleración arranca fija en 3132 m y la frenada cae en la recta del 3363 m con 140 y del 3437 m con 150; con
130 km/h la banda tiene que ser 60 para caer en la recta). El comando completo, con rutas absolutas:

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --ident frenar --ident-caps 150 --speed-band 100 --max-gear 3 --lat-accel-limit 9 --steer-ff-gain 0.003 --steer-ff-v0-kmh 0 --steer-preview-s 0.3 --steer-slip-gain 5 --lat-gain-v0-kmh 70 --throttle-max 1.0 --brake-decel-straight 8 --brake-overspeed-straight-ms 2.5 --brake-slip-limit 0.25 --brake-slip-hold 0.85 --ident-straights 1 --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_smooth.json --experiment a1_frenar_g3_slip025_hold085_150_100_a2 --laps 3
```

Tabla por tramos de velocidad de V55 (sin cuesta, m/s²; los de más de 120 km/h incluyen el arranque del pedal y
los de 100-80 y 40-30 km/h cambios de marcha): 150-130 11,03; 130-120 11,13; 120-100 11,56; 100-80 10,28;
80-60 11,49; 60-40 11,99; 40-30 9,82.

**Regenerar las líneas locales** (por orden; la segunda tarda ≈ 70 s y la tercera ≈ 50 s):

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\circuito_virtual\src\linea_suave.py
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\circuito_virtual\src\linea_optima.py --coche-a1-mu 9 --max-barridos 80
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\circuito_virtual\src\linea_optima.py --coche-a1-mu 9 --max-barridos 80 --pasillo-estricto --salto-max-rel 1.0 --margen 0.6 --nombre sugo_optima_a1mu9b
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\circuito_virtual\src\linea_optima.py --coche-a1-mu 9 --tope-kmh 125 --max-barridos 80 --pasillo-estricto --salto-max-rel 1.0 --margen 0.6 --curvatura-local-rel 1.2 --nombre sugo_optima_a1mu9c12
```

`a1mu9` y `a1mu9b` se hicieron con tope 125 km/h y la tabla de aceleración anterior a V56: regenerarlas hoy da líneas algo
distintas (las ya hechas no cambian). `a1mu9c12` es la línea con la cota local de curvatura (V62).

**Analizar una sesión** (el usuario pasa el informe HTML; el log está en `PCARS2-AI\logs\learning\`).
Con salida por tubería, anteponer `PYTHONIOENCODING=utf-8`; el procedimiento paso a paso para la próxima sesión está arriba:

- A2.0: `experimental\common\resumen_sesion.py <log> --previsto <s>` (criterio de volante, tramos fuera
  de criterio, frenos, cambios de marcha, ruedas fuera). Sin previsión del solver, no inventar una: comparar con la sesión de referencia.
- **Curvas numeradas (V70):** el informe HTML, `resumen_sesion.py` y `pedales_sesion.py` usan `circuito_virtual/pistas/<pista>/curvas.json` (C1-C14 en Sugo, tabla en `TECNICA_CONDUCCION.md` §9). Para que el usuario diga «la curva N», darle el número de ese catálogo; regenerar el informe de un log antiguo: `python experimental/common/informe_c0.py <log>`.
- Pedales y frenada (V65-V67): `experimental\common\pedales_sesion.py <log> --vueltas 2,3,4 [--eventos] [--consigna <linea.json>]` (inversiones y rebotes del gas, tiempo muerto antes de
  frenar, deceleración, % de la frenada con > 4 m/s² laterales, uso del círculo; con `--consigna`, el mayor salto de la consigna del teacher sin juego). Cifras de partida en `TECNICA_CONDUCCION.md` §7.1.
- **Aceleraciones de un log**: usar `session_log.tick_accels(tick["vehicle"])` (lateral, longitudinal positiva al acelerar) o `local_accel[0]` / `local_accel[2]`; **nunca `vehicle.lat_accel`
  en logs anteriores a V67** (era la longitudinal).
- A1: `experimental\common\analisis_a1.py <log>`.
- Modelo del volante: `experimental\common\modelo_volante.py --ajuste "LOG|REF" --prueba "LOG|REF"`.

### Receta del teacher (opciones de `aislado.py`)

| Opción | Valor | Qué hace | Decisión |
| --- | --- | --- | --- |
| `--teacher-only --max-gear 3` | 3 (2 hasta 115 km/h) | El teacher conduce y el cambio sube hasta 3.ª (techo permitido 150 km/h) | X24, V28-V30 |
| `--lat-accel-limit` | **9,5 en la receta vigente** (9 en V73; 10 gana 1,9 s pero no cumple V19, V74-V75) | Límite lateral que el teacher supone en curva (máx. 14,6 por D21); el coche pide ≈ 1,45 veces ese valor | V27, V74-V76 |
| `--steer-ff-gain` + `--steer-ff-v0-kmh` | 0.003 y 0 | Anticipación de volante 1 + 0,003 · v². A más de 100 km/h se pasa de lo que pide el coche; bajar a 0.002 arregla las curvas rápidas y estropea las lentas | V21, V38-V41 |
| `--steer-ff-cap-kmh` | 0 (sin tope); **100 en la receta vigente** (V72: C14 de 2,0 a 0,95 m y C13 de 1,65 a 1,2 m) | Con `--steer-ff-gain`: por encima de esta velocidad el factor 1 + G · v² deja de crecer; sin cambio por debajo | V41, V57 |
| `--steer-preview-s` | 0.3 | La curvatura del volante se lee a v · 0,3 s y no a 30 m fijos | V22 |
| `--steer-slip-gain` | 5 | Contravolante por deriva (zona muerta 3°, la ganancia de CTE baja a 0 a 8°) | V17 |
| `--lat-gain-v0-kmh` | 60 con la línea suavizada; 70 con la óptima y en A1 | Ganancia de CTE × (v0/v)² por encima de v0: estabilidad del lazo a alta velocidad; sin ella oscila a más de 135 km/h. No subir a 80 | V18, V35, V42 |
| `--throttle-max` | 1.0 | Gas a fondo (producción 0,85: acelera un 15-20 % menos) | V24, V25 |
| `--brake-decel-straight` + `--brake-overspeed-straight-ms` | 8 y 2.5 (**10 y 2.5 con el limitador en la receta vigente**) | En recta (\|κ\| < 0,004 y \|CTE\| < 1 m) frena a ≈ 8-11 m/s²; con `--brake-profile` es la `a_b` del perfil | V31, V32, V71 |
| `--reference` | `sugo_smooth.json` o `sugo_optima_a1mu9c12.json` | Línea que sigue el teacher | V14, V32, V36 |
| `--brake-slip-limit` | 0 (apagado); 0.25 en la receta vigente | Si 1 − rps delanteras / rps traseras pasa de este valor, el pedal baja y vuelve a subir al recuperar agarre; actúa sobre el pedal de cualquier origen, también `--ident frenar` | V43, V44 |
| `--brake-slip-hold` | 0 (sin memoria); 0.85 | Con `--brake-slip-limit`: tras pasar del objetivo el pedal sube deprisa solo hasta esta fracción del pedal que lo provocó y despacio desde ahí, en lugar de volver a 1,0 y oscilar | V49, V50 |
| `--pedal-technique` | apagado; en la receta vigente | Técnica de pedales (solo con el modelo físico): gas cortado del todo y enclavado antes de frenar, freno que se suelta en proporción al exceso hasta el vértice y gas que solo sube desde el vértice | V65 |
| `--pedal-exit-slew` | 1.5 | Con `--pedal-technique`: subida máxima del gas por segundo desde el vértice (1,5 = de 0 a fondo en ≈ 0,7 s; con 0,8 el coche de juguete perdía 1,2 s) | V65 |
| `--brake-profile` | apagado; en la receta vigente | Con `--pedal-technique` (V68): consigna de velocidad continua por barrido hacia atrás con el círculo de adherencia (sin el salto 8 → 4 m/s² al entrar en la curva) y freno por avance sin margen ni tiempo muerto | V68-V71 |
| `--profile-peak-min-kmh` | 0 (sin umbral); **8 en la receta vigente (V83)** | Con `--profile-peak-min-m`: un pico solo se aplana si el recorte lo baja al menos estos km/h (sobre el perfil lateral, antes del barrido hacia atrás). 8 deja intactos el pico de 1,4 km/h junto a C4 y el de su salida y mantiene los de C5-C6; depende de la línea y del límite lateral (medido con `sugo_smooth.json` y 9,5) | V82 |
| `--brake-circle` | 14.6; **10 en la receta vigente** | Con `--brake-profile`: radio del círculo en unidades de la línea. 14,6 = trail braking completo; ≈ 10 = casi terminar de frenar antes de girar (el coche hace ≈ 1,45 veces el lateral que cree la línea) | V69-V70 |
| `--exit-circle` | 0 (apagado); **14.6 en la receta vigente** | Con `--pedal-technique` (V72, F3): en la salida el gas no pasa de `gas_max · √(1 − (lateral medido / R)²)` (0,60 a 11,7 m/s²); cuesta ≈ 0,23 s por vuelta y baja el \|CTE\| en casi todas las curvas | V72-V73 |
| `--profile-peak-min-m` | 0 (apagado); **60 con `--profile-peak-min-kmh 8` en la receta vigente (V83-V85)** | Con `--brake-profile`: aplana al valle más alto de alrededor los picos de la consigna más estrechos que estos metros; el coche no acelera en un tramo corto entre dos curvas para frenar enseguida (C5-C6, C9). Con el coche de juguete: 30 m −0,03 s, 60 m +0,08 s, 100 m +0,5-0,8 s, 150 m +3-3,8 s; en el juego (V80-V81) quita la frenada de C5-C6 y baja ≈ 0,15 s, pero cambia 32 tramos del perfil, entre ellos un pico de 1,4 km/h junto a C4 que sube su deriva | V79-V81 |

`aislado.py` pasa siempre `--hold-stage` a `learn_driver.py` con `--teacher-only` (V64): sin él dos vueltas limpias cerraban la sesión aunque `--laps` fuese mayor.

Reglas de `aislado.py` para estas opciones: sin `--ident` exigen `--teacher-only` y un
`--experiment` con prefijo `a2_` (el nombre por defecto borraría el buffer `teacher_<banda>`); con
`--max-gear 2` la banda máxima es 115 km/h. Con `--ident` se aceptan y se pasan igual. `--profile-peak-min-m` exige `--brake-profile`.

### Escalera de bandas con la línea suavizada (vuelta lanzada)

| Banda | Límite lat. | Cambios | Vuelta medida / prevista | \|CTE\| máx. | Deriva máx. | Decisión |
| --- | --- | --- | --- | --- | --- | --- |
| 80 | 7,5 | 2.ª | 162,8 / 163,9 s | 0,71 m | 1,0° | V23 |
| 90 (gas 1,0) | 7,5 | 2.ª | 148,9 / 149,6 s | 0,85 m | 1,3° | V25 |
| 100 | 9 | 2.ª | 135,4 / 135,7 s | 1,42 m | 2,9° | V27 |
| 110 | 9 | 2.ª | 128,0 / 127,9 s | 1,42 m | 3,4° | V28 |
| 120 | 9 | 2.ª-3.ª | 123,4 / 122,6 s | 1,77 m | 1,6° | V30 |
| 125 | 9 | 2.ª-3.ª | 121,8 / 120,6 s | 1,59 m | 3,5° | V31 |
| 125 + frenada fuerte | 9 | 2.ª-3.ª | 120,4 / 120,6 s | 1,56 m | 2,5° | V32 |
| 125 + técnica de pedales completa | 9,5 | 2.ª-3.ª | 119,8 s | 1,77 m | 3,9° | V76 |

Con la línea óptima los resultados están en `DECISIONES.md` (V33-V41, V58-V64).

Criterio de volante para subir de banda (V19, provisional): 2 vueltas completas seguidas, sin
salirse, con rectas de volante rms ≤ 0,04, ≤ 1 inversión/100 m y |CTE| rms ≤ 0,25 m, y curvas con
tasa ≤ 0,2/s, |CTE| máx. ≤ 1,8 m y deriva máx. ≤ 4°; además, 0 ticks con ruedas fuera de la
superficie de carrera (hoy el terreno 48, pintura sobre hormigón, cuenta como fuera: ver V78). Referencia: la IA a ritmo real hace 97,9 s.

### Qué está probado y qué no

- **Probado:** teacher en 2.ª hasta 110 km/h y con 3.ª hasta 125 km/h, parejas de vueltas limpias por banda (el solver
  tiene las tablas de aceleración hasta 140 km/h desde V56, pero no hay vuelta completa a más de 125);
  aceleración en 3.ª hasta 140 km/h con el volante tranquilo (y el motor hasta 149,9 km/h); frenada
  fuerte en recta hasta 123 km/h con pedal ≤ 0,84 y sin bloqueo (11,6 m/s²); el solver acierta el
  tiempo de vuelta con el coche de A1 en cada banda (−0,2 % a +1,0 %); la técnica de pedales completa con el límite 9 y 9,5 (V73, V76).
- **Con aviso:** las frenadas a fondo de A1 desde 100, 110, 135, 140 y 150 km/h (pedal 1,0, 11,5-11,9
  m/s²) bloquean las delanteras a los ≈ 0,3 s y hasta casi parar; el «sin bloqueo» anterior solo
  miraba las traseras (V42-V43).
- **Sin validar:** el recorte con umbral de prominencia sobre la línea óptima (V83, solo comprobado sin juego) o con otro límite lateral; el grabador manual contra el juego (V77); frenadas sin bloqueo desde más de 123 km/h; aceleración por encima de 140 km/h con
  el volante tranquilo; 4.ª marcha; límite lateral por encima de 14,6 m/s² sostenidos (A1.3b);
  cualquier otra pista o coche; los bordes reales (D1b: semivía de 0,85 m y margen supuestos).

## Reglas de la sesión (no olvidar)

- **El usuario lanza el juego, yo nunca.** No ejecutar `aislado.py` ni `learn_driver.py` con
  argumentos válidos, ni para «probar» la CLI: lanza una sesión real y borra el buffer del
  experimento (incidente c0_log, memoria `feedback-no-ejecutar-aislado-para-probar`). Para
  comprobar una línea de comandos: `build_argv` y `a2_error` de `aislado.py` desde Python. Lo mismo con `sesion_manual.py` (abre el puerto UDP y escribe un log): solo `--help` y tests.
- **Seco y mojado van separados** (sección «Seco y mojado»): las sesiones con lluvia llevan `a2_mojado_` en el experimento y no se comparan con la base ni con V19.
- **Una sola variable por sesión** y primero el volante, después la velocidad (V19).
- **Las sesiones anteriores son referencia, no vara de medir** (memoria
  `feedback-versiones-anteriores-solo-referencia`): cada sesión se juzga contra el criterio y su
  propio log; los modelos se reajustan con cada log nuevo.
- Antes de cada sesión arriesgada (techo alto, frenadas desde más de 115 km/h, arcos, mapeo de
  bordes) confirmar que el usuario está delante del juego y en seco, y que corta con Ctrl+C si el
  coche oscila.
- **Bloqueo de ruedas:** medirlo en las delanteras y en las traseras (rps de cada eje frente al otro),
  no solo con la razón traseras/delanteras mínima.
- Dependencias en un solo sentido: `PCARS2-AI` ← `circuito_virtual` ← `experimental`.
  `circuito_virtual` no importa de `experimental`.
- Documentos de `circuito_virtual/` y `experimental/` en **LF**; en `PCARS2-AI/` los `.py` son
  CRLF salvo los tests nuevos (usar una utilidad que respete cada archivo). Para escribir archivos
  largos usar Write y no scripts de Python con `\n` dentro de cadenas en la línea de comandos.
- El usuario reformatea los docs con markdownlint: no comprobar texto con búsquedas literales
  frágiles (usar regex tolerante a espacios).
- **Ejes del log (V67):** `lat_accel` es la lateral solo desde `log_schema` 3; en los logs anteriores es la longitudinal. Un análisis suelto con el eje equivocado ya produjo cifras falsas en V64-V66.
- **Cambios del teacher que tocan los pedales:** los tests deben medir también la velocidad con la que se llega a cada curva (regresión de V65 7: la consigna «congelada» de la salida tapó la curva siguiente
  y el coche se pasó), no solo inversiones, rebotes y tiempo; el coche de juguete debe acelerar tanto o más que el real (probar ×1,0, ×1,3 y ×1,6).
- **Primera sesión tras un cambio de pedales:** el usuario atento y con Ctrl+C a mano; la primera vuelta es la que revela si el coche llega a una curva sin levantar.
- **Ruedas fuera:** separar siempre el terreno 48 (pintura sobre hormigón, probablemente legal) de la hierba (7) antes de dar una cifra (V78).
- **Datos de fuera del proyecto** (ancho de pista, mapas de la web): comprobación de cordura, no entrada; la página consultada es de otra variante (con chicane), no la `SUGO_GP` del juego.
- Camino sólido a largo plazo, sin prisa. Si hay que elegir, recomendar y no listar todo.

## Siguiente (en este orden)

La historia de cada sesión de hoy está en `DECISIONES.md` V69-V86; aquí solo lo que toca.

0. **Al empezar:** `git status` (debería estar limpio; puede quedar suelto el `Sportsland Sugo International track map.svg` de la raíz, que no es del proyecto); leer «Próxima sesión» (arriba) y `docs/TECNICA_CONDUCCION.md` §8-§9. Cuando el usuario diga «la curva N», es el catálogo C1-C14.
1. **Prueba de banda 135 km/h con la línea óptima** (V86, `--speed-band 135`): comando, previsión del solver y criterio de éxito en «Próxima sesión».
2. **D1b por conducción manual — EN PAUSA a petición del usuario (V78: «deja las pruebas pendientes»).** El ancho real declarado (10-12,5 m) duplica los 5,4 m comprobados, así que la línea óptima está limitada por lo recorrido y no por la pista. El usuario conduce (teclado) con las dos ruedas de un lado sobre la hierba y el limitador a 60 km/h, una sesión por lado y 3 vueltas; nada del teacher en marcha a la vez (comparten el puerto UDP). Después: `bordes_logs.py actualizar`, mirar la cobertura y, si hay metros con una sola cota, hacer el extractor con ventana (V77, punto 2); calibrar la semivía con los dos lados; mirar qué ids de terreno hay al cruzar la línea blanca (46, 47, 49) y decidir el 48. Éxito (`PLAN.md`): los dos bordes medidos en ≥ 90 % de la vuelta con incertidumbre ≤ 0,3 m. Diseño original con el teacher (6-10 rondas por lado) en `PLAN.md`, solo si esto no alcanza.

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\circuito_virtual\src\sesion_manual.py --lado izq --laps 3
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\circuito_virtual\src\sesion_manual.py --lado dcha --laps 3
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\circuito_virtual\src\bordes_logs.py actualizar
```

3. **Prueba de banda** (el punto 1 es su primer paso, 135 km/h; esto es la escalera completa; a petición del usuario, solo exploratoria, no es una sesión de receta ni se juzga con V19): subir `--speed-band` para ver hasta dónde llega. El techo con 3.ª es 150 km/h (`ident_max_cap_kmh(3)`); el solver tiene tablas de aceleración hasta 140 y el techo de 3.ª está limpio hasta 140; por encima de 135 hace falta `--lat-gain-v0-kmh 70` (V42). Propuesta: 135 con la receta tal cual y luego 140 con `--lat-gain-v0-kmh 70`; el salto a 150 solo con el usuario atento (la recta tras C8 toca hierba ya a 124 km/h y la frenada a C9 pasa de 126 a 68 km/h). Antes de cada sesión, calcular lo que prevé el solver para esa banda. La recta final (3113-3567 m) y la de 2555-2655 m van hoy a 126 km/h con el gas a medias: ahí está el tiempo.
4. ~~C11~~ **Resuelto con la línea óptima y `--lat-gain-v0-kmh 70` (V85):** 1,57-1,63 m.

5. **Pendientes menores del circuito** (observaciones del usuario curva a curva, V76): C3 se podía trazar mejor (\|CTE\| 1,24 → 1,33 m, sube por vuelta); C4 toca el piano (terreno 48) y el \|CTE\| máx. sube por vuelta (0,4 → 0,95 m); deriva de C5 ≈ 3,9-4,15° en todas las sesiones; hierba en 1444-1465 m tras C8 (el \|CTE\| pasa de +0,87 a −0,86 m en 70 m, la regla `edge_grass` recorta el gas, la velocidad no baja); ajuste de pedales en C9-C11.
6. **Más técnica** (`TECNICA_CONDUCCION.md` §5): F10 gas con espera en la salida de curvas cerradas, F11 clasificar las curvas (C12-C14 son un solo viraje largo), F12 eses, F13 horizonte de mirada (el recorte de picos de V79 es un primer paso), F5 puntos de frenada adaptativos, F6 cambios de marcha respecto a la frenada, F7 neumáticos (se enfrían de 80 a 46 °C en 4 vueltas).
7. **Decidir la tabla de frenada del solver** (V55, punto 4; enlaza con F4, perfil del solver como archivo): la de `parametros_a1.json` (45-105 km/h, 11,87-13,05 m/s²) y las medias por ventanas de V55 (10,3-12,0 m/s²) no coinciden. Las tablas de A1 ya descuentan la pendiente. Datos de partida (radio efectivo 0,274 m): sin bloqueo el deslizamiento delantero va al 10-15 % con pedal 0,6-0,95; con bloqueo (80-110 %) la deceleración baja a 11,9 m/s² frente a 12,5-12,7 con el 20-50 %.

   **Estado de `coches/formula_rookie/parametros_a1.json` (revisado 2026-11-03, V86):** la aceleración (15-135 km/h) es de V56 y regenerarla con `analisis_a2.py` desde sus 6 logs da el mismo archivo; la frenada (45-105 km/h, 11,87-13,05 m/s²) es la de A1 con pedal 1,0 y no tiene datos por encima de 105 km/h (usa 13,05 hasta el tope). `mu` 14,6 no pesa: `coche_a1()` lo sustituye por el que se pide. Solo lo leen el solver y la generación de líneas (`coche_a1()`, `linea_optima.py`, los informes de líneas); el teacher y el juego no. **Efecto medido con la línea `a1mu9c12`** (solo cambia la tabla de frenada; segundos de vuelta prevista a 125 / 135 / 140 km/h): la actual 118,4 / 115,3 / 114,1; las medias de V55 con el limitador (150-130 11,03; 130-120 11,13; 120-100 11,56; 100-80 10,28; 80-60 11,49; 60-40 11,99) 118,6 / 115,5 / 114,3; plana a 10,0 m/s² (la `a_b` de la receta) 118,7 / 115,6 / 114,5. Es decir, +0,2 a +0,3 s (0,2 %), y con las medias de V55 la previsión a 125 km/h (118,6 s) coincide con lo medido en las sesiones de V85-V86 (118,6-118,7 s). **No urgente y no tocarlo antes de la sesión de 135:** esa sesión se juzga contra 115,3 s con la tabla actual, y cambiar la frenada del solver cambiaría la línea óptima si se regenera (una variable nueva sobre la receta confirmada). **Cuando se decida:** regenerar el archivo con las medias del limitador (`analisis_a2.py --guardar …/parametros_a1.json` tras ajustar `BRAKE_LOGS` o la tabla), regenerar `a1mu9c12` y comparar la línea nueva con la actual, y probarla en una sesión aparte (una variable: `--reference`).

## Después (en este orden)

1. **Medir el límite lateral del coche (A1.3b)**: el teacher ya pide 13-15 m/s² sostenidos con
   `--lat-accel-limit 9`, en la cota validada de D21 (≥ 14,6). Subir más exige arcos en 3.ª y 4.ª
   (D23). Riesgo de daño de motor (P26): tres de tres sesiones de arcos lo dieron hacia los 607 s;
   `aislado.py` ya pasa `--stop-on-damage`; sesiones cortas.
2. **A/B de la ayuda de bloqueo opuesto (D12, P20):** el log no muestra intervención
   (`game_steer` ≈ `raw_steer`, diferencia media 0,017) pero no se sabe si actúa sin reflejarse.
   Misma sesión con la ayuda desactivada (ajuste del juego, se aplica al empezar una sesión
   nueva; anotarlo en el nombre del experimento).
3. **Completar el reglaje del diferencial:** del trasero solo se ve «DDL por embragues: Sí» y rampa
   en deceleración de 30°; faltan precarga, embragues, potencia de rampa y todo el delantero
   (pedir captura). El freno de motor está en 8. No tocar el reglaje: A1 y A2 están medidos así.
4. **Datos de agarre sin leer:** `telemetry_udp.py` salta los bytes 224-295 del paquete de física
   (72 bytes entre `tyre_tread_temp` y `ride_height`). La cabecera de la shared memory (CREST2-AMS2) nombra
   `mTyreLayerTemp`, `mTyreCarcassTemp`, `mTyreRimTemp` y `mTyreInternalAirTemp` (sin comprobar que PC2 los
   rellene; V78). Comprobar guardando esos bytes en bruto en una sesión corta.
5. **Peralte de la pista:** el mapa tiene altura (−46 a +25 m) y pendiente, pero no inclinación lateral; se puede sacar de los logs (alabeo menos la parte de la aceleración lateral; a 30-60 km/h en recta el alabeo es casi el de la pista).
6. **Visión por pantalla para las líneas blancas** (idea del usuario, V78): sería el mejor objetivo de una visión (HUD oculto, cámara de capó, campo de visión fijo, captura sincronizada con la posición y la orientación del UDP); solo si los ids de terreno no ven la línea blanca y D1b no basta; D1b serviría de verdad de referencia.
7. **A3, segunda pista:** repetir A2 con otra pista y otra IA para saber si el factor de ritmo y
   las envolventes se generalizan. Requiere `circuito_virtual/pistas/<pista>/` con mapa y
   referencia suavizada.
8. **Rivales:** ver si el paquete de tiempos trae la posición de los rivales (hoy solo se lee al
   participante propio; el relay de memoria compartida del Telemetry Tool dice dar «posición y
   velocidad de otros coches»), antes de D5.
9. **PPO residual sobre el teacher:** la técnica de curva del manual (frenar fuerte y soltar con el giro, mínimo en el ápice, gas progresivo con tope por el círculo) ya está en el teacher (paso 4 de V17; V65-V79, `TECNICA_CONDUCCION.md`), así que el PPO va después como corrección acotada sobre ese teacher (V17); antes, revisar el estado de `ppo_guard`, `ppo_anchor` y `ppo_bootstrap`, y decidir si el BC aprende la receta vigente (los logs ya traen `long_accel`, el catálogo de curvas y las razones `lift_lock`/`accel_exit` normalizadas al vocabulario del BC).

## Ideas y referencias

- **Técnica de conducción** (V66): `docs/TECNICA_CONDUCCION.md` recoge lo que dicen PCA «The Art of Braking» y 8000vueltas (frenar y acelerar), lo que hace el teacher con datos y las fases F1-F13.
- **Manual de Racelogic** (*Advanced Circuit Driving Techniques*, aportado por el usuario): volante
  mínimo («enderezar cada curva» valió 0,9 de 1 s en Eau Rouge); la velocidad en curva no es
  constante (frenada modulada, mínimo en el ápice); gas solo cuando no haya que soltarlo; una línea
  que usa todo el ancho pide menos volante (apoya la línea óptima).
- **Ancho y geometría de la pista (V78):** ni el UDP ni la shared memory de PC2 traen el ancho ni los bordes (solo `mTrackLength`); yourdatadriven.com da 10 m, ≈ 75 m de desnivel (nuestro mapa 70,9 m) y 3704 m, pero es otra variante (con chicane; el juego mide 3567 m) y su mapa viene de OpenStreetMap. Shared memory = los mismos datos en `float`, con número de secuencia; seguir con UDP.
- **Terrenos (V78):** 46 `RunoffRoad`, 47 `IllegalStrip`, 48 `PaintConcrete`, 49 `PaintConcreteIllegal`; solo el 10 (franjas) está en la lista de carrera.
- **SecondMonitor** (Winzarten, GitLab): según foros soporta PC2 por shared memory (tiempos, deltas, mapa tras una vuelta, temperaturas, visor de telemetría); sin ancho ni bordes; aporta poco que no registremos ya.
- **Telemetry Tool for PC2 (Iko Rein) v15.09**, revisado en solo lectura: lee el mismo UDP; no trae
  canales de agarre para PC2 (carga por rueda y nivel de agarre son de F1 y rF2); sus indicadores
  útiles (deriva frente a guiñada, razón traseras/delanteras, índice de subviraje) se calculan con
  lo que ya registramos. El índice de subviraje sería un buen estado para el gas de salida.
- **Dato:** `air_pressure` del log son centésimas de bar y en caliente (155/142 con el garaje en
  1,51/1,39 bar); `CONFIGURACION_JUEGO.md` da el reglaje en frío (1,25/1,15).
- **Más puntos de control en la línea:** `--paso-nudos 15` da −5,3 % frente a −3,5 % con 20 m con
  las envolventes de la IA, pero una línea con más movimiento lateral; solo cuando la de 20 m esté
  rodada (hoy exige más seguimiento).

## Más adelante (tras D2, D3 y el mapa)

- **D3-D5:** planificador (dónde y a qué velocidad), política aprendida por selección y
  adelantar/defender, según el plan D de `docs/PLAN.md`.
- **PPO / C4:** después de mapa, modelo y BC v2, con noche protegida.
- **Reentreno v2 del BC y controles de seco:** en `experimental/docs/PENDIENTE.md`.
- **Informe del mapa:** añadir la línea óptima (D2) a `src/informe_mapa.py`.
- **Informes HTML (no versionados, `pistas/sugo_gp/informes/`)**: `informe_mapa.html`, `informe_linea_optima.html` e
  `informe_lineas_teacher.html` (V63). Se regeneran con los comandos de «Uso» del `README.md`; el último, tras cada
  sesión nueva de A2.0, añade la sesión a su tabla.

## Hecho (no repetir)

- ~~G1b~~ **Hecho (V14):** 134,9 km/h en 3.ª, 3 vueltas, sin cortes, sin daño.
- ~~A2 con la IA a ritmo real~~ **Hecho (V12, V13).**
- ~~D0~~ **Hecho (V7):** coordenadas (s, n), `src/mapa.py`, `pistas/sugo_gp/mapa.json`.
- ~~D1a~~ **Hecho (V9, V10, V33):** bordes de 124 logs (hoy se añadieron 18).
- ~~Línea suavizada~~ **Hecho (H61 en `experimental/docs/DECISIONES.md`).**
- ~~D2~~ **Hecho (V15, V32, V33):** línea óptima por ritmo de la IA y por coche del teacher.
- ~~A2.0, escalera 80 → 125 km/h~~ **Hecho (V16-V32).**
- ~~G3, frenadas desde la 3.ª hasta 115 km/h~~ **Hecho (V29).**
- ~~Frenada fuerte en recta~~ **Hecho (V31, V32).**
- ~~Techo en 3.ª~~ **Hecho hasta 140 km/h (V43):** volante tranquilo; el motor llega a 149,9 km/h (V42).
- ~~Modelo del volante~~ **Hecho (V39-V41):** `experimental/common/modelo_volante.py`.
- ~~Línea `a1mu9b`~~ **Hecha (V36):** quita las ruedas fuera de 759-771 y 1444-1454 m; no cumple todavía el criterio.
- ~~Corregir el campo `lat_accel` del log~~ **Hecho (V67):** `log_schema` 3, `long_accel` y `tick_accels`.
- ~~Leer las tres partes de 8000vueltas y el PDF de Porsche (PCA)~~ **Hecho (V66, V67):** `docs/TECNICA_CONDUCCION.md`.
- ~~Técnica de pedales implementada~~ **Hecho (V65-V73):** frenada con perfil, tope del gas por el círculo y volante con tope de anticipación; cumple V19 en una pareja de vueltas (V73, V76).
- ~~Actualizar la tabla de aceleración de A1 y el tope del solver~~ **Hecho (V56).** Queda, si se quiere, una sesión de aceleración con techo 150 km/h (`--ident acel --ident-cap-kmh 150 --lat-gain-v0-kmh 70`).
- ~~Subir el límite lateral del teacher a 10~~ **Probado (V74-V75):** gana 1,9 s pero no cumple V19; la receta vigente usa 9,5 (V76).
- ~~Grabador pasivo para D1b manual~~ **Hecho (V77):** `circuito_virtual/src/sesion_manual.py`.
- ~~Recorte de picos de la consigna~~ **Implementado (V79) y probado dos veces en el juego (V80-V81):** sin freno en C5-C6, 119,5-119,7 s, pero sin pareja V19 por la deriva de C4; el umbral de prominencia lo arregló (V82-V83) y es parte de la receta vigente.
- ~~La línea óptima con la receta vigente~~ **Hecho (V84-V85):** `a1mu9c12` con `--lat-gain-v0-kmh 70` da 118,6 s con las tres parejas de vueltas cumpliendo V19; confirmado con 6 vueltas (V86).
