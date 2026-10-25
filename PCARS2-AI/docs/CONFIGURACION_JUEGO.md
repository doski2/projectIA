# Configuración del juego y del mando (Project CARS 2)

Valores con los que se grabaron y entrenaron todos los datos actuales. Si algo cambia en el
comportamiento del coche (volante que no responde, zona muerta, giros bruscos), compara primero
con esta tabla antes de tocar el código.

**Capturas de referencia:** 2026-10-25, pantalla *Controles → Configuración* del juego.
Circuito: Sugo; 19 °C ambiente, 24 °C circuito, viento 3 km/h, despejado; 18 L de combustible;
neumáticos lisos (1,69 / 1,55 bar).

## Controles → Configuración

| Opción                      | Valor | Nota                                                       |
| --------------------------- | ----: | ---------------------------------------------------------- |
| Zona muerta de dirección    |     0 | Sin zona muerta: el volante responde desde la primera señal |
| Sensibilidad de dirección   |    50 | Neutra (el juego equipara lo aplicado a lo introducido)    |
| Zona muerta de acelerador   |     0 |                                                            |
| Sensibilidad de acelerador  |    50 | Neutra                                                     |
| Zona muerta del freno       |     0 |                                                            |
| Sensibilidad del freno      |    50 | Neutra                                                     |
| Zona muerta de embrague     |     0 |                                                            |
| Sensibilidad de embrague    |    25 | Única sensibilidad que no está en 50                       |
| Sensibilidad de velocidad   |     0 | Sin reducción del volante al subir la velocidad            |
| Amortiguación de mando      |     0 |                                                            |
| Vibración del mando         |    50 |                                                            |
| Tiempo de cambio mínimo     |     0 |                                                            |
| Visor RPM/marchas           |    No |                                                            |

Los cambios en estas opciones se guardan y **surten efecto al volver a la central de carreras e
iniciar una nueva sesión** (indicado por el propio juego), no en caliente.

## Juego → Realismo (captura 2026-10-25)

| Opción                    | Valor                | Nota                                      |
| ------------------------- | -------------------- | ----------------------------------------- |
| Asistencia de dirección   | No                   |                                           |
| Asistencia al frenado     | No                   |                                           |
| Asistencias de conducción | Auténticas           | ABS Alto, control de estabilidad Auténtico, control de tracción Alto |
| Ayuda de bloqueo opuesto  | Desact.              |                                           |
| Tipo de daño              | Desact.              |                                           |
| Fallos mecánicos          | No                   |                                           |
| Desgaste de neumáticos    | Desact.              |                                           |
| Uso de combustible        | Desact.              |                                           |
| Arranque automático       | Sí                   | El motor se rearranca solo tras calarse   |
| Reglas y sanciones        | Desact.              |                                           |
| Parada en boxes manual    | No                   |                                           |

Los ajustes del mando se guardan en un fichero binario cifrado/comprimido
(`Documents\Project CARS 2\savegame\<id>\project cars 2\profiles\default.controllersettings.v1.03.sav`)
que no se puede leer ni editar a mano; `ffb_custom_settings.txt` es solo del force feedback de
volantes físicos y no afecta al mando virtual. Por eso la referencia son estas tablas y las
capturas.

## Curva de respuesta del volante (medida)

El juego **no aplica lo que se envía**. Medido con `vehicle.game_steer` frente a `steering`
(retardo de 3 ticks compensado, solo a más de 25 km/h): 18 sesiones, 639 250 ticks, y la curva
sale igual en todas, así que es estática.

| Enviado | 0,075 | 0,125 | 0,175 | 0,225 | 0,275 | 0,325 | 0,425 | 0,525 | 0,625 | 0,725 | 0,825 | 0,925 |
| ------- | ----: | ----: | ----: | ----: | ----: | ----: | ----: | ----: | ----: | ----: | ----: | ----: |
| Aplicado |0,007 | 0,028 | 0,058 | 0,096 | 0,140 | 0,193 | 0,317 | 0,468 | 0,618 | 0,780 | 0,917 | 0,990 |

Zona muerta blanda en el centro (órdenes menores de ~0,1 casi no hacen nada), ganancia menor
que 1 hasta ~0,6 y mayor que 1 entre 0,65 y 0,9. Los valores completos están en
[steering_curve.py](../src/steering_curve.py).

**Compensación (experimental, apagada por defecto):** `learn_driver --steer-comp`, o la casilla
*Compensar curva del volante* de la pestaña Aprendizaje. Envía la orden inversa para que lo
aplicado ≈ lo pedido. Riesgo: el teacher y el BC se ajustaron con la curva actual; con la
compensación la ganancia cerca del centro sube (hasta ~3×) y a volante alto baja (~30 %). Probar
primero a baja velocidad (L1 a 30 km/h) y comparar CTE y volantazos antes de subir.

**Verificación (2026-10-25, L1 a 55 km/h con `--steer-comp`, sesión
`20261025T004755Z_sugo_gp_l1_linea`):** `game_steer` ≈ **1,00** × volante pedido (2738 ticks con
|volante| > 0,15), frente a ≈ 0,82 sin compensar. Resultado frente a las dos sesiones a 55 km/h
sin compensar (`000528`, `001539`):

| Métrica                          | Sin compensar        | Con compensación          |
| -------------------------------- | -------------------- | ------------------------- |
| Vuelta 1 completada              | No (se salía a 1389 m) | Sí, 5:03, CTE medio 0,48 m |
| CTE máximo                       | 8,3 m                | 2,0 m                     |
| Ticks con volante > 0,9          | 2729                 | 0                         |
| Ticks de `edge_grass`            | 619                  | 23                        |
| Cuota de conducción del BC       | 55 %                 | 76,5 %                    |

Dos vueltas limpias seguidas (CTE medio 0,48 y 0,26 m) y paso a L2. La variable que cambió fue la
compensación; no se puede separar su efecto del de `damp_bc_steering` porque ambos estaban
disponibles en la prueba. Las etiquetas del teacher (la orden que da el teacher en cada estado)
siguen siendo válidas con la compensación: lo que cambia es cómo las realiza el coche.

## Reglajes del coche (capturas 2026-10-25)

Coche de fórmula de 4 marchas (`num_gears = 4` en el log) en Sugo. Reglaje **simétrico**
(izquierda = derecha). Solo se anotan los valores visibles en las capturas.

### Neumáticos, frenos y chasis

| Opción                          | Delantero      | Trasero        |
| ------------------------------- | -------------- | -------------- |
| Compuesto                       | Lisos, Automático | Lisos, Automático |
| Presión de los neumáticos (reglaje) | 1,25 bar   | 1,15 bar       |
| Presión mostrada (en caliente)  | 1,51 bar       | 1,39 bar       |
| Temperatura (int. / centro / ext.) | 87 / 87 / 87 °C | 87 / 87 / 87 °C |

| Opción                         | Valor       |
| ------------------------------ | ----------- |
| Presión de los frenos          | 90 %        |
| Equilibrio de frenos           | 60,0 / 40,0 |
| Reparto de peso longitudinal   | 45,0 / 55,0 |

> Las capturas de Controles y Realismo mostraban 1,69-1,70 bar delante y 1,55-1,57 bar detrás
> en el marcador superior; las de Reglajes, 1,51 / 1,39 bar. **Si las presiones se cambiaron
> hoy, las sesiones anteriores se grabaron con otras.** Anotar aquí la fecha de cada cambio.

### Suspensión

| Opción               | Delantera    | Trasera     |
| -------------------- | ------------ | ----------- |
| Relación de dirección | **12,0 : 1** | —           |
| Ángulo de pivote     | 5,0°         | —           |
| Ángulo de caída      | -1,5°        | -2,0°       |
| Ángulo de puntera    | -0,2°        | 0,4°        |
| Altura de rodaje     | 85 mm        | 95 mm       |
| Índice de rigidez (muelle) | 48 N/mm | 38 N/mm     |
| Barra estabilizadora | 20 N/mm      | 2 N/mm      |

### Amortiguadores

| Opción                   | Delantero   | Trasero     |
| ------------------------ | ----------- | ----------- |
| Tope de amortiguación    | 20 mm       | 20 mm       |
| Compresión lenta         | 3600 N/m/s  | 2300 N/m/s  |
| Extensión lenta          | 3700 N/m/s  | 3700 N/m/s  |
| Compresión rápida        | 1600 N/m/s  | 1500 N/m/s  |
| Extensión rápida         | 2300 N/m/s  | 2000 N/m/s  |
| Transición de compresión | 250 N       | 100 N       |
| Transición de extensión  | -210 N      | -200 N      |

### ECU / motor / marchas

| Opción               | Valor                 |
| -------------------- | --------------------- |
| Carga de combustible | 33 L (47 vueltas)     |
| Apertura del radiador | 75 %                 |
| Freno de motor       | 8                     |
| Transmisión final    | 3,444                 |
| 1.ª / 2.ª marcha     | 2,846 / 1,875         |
| 3.ª / 4.ª marcha     | 1,421 / 1,125         |

> El marcador superior seguía mostrando 18 L mientras el reglaje decía 33 L: comprobar cuál se
> aplicó en la sesión.

### Diferencial (trasero)

DDL por embragues: **Sí**; punto muerto (rampa en deceleración): **30°**. Precarga, número de
embragues y potencia de rampa no se veían en la captura, y el eje delantero quedó fuera de pantalla.

### Qué dice esto del comportamiento observado

- **Relación de dirección 12:1** es lo único del reglaje que toca directamente la ganancia del
  volante. Según la ayuda del juego, una relación mayor da menos ángulo de rueda por movimiento
  de volante (menos ganancia); una menor, más sensibilidad. Subirla reduciría la ganancia del
  lazo igual que `damp_bc_steering`, pero dentro del juego y para todas las velocidades, y
  limitaría el giro máximo en curvas cerradas. **Sin probar**, y cambia lo que el dataset
  aprendió, igual que cualquier ajuste del mando.
- **Marchas y bandas 70-80.** En 1.ª se miden ~92,6 rpm por km/h, y `auto_shift` sube a 2.ª al
  87 % del régimen máximo (estimo ~72 km/h con un máximo de ~7700 rpm; no leí `max_rpm` de la
  telemetría). Todas las sesiones hasta hoy fueron ≤ 61 km/h **sin pasar de 1.ª**, así que
  **la primera subida de marcha en vuelta llegará en las bandas 70 y 80** y es un
  comportamiento nuevo que conviene vigilar (`shift_event: up` en el log).
- **Nada del resto del reglaje** (muelles, amortiguadores, barras, diferencial, presiones)
  señala una causa clara del zigzag; no hay forma de deducirlo de las capturas. Barra trasera de
  2 N/mm frente a 20 N/mm delante y reparto 45/55 son valores poco habituales, anotados por si
  hay que revisarlos.

## Controles → Esquema de controles (captura 2026-10-25)

| Opción                | Valor                                         |
| --------------------- | --------------------------------------------- |
| Tipo                  | Volante                                       |
| Fabricante / modelo   | Fanatec / CSW V2.5                            |
| Tipo de pedales       | Combinados (un solo eje para gas y freno)     |
| Embrague automático   | Activ.                                        |
| Marchas               | Manual                                        |

El juego incluye perfiles de volante de Fanatec, Thrustmaster y Logitech.

> **No está confirmado que este fuera el esquema activo en las sesiones de aprendizaje.** Con
> pedales *combinados* el juego no podría aplicar gas y freno a la vez, y en los logs sí lo hace
> (`vehicle.game_throttle` y `game_brake` > 0,05 a la vez en 17 639 de 38 595 ticks de la sesión
> `20261024T182522Z_sugo_gp_l1_linea`, con valores iguales a lo enviado). Gas y freno se aplican
> de forma lineal y fiel; solo el volante tiene la curva no lineal medida arriba. Anotar aquí
> cuál es el esquema usado en cada sesión.
>
> *Embrague automático* activado y *Marchas* en manual encajan con lo observado: el motor se
> rearranca solo (Arranque automático) y las marchas se cambian con RB / LB.

## Qué no está en las capturas

Faltan por documentar las pestañas *Editar asignaciones* (qué botón
hace cada cosa: RB / LB para marchas, etc.) y *Force feedback*. Si se vuelven a revisar, añadir
una captura de cada una.

## Relación con el código

- **Volante.** El mando de Xbox se emula con `vgamepad` ([controller.py](../src/controller.py)).
  Referencia medida con esta configuración (sesión `20261025T000528Z_sugo_gp_l1_linea`, 2091
  ticks del BC con |volante| > 0,2, ajuste por el origen): `game_steer` ≈ **0,82** × volante
  enviado y `raw_steer` ≈ **0,90** × enviado. Incluye el retardo entre la orden y la respuesta,
  así que es una pendiente aparente, no la ganancia estática. Si en otro coche o configuración
  estos cocientes cambian mucho, el mando ha cambiado. Ver el Flujo B de
  [PLAN_NUEVAS_PISTAS_Y_COCHES.md](PLAN_NUEVAS_PISTAS_Y_COCHES.md).
- **Marchas.** RB sube y LB baja ([TEACHING_MARCHAS_Y_DATASET.md](TEACHING_MARCHAS_Y_DATASET.md)).
  «Tiempo de cambio mínimo» en 0 y «Visor RPM/marchas» en No no afectan al envío de botones.
- **Oscilación del volante a 55-60 km/h.** Con *Sensibilidad de velocidad* = 0 el juego no reduce
  el volante al subir la velocidad. Ya se amortigua del lado del código
  (`damp_bc_steering`, argumento `--steer-damp-kmh` de `learn_driver`). *Sensibilidad de
  velocidad* y *Amortiguación de mando* del juego son dos palancas alternativas **sin probar**;
  si se prueban, anotar aquí el valor y el resultado, porque cambiar el mando obliga a regrabar
  el dataset del teacher (las respuestas del coche a la misma orden ya no serían las mismas).

## Registro de cambios

| Fecha      | Cambio                              | Motivo |
| ---------- | ----------------------------------- | ------ |
| 2026-10-25 | Configuración inicial documentada   | Referencia para volver a ajustar |
| 2026-10-25 | Reglajes del coche documentados (capturas); notas sobre marchas 70-80 y presiones | Referencia para volver a ajustar |
| 2026-10-25 | Compensación del volante verificada en L1 a 55 km/h (pendiente 1,00; CTE máx. 8,3 → 2,0 m) | Resultado de la prueba |
| 2026-10-25 | Medida la curva de respuesta del volante; compensación opcional | El volante aplicado es la mitad del pedido por debajo de ~0,3 |
