# Pendiente de circuito_virtual

Estado al cierre de la sesión del **2026-11-02** (noche, tras F3, el criterio por parejas y `--lat-accel-limit 10`, V1-V74). Lo que no es del circuito (rampa del BC, PPO, daño
de motor P26, controles de seco, reentreno v2) está en `experimental/docs/PENDIENTE.md`. El plan está
en `docs/PLAN.md`, las decisiones en `docs/DECISIONES.md` y la historia en `docs/DIARIO.md`.

**Qué significan las «V»:** cada Vnn es una entrada del registro de decisiones (hoy V1-V74), no una
versión del software. La versión del software es el commit de git, que cada sesión guarda en la
cabecera de su log. Este documento recoge solo el estado actual y lo que sigue; las cifras de sesiones
anteriores son referencia (están en `DECISIONES.md`) y cada sesión nueva se juzga contra el criterio de
volante de más abajo, no contra la anterior.

## Dónde estamos

- **Estado del código:** comiteado en `8e8a666` lo hecho hasta V68. **Sin comitear (V69-V74), propuesta de dos commits:** (1) código: `circuito_virtual/src/curvas.py` y `tests/test_curvas.py`, `pistas/sugo_gp/curvas.json`, `PCARS2-AI/src/{learn_driver,teacher_controller}.py` (`--exit-circle`, V72) y `PCARS2-AI/tests/test_exit_circle.py`, `experimental/common/{aislado,informe_c0,pedales_sesion,resumen_sesion}.py` (curvas numeradas, criterio por parejas, V70-V73) y `experimental/tests/{test_aislado,test_resumen_sesion,test_curvas_informe}.py`; (2) documentos: `circuito_virtual/docs/{DECISIONES,DIARIO,PENDIENTE,TECNICA_CONDUCCION}.md`. Los logs de las sesiones de hoy llevan `626cf27` en la cabecera aunque ya traían cambios sin comitear.
- **Tests en verde:** `circuito_virtual` 71, `experimental` 111, `PCARS2-AI` 534 (ruff limpio salvo los avisos antiguos de `resumen_sesion.py` y `test_resumen_sesion.py`). Se lanzan con
  `pytest` dentro de cada carpeta.
- **Teacher** (`teacher_controller.py`, `learn_driver.py`): cada opción es opt-in y su valor por
  defecto es el de producción.
- **Archivos locales no versionados** (4,5 MB cada uno): `circuito_virtual/pistas/sugo_gp/` con
  `sugo_smooth.json`, `sugo_optima_a1mu9.json`, `sugo_optima_a1mu9b.json`, `sugo_optima_a1mu9c15.json` y
  `sugo_optima_a1mu9c12.json`. Cómo regenerarlos, en
  «Comandos vigentes».

## Estado por tema

| Tema | Estado | Qué falta |
| --- | --- | --- |
| A2.0 a 125 km/h con la línea suavizada | **Receta vigente (V73), `181618Z`: la pareja de vueltas 3-4 cumple V19**, 120,8 s (la 1-2 y la 2-3 solo fallan por la deriva de C5, 4,76°). Quedan 227 ticks por 4 vueltas con rueda fuera de la superficie de carrera (140 en la recta C8→C9, desde V63; 87 en C4). Sin la técnica: `124357Z`, 120,5 s. **Con `--lat-accel-limit 10` (V74, `213236Z`): 118,8-118,9 s (−1,9 s), lateral máx. 14,4 m/s², 237 ticks fuera (163 en C8→C9, 61 en C4); no cumple V19 por C11 (1,84 m) y la deriva de C5 (4,1°, vuelta 3), ninguna pareja pasa** | Repetir el límite 10 sin cambios para separar ruido de efecto (si falla otra vez, 9,5); después la línea óptima con esta receta |
| A2.0 con la línea óptima `a1mu9b` | Prevé −1,7 s pero no cumple (V58: |CTE| 2,38 m, deriva 5,6°, 0 ruedas fuera, +1,1 % de tiempo) | Con `--steer-ff-cap-kmh 100` (V58): 2690-2860 m arreglado, 0 ruedas fuera, 118,9 s; la S de 2400-2500 m (2,2-2,4 m) y una deriva de 5,6° en 920-930 m no cumplen. Tope 90 (V60) y banda 115 (V61): no mejoran; la óptima serpentea donde la suavizada no (V61). Cota local de curvatura hecha (V62), línea `a1mu9c12` generada y **probada a 125 km/h (V64): 119,5 s, 0 ruedas fuera, volante y deriva bien, 880-980 / 2380-2560 / 2680-2870 m en 0,60 / 1,71 / 0,75 m; no cumple solo por la S de 400-600 m en la vuelta 2 (2,38 m, rumbo 0,22 rad), que es casi igual que en la suavizada** (segundo modo de las líneas óptimas en vueltas ≥ 2; la vuelta 1 nunca). Repetida: 2,48 m; con 4 vueltas y `--hold-stage` (V64): vuelta 2 1,76 m (cumpliría), 3 y 4 2,46 y 2,56 m, y la 4 pisa fuera. **Los neumáticos fríos no son la causa por sí solos (la suavizada cumple V19 en 4 vueltas, V64 14). La receta 60 / sin tope mantiene la S en 1,4-1,7 m pero falla en las zonas rápidas (hasta 1,94 m, V64 17); la receta 70 / tope 100 al revés.** La técnica de pedales cumple V19 en 4 vueltas (V66). Siguiente: frenada de entrada (F1) |
| Techo en 3.ª (G2) | **Limpio hasta 140 km/h** (volante ±0,01, CTE ≤ 0,16 m por encima de 128 km/h). El motor llega a 149,9 km/h (112 N·m a 6756 rpm) | Repetir 150 km/h con la ganancia por velocidad |
| Frenadas fuertes | Con pedal ≤ 0,84 (teacher de A2) no hay bloqueo; con pedal 1,0 (A1) se bloquean las delanteras. **Limitador por deslizamiento (V44, V45, V47): cuatro sesiones reales, sin bloqueo; el mejor valor del limitador sin memoria es el objetivo 0,3 con 10,9-11,3 m/s² (criterio 11,5) y el pedal sigue en ciclo; **cerrado** con objetivo 0,25 y memoria 0,85 (V50-V55): 11,4-11,8 m/s² desde 150 km/h y 11,0-11,4 desde 140, 0 ruedas paradas, CTE ≤ 0,56 m | Decidir qué tabla de frenada usa el solver (V55, punto 4); revisar los cambios de marcha durante la frenada; luego 140 km/h y el techo a 150 km/h |
| Técnica de pedales y frenada (`--pedal-technique`, `--brake-profile`, `--exit-circle`; V65-V73) | **Terminada y en la receta vigente.** Frenada: deceleración mediana 7,1 m/s², 27 % del tiempo ≥ 10 m/s², pedal 0,93, tiempo muerto 0,02 s, 47 % del freno girando, consigna sin saltos. Gas de salida con tope por el círculo (C11 de 2,2 a 1,4-1,7 m). No cambia el tiempo de vuelta | Filas F10-F13 de `TECNICA_CONDUCCION.md` (gas con espera, tipos de curva, eses, horizonte) |
| Curvas numeradas (V70) | `circuito_virtual/pistas/sugo_gp/curvas.json` (C1-C14, tabla en `TECNICA_CONDUCCION.md` §9); el informe HTML, `resumen_sesion.py` y `pedales_sesion.py` las usan | Regenerar con `python circuito_virtual/src/curvas.py` si cambia el mapa |
| Registro de sesión | `log_schema` 3 desde V67: `lat_accel` lateral real y `long_accel`; los logs anteriores tienen `lat_accel` = longitudinal | Leer cualquier log con `session_log.tick_accels` |
| Modelo del volante | `experimental/common/modelo_volante.py` acierta a más de 108 km/h y no ve las entradas en curva cerrada | Reajustarlo con cada log nuevo |
| Bordes de la pista | Pasillo comprobado, bordes reales sin medir | D1b |

## Comandos vigentes

Los lanza el usuario (en seco, delante del juego, Ctrl+C si el coche oscila o se sale). Siempre con
la ruta absoluta del Python del proyecto.

**A2.0, RECETA VIGENTE (V73): línea suavizada a 125 km/h con todo lo de la técnica; la pareja de vueltas 3-4 cumple V19, ≈ 120,8 s.** Cada opción nueva está explicada en la tabla de «Receta del teacher». Las sesiones se hacen cambiando **una** opción de este comando y un nombre de experimento nuevo (acabado en `_l4`, `_l4b`…):

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --teacher-only --speed-band 125 --max-gear 3 --lat-accel-limit 9 --steer-ff-gain 0.003 --steer-ff-v0-kmh 0 --steer-ff-cap-kmh 100 --steer-preview-s 0.3 --steer-slip-gain 5 --lat-gain-v0-kmh 60 --throttle-max 1.0 --brake-decel-straight 10 --brake-overspeed-straight-ms 2.5 --brake-slip-limit 0.25 --brake-slip-hold 0.85 --pedal-technique --brake-profile --brake-circle 10 --exit-circle 14.6 --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_smooth.json --experiment a2_suave_125_g3_lat9_slip5_v60_ff0_cap100_pv03_gas1_fr10_perfil_c10_slip_exit146_l4b --laps 4
```

**A2.0, receta base histórica (sin técnica de pedales, `124357Z`, 120,5 s).**

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --teacher-only --speed-band 125 --max-gear 3 --lat-accel-limit 9 --steer-ff-gain 0.003 --steer-ff-v0-kmh 0 --steer-preview-s 0.3 --steer-slip-gain 5 --lat-gain-v0-kmh 60 --throttle-max 1.0 --brake-decel-straight 8 --brake-overspeed-straight-ms 2.5 --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_smooth.json --experiment a2_suave_125_g3_lat9_slip5_v60_ff0_pv03_gas1_fr8 --laps 3
```

**A2.0 con la técnica de pedales (V65, sesión de referencia `140704Z`: cumple V19 en 4 vueltas, 120,1 s).** La receta base con `--pedal-technique`
(y 4 vueltas: `aislado.py` pasa `--hold-stage` con `--teacher-only`; usar un nombre de experimento nuevo para no borrar el buffer anterior):

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --teacher-only --speed-band 125 --max-gear 3 --lat-accel-limit 9 --steer-ff-gain 0.003 --steer-ff-v0-kmh 0 --steer-preview-s 0.3 --steer-slip-gain 5 --lat-gain-v0-kmh 60 --throttle-max 1.0 --brake-decel-straight 8 --brake-overspeed-straight-ms 2.5 --pedal-technique --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_smooth.json --experiment a2_suave_125_g3_lat9_slip5_v60_ff0_pv03_gas1_fr8_pedal_l4b --laps 4
```

**A2.0 con la línea óptima (en prueba, no cumple todavía).** Igual, con `--lat-gain-v0-kmh 70`,
`--reference ...\sugo_optima_a1mu9b.json` y `--experiment a2_optA1mu9b_125_g3_lat9_slip5_v70_ff0_pv03_gas1_fr8`.
**Última sesión con la línea óptima (V58): lo mismo con `--steer-ff-cap-kmh 100`**, experimento
`a2_optA1mu9b_125_g3_lat9_slip5_v70_ff0_pv03_gas1_fr8_cap100`. Resultado: 2690-2860 m arreglado (CTE 0,85 m),
0 ruedas fuera, 118,9 s; no cumple por la S de 2400-2500 m (2,38 m) y una deriva de 5,6° en 920-930 m.
El modelo del volante no reproduce la S (V59), el tope 90 mejora una S y empeora la otra (V60) y la banda 115 no
ayuda (V61). La causa probable está en la línea (V61). Comando de la sesión con tope 100 a 125 km/h:

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --teacher-only --speed-band 125 --max-gear 3 --lat-accel-limit 9 --steer-ff-gain 0.003 --steer-ff-v0-kmh 0 --steer-ff-cap-kmh 100 --steer-preview-s 0.3 --steer-slip-gain 5 --lat-gain-v0-kmh 70 --throttle-max 1.0 --brake-decel-straight 8 --brake-overspeed-straight-ms 2.5 --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_optima_a1mu9b.json --experiment a2_optA1mu9b_125_g3_lat9_slip5_v70_ff0_pv03_gas1_fr8_cap100 --laps 3
```

**A1, aceleración hasta el techo.** Por encima de 135 km/h hace falta `--lat-gain-v0-kmh 70`; sin
él el volante oscila (V42). Con el pedal 1,0 de la frenada final se bloquean las delanteras, por eso el
techo se queda en 140 km/h hasta probar el limitador de frenada (V44; añadir `--brake-slip-limit 0.2` y
subir el techo solo después de la prueba de frenada de arriba):

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
Con salida por tubería, anteponer `PYTHONIOENCODING=utf-8`:

- A2.0: `experimental\common\resumen_sesion.py <log> --previsto <s>` (criterio de volante, tramos fuera
  de criterio, frenos, cambios de marcha, ruedas fuera).
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
| `--lat-accel-limit` | 9 | Límite lateral que el teacher supone en curva (máx. 14,6 por D21); el coche pide ≈ 1,5 veces ese valor | V27 |
| `--steer-ff-gain` + `--steer-ff-v0-kmh` | 0.003 y 0 | Anticipación de volante 1 + 0,003 · v². A más de 100 km/h se pasa de lo que pide el coche; bajar a 0.002 arregla las curvas rápidas y estropea las lentas | V21, V38-V41 |
| `--steer-ff-cap-kmh` | 0 (sin tope); **100 en la receta vigente** (V72: C14 de 2,0 a 0,95 m y C13 de 1,65 a 1,2 m) | Con `--steer-ff-gain`: por encima de esta velocidad el factor 1 + G · v² deja de crecer; sin cambio por debajo; sin probar en el juego | V41, V57 |
| `--steer-preview-s` | 0.3 | La curvatura del volante se lee a v · 0,3 s y no a 30 m fijos | V22 |
| `--steer-slip-gain` | 5 | Contravolante por deriva (zona muerta 3°, la ganancia de CTE baja a 0 a 8°) | V17 |
| `--lat-gain-v0-kmh` | 60 con la línea suavizada; 70 con la óptima y en A1 | Ganancia de CTE × (v0/v)² por encima de v0: estabilidad del lazo a alta velocidad; sin ella oscila a más de 135 km/h. No subir a 80 | V18, V35, V42 |
| `--throttle-max` | 1.0 | Gas a fondo (producción 0,85: acelera un 15-20 % menos) | V24, V25 |
| `--brake-decel-straight` + `--brake-overspeed-straight-ms` | 8 y 2.5 | En recta (\|κ\| < 0,004 y \|CTE\| < 1 m) frena a ≈ 8-11 m/s² y no al 40 % de lo que da el coche | V31, V32 |
| `--reference` | `sugo_smooth.json` o `sugo_optima_a1mu9b.json` | Línea que sigue el teacher | V14, V32, V36 |
| `--brake-slip-limit` | 0 (apagado); 0.2 para frenar desde más de 123 km/h | Si 1 − rps delanteras / rps traseras pasa de este valor, el pedal baja y vuelve a subir al recuperar agarre; actúa sobre el pedal de cualquier origen, también `--ident frenar` | V43, V44 |
| `--brake-slip-hold` | 0 (sin memoria); 0.85 | Con `--brake-slip-limit`: tras pasar del objetivo el pedal sube deprisa solo hasta esta fracción del pedal que lo provocó y despacio desde ahí, en lugar de volver a 1,0 y oscilar; sin probar en el juego | V49, V50 |
| `--pedal-technique` | apagado | Técnica de pedales (solo con el modelo físico): gas cortado del todo y enclavado antes de frenar, freno que se suelta en proporción al exceso hasta el vértice y gas que solo sube desde el vértice; sin probar en el juego | V65 |
| `--pedal-exit-slew` | 1.5 | Con `--pedal-technique`: subida máxima del gas por segundo desde el vértice (1,5 = de 0 a fondo en ≈ 0,7 s; con 0,8 el coche de juguete perdía 1,2 s) | V65 |
| `--brake-profile` | apagado; en la receta vigente | Con `--pedal-technique` (V68): consigna de velocidad continua por barrido hacia atrás con el círculo de adherencia (sin el salto 8 → 4 m/s² al entrar en la curva) y freno por avance sin margen ni tiempo muerto; usa `--brake-decel-straight` como `a_b` | V68-V71 |
| `--brake-circle` | 14.6; **10 en la receta vigente** | Con `--brake-profile`: radio del círculo en unidades de la línea. 14,6 = trail braking completo; ≈ 10 = casi terminar de frenar antes de girar (el coche hace ≈ 1,45 veces el lateral que cree la línea) | V69-V70 |
| `--brake-decel-straight` | 8 (producción); **10 con el limitador en la receta vigente** | Deceleración en recta que supone el teacher; con `--brake-profile` es la `a_b` del perfil | V31, V71 |
| `--exit-circle` | 0 (apagado); **14.6 en la receta vigente** | Con `--pedal-technique` (V72, F3): en la salida el gas no pasa de `gas_max · √(1 − (lateral medido / R)²)` (0,60 a 11,7 m/s²); cuesta ≈ 0,23 s por vuelta y baja el \|CTE\| en casi todas las curvas | V72-V73 |

`aislado.py` pasa siempre `--hold-stage` a `learn_driver.py` con `--teacher-only` (V64): sin él dos vueltas limpias cerraban la sesión aunque `--laps` fuese mayor.

Reglas de `aislado.py` para estas opciones: sin `--ident` exigen `--teacher-only` y un
`--experiment` con prefijo `a2_` (el nombre por defecto borraría el buffer `teacher_<banda>`); con
`--max-gear 2` la banda máxima es 115 km/h. Con `--ident` se aceptan y se pasan igual.

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

Con la línea óptima los resultados están en `DECISIONES.md` (V33-V41).

Criterio de volante para subir de banda (V19, provisional): 2 vueltas completas seguidas, sin
salirse, con rectas de volante rms ≤ 0,04, ≤ 1 inversión/100 m y |CTE| rms ≤ 0,25 m, y curvas con
tasa ≤ 0,2/s, |CTE| máx. ≤ 1,8 m y deriva máx. ≤ 4°; además, 0 ticks con ruedas fuera de la
superficie de carrera. Referencia: la IA a ritmo real hace 97,9 s.

### Qué está probado y qué no

- **Probado:** teacher en 2.ª hasta 110 km/h y con 3.ª hasta 125 km/h, dos vueltas limpias por banda (el solver
  tiene las tablas de aceleración hasta 140 km/h desde V56, pero no hay vuelta completa a más de 125);
  aceleración en 3.ª hasta 140 km/h con el volante tranquilo (y el motor hasta 149,9 km/h); frenada
  fuerte en recta hasta 123 km/h con pedal ≤ 0,84 y sin bloqueo (11,6 m/s²); el solver acierta el
  tiempo de vuelta con el coche de A1 en cada banda (−0,2 % a +1,0 %).
- **Con aviso:** las frenadas a fondo de A1 desde 100, 110, 135, 140 y 150 km/h (pedal 1,0, 11,5-11,9
  m/s²) bloquean las delanteras a los ≈ 0,3 s y hasta casi parar; el «sin bloqueo» anterior solo
  miraba las traseras (V42-V43).
- **Sin validar:** el limitador de frenada en el juego (V44); frenadas sin bloqueo desde más de 123 km/h; aceleración por encima de 140 km/h con
  el volante tranquilo; 4.ª marcha; límite lateral por encima de 14,6 m/s² sostenidos (A1.3b);
  cualquier otra pista o coche; los bordes reales (D1b: semivía de 0,85 m y margen supuestos).

## Reglas de la sesión (no olvidar)

- **El usuario lanza el juego, yo nunca.** No ejecutar `aislado.py` ni `learn_driver.py` con
  argumentos válidos, ni para «probar» la CLI: lanza una sesión real y borra el buffer del
  experimento (incidente c0_log, memoria `feedback-no-ejecutar-aislado-para-probar`). Para
  comprobar una línea de comandos: `build_argv` y `a2_error` de `aislado.py` desde Python.
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
- Camino sólido a largo plazo, sin prisa. Si hay que elegir, recomendar y no listar todo.

## Siguiente (en este orden)

La historia de cada sesión de hoy (F1-1, F1-1b, F1-2, cap 100, exit-circle) está en `DECISIONES.md` V69-V73; aquí solo lo que toca.

0. **Al empezar:** `git status` y preguntar por los dos commits propuestos (ver «Dónde estamos»); leer la receta vigente (arriba) y `docs/TECNICA_CONDUCCION.md` §8-§9. Cuando el usuario diga «la curva N», es el catálogo C1-C14.
1. **Repetir `--lat-accel-limit 10` sin cambiar nada** (V74: la primera sesión dio 118,8-118,9 s, −1,9 s, y falló V19 por 0,04 m en C11 y 0,1° en la deriva de C5; con esos márgenes no se distingue ruido de efecto). Solo cambia el nombre del experimento (`..._l4b`). Éxito: una pareja de vueltas seguidas que cumpla V19 y tiempo < 120,3 s; entonces el límite 10 pasa a receta vigente. Si C11 vuelve a pasar de 1,8 m o la deriva de C5 de 4°: `--lat-accel-limit 9.5`. Vigilar C4 (el \|CTE\| máx. subió por vuelta de 0,36 a 0,99 m) y el lateral máximo (hoy 14,4; cota 14,6). No relajar los umbrales de V19. El usuario atento en las primeras vueltas.

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --teacher-only --speed-band 125 --max-gear 3 --lat-accel-limit 10 --steer-ff-gain 0.003 --steer-ff-v0-kmh 0 --steer-ff-cap-kmh 100 --steer-preview-s 0.3 --steer-slip-gain 5 --lat-gain-v0-kmh 60 --throttle-max 1.0 --brake-decel-straight 10 --brake-overspeed-straight-ms 2.5 --brake-slip-limit 0.25 --brake-slip-hold 0.85 --pedal-technique --brake-profile --brake-circle 10 --exit-circle 14.6 --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_smooth.json --experiment a2_suave_125_g3_lat10_slip5_v60_ff0_cap100_pv03_gas1_fr10_perfil_c10_slip_exit146_l4 --laps 4
```

(Es el comando de la sesión `213236Z`; para la repetición, cambiar el final del nombre del experimento a `_l4b`.)

2. **La línea óptima con la receta vigente** (una variable respecto a la receta vigente: `--reference …\sugo_optima_a1mu9c12.json`). El solver prevé −1,4 s y con la receta antigua dio 119,3-119,5 s (V64) pero rompía zonas rápidas o la S según la receta; la receta nueva (cap 100, tope del gas, perfil) no se ha probado con ella. Éxito: pareja de vueltas que cumpla V19 y tiempo < 119,8 s.

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --teacher-only --speed-band 125 --max-gear 3 --lat-accel-limit 9 --steer-ff-gain 0.003 --steer-ff-v0-kmh 0 --steer-ff-cap-kmh 100 --steer-preview-s 0.3 --steer-slip-gain 5 --lat-gain-v0-kmh 60 --throttle-max 1.0 --brake-decel-straight 10 --brake-overspeed-straight-ms 2.5 --brake-slip-limit 0.25 --brake-slip-hold 0.85 --pedal-technique --brake-profile --brake-circle 10 --exit-circle 14.6 --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_optima_a1mu9c12.json --experiment a2_optA1mu9c12_125_g3_lat9_slip5_v60_ff0_cap100_pv03_gas1_fr10_perfil_c10_slip_exit146_l4 --laps 4
```

3. **Pendientes menores del circuito:** deriva de C5 en las vueltas 1-2 (4,0-4,8°, inversión del volante de la S); ruedas fuera en C4 (87 ticks) y en la recta C8→C9 (140, desde V63); C3 sube un poco cada vuelta (0,93 → 1,27 m); la banda de 125 km/h es el tope de las rectas (subirla gana tiempo en rectas, pide repetir G2/G3).
4. **Más técnica** (`TECNICA_CONDUCCION.md` §5): F10 gas con espera en la salida de curvas cerradas, F11 clasificar las curvas, F12 eses, F13 horizonte de mirada, F5 puntos de frenada adaptativos, F6 cambios de marcha respecto a la frenada, F7 neumáticos (se enfrían de 80 a 46 °C en 4 vueltas).
5. **Decidir la tabla de frenada del solver** (V55, punto 4; enlaza con F4, perfil del solver como archivo): la de `parametros_a1.json` (45-105 km/h, 11,87-13,05 m/s²) y las medias por ventanas de V55 (10,3-12,0 m/s²) no coinciden. Las tablas de A1 ya descuentan la pendiente. Datos de partida (radio efectivo 0,274 m): sin bloqueo el deslizamiento delantero va al 10-15 % con pedal 0,6-0,95; con bloqueo (80-110 %) la deceleración baja a 11,9 m/s² frente a 12,5-12,7 con el 20-50 %.
6. ~~Actualizar la tabla de aceleración de A1 y el tope del solver~~ **Hecho (V56).** Queda, si se quiere, una sesión de aceleración con techo 150 km/h (`--ident acel --ident-cap-kmh 150 --lat-gain-v0-kmh 70`).

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
   (72 bytes entre `tyre_tread_temp` y `ride_height`), que cuadran con temperaturas de capa,
   carcasa, llanta y aire interno y temperatura izquierda/centro/derecha de la banda por rueda
   (inferencia por tamaño, sin confirmar; un hilo de Reiza dice que van en el UDP). Comprobar
   guardando esos bytes en bruto en una sesión corta.
5. **D1b: mapeo de bordes con sesiones** (necesita visto bueno del usuario). Diseño en
   `docs/PLAN.md`, sección «D1b»: `src/sesion_mapeo.py` (sin escribir) no arranca el juego;
   escribe referencias desplazadas en `pistas/sugo_gp/desplazadas/` e imprime los comandos de
   `aislado.py` (`--teacher-only --speed-band 30 --reference <archivo> --experiment
   mapa_<lado>_<k>`), una ronda por lado y avance de 0,4 m (0,2 m cerca de muros). Antes de la
   primera ronda, revisar la guardia de superficie (una o dos ruedas en hierba son `edge_surface`,
   tres son `off_surface`). Calibrar de paso la semivía de 0,85 m. Éxito: los dos bordes medidos en
   ≥ 90 % de la vuelta con incertidumbre ≤ 0,3 m. **Hoy el coche pasó el 16,7 % del tiempo fuera del
   pasillo comprobado sin pisar nunca fuera del asfalto (V33): el pasillo real es más ancho.**
6. **A3, segunda pista:** repetir A2 con otra pista y otra IA para saber si el factor de ritmo y
   las envolventes se generalizan. Requiere `circuito_virtual/pistas/<pista>/` con mapa y
   referencia suavizada.
7. **Rivales:** ver si el paquete de tiempos trae la posición de los rivales (hoy solo se lee al
   participante propio; el relay de memoria compartida del Telemetry Tool dice dar «posición y
   velocidad de otros coches»), antes de D5.
8. **PPO residual sobre el teacher:** la técnica de curva del manual (frenar fuerte y soltar con el giro, mínimo en el ápice, gas progresivo con tope por el círculo) ya está en el teacher (paso 4 de V17; V65-V73, `TECNICA_CONDUCCION.md`), así que el PPO va después como corrección acotada sobre ese teacher (V17); antes, revisar el estado de `ppo_guard`, `ppo_anchor` y `ppo_bootstrap`, y decidir si el BC aprende la receta vigente (los logs ya traen `long_accel`, el catálogo de curvas y las razones `lift_lock`/`accel_exit` normalizadas al vocabulario del BC).

## Ideas y referencias

- **Técnica de conducción** (V66): `docs/TECNICA_CONDUCCION.md` recoge lo que dicen PCA «The Art of Braking» y 8000vueltas (frenar y acelerar), lo que hace el teacher con datos y las fases F1-F9 pendientes. Las tres partes de 8000vueltas están leídas (V67); filas F10-F13 nuevas para la salida de curva, los tipos de curva, las eses y el horizonte de mirada.
- **Manual de Racelogic** (*Advanced Circuit Driving Techniques*, aportado por el usuario): volante
  mínimo («enderezar cada curva» valió 0,9 de 1 s en Eau Rouge); la velocidad en curva no es
  constante (frenada modulada, mínimo en el ápice); gas solo cuando no haya que soltarlo; una línea
  que usa todo el ancho pide menos volante (apoya la línea óptima).
- **Telemetry Tool for PC2 (Iko Rein) v15.09**, revisado en solo lectura: lee el mismo UDP; no trae
  canales de agarre para PC2 (carga por rueda y nivel de agarre son de F1 y rF2); sus indicadores
  útiles (deriva frente a guiñada, razón traseras/delanteras, índice de subviraje) se calculan con
  lo que ya registramos. El índice de subviraje sería un buen estado para el gas del paso 2.
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
- ~~Técnica de pedales implementada~~ **Hecho (V65):** `--pedal-technique` cumple V19 en 4 vueltas (`140704Z`); sus criterios del gas no se cumplen todavía.
