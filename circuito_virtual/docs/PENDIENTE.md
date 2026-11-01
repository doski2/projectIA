# Pendiente de circuito_virtual

Orden de trabajo y estado al cierre de la sesión del **2026-11-01** (segunda parte: el teacher de
A2.0 pasó de salirse a los 30 s a rodar vueltas completas a 125 km/h). Lo que no es del circuito
(rampa del BC, PPO, daño de motor P26, controles de seco, reentreno v2) sigue en
`experimental/docs/PENDIENTE.md`. Las decisiones están en `docs/DECISIONES.md` (V1-V35), el plan
en `docs/PLAN.md` y la historia en `docs/DIARIO.md`.

## Dónde estamos (para retomar sin releer nada)

- **Último commit:** `065844d` (D2, V15). **Todo lo de V16-V35 está sin commit** (ver la lista de
  abajo); el usuario decide cuándo y cómo se commitea.
- **Tests en verde:** `circuito_virtual` 53, `experimental` 82, `PCARS2-AI` 489. Se lanzan con
  `pytest` dentro de cada carpeta.
- **Sin commit, código de producción tocado con visto bueno del usuario** (cada opción es opt-in y
  su valor por defecto es el de producción):
  `PCARS2-AI/src/teacher_controller.py`, `PCARS2-AI/src/learn_driver.py` y
  `PCARS2-AI/tests/test_teacher_controller.py`.
- **Sin commit, resto:** `experimental/common/aislado.py`, `analisis_volante.py` (nuevo),
  `resumen_sesion.py` (nuevo), `analisis_a1.py` (arreglos), sus tests;
  `circuito_virtual/src/linea_optima.py` (`coche_a1`, `--coche-a1-mu`), `bordes_logs.py`
  (`actualizar`), `pistas/sugo_gp/observaciones_logs.json` (124 logs), `sugo_optima_a1mu9_n.npy`,
  `.gitignore` y estos documentos.
- **Archivos locales no versionados que hacen falta para la próxima prueba:**
  `circuito_virtual/pistas/sugo_gp/sugo_smooth.json` y `sugo_optima_a1mu9.json` (4,5 MB cada uno).
  Si falta el segundo: `python circuito_virtual/src/linea_optima.py --coche-a1-mu 9
  --max-barridos 80` (≈ 70 s); si falta el primero: `python circuito_virtual/src/linea_suave.py`.

### Receta actual del teacher (todas las opciones, qué hace cada una y dónde se decidió)

| Opción de `aislado.py` | Valor | Qué hace | Decisión |
| --- | --- | --- | --- |
| `--teacher-only --max-gear 3` | 3 (2 hasta 115 km/h) | El teacher conduce y el cambio sube hasta 3.ª (techo 150 km/h con 3.ª) | X24, V28-V30 |
| `--lat-accel-limit` | 9 | Límite lateral que el teacher supone en curva (máx. 14,6 por D21); el coche pide ≈ 1,5 veces ese valor | V27 |
| `--steer-ff-gain` + `--steer-ff-v0-kmh` | 0.003 y 0 | Anticipación de volante 1 + 0,003 · v² (lo que pide la curva, ≈ H58) | V21 |
| `--steer-preview-s` | 0.3 | La curvatura del volante se lee a v · 0,3 s y no a 30 m fijos | V22 |
| `--steer-slip-gain` | 5 | Contravolante por deriva (zona muerta 3°, la ganancia de CTE baja a 0 a 8°) | V17 |
| `--lat-gain-v0-kmh` | 70 (antes 60) | Ganancia de CTE × (v0/v)² por encima de v0: estabilidad del lazo a alta velocidad; con 70 los tramos con \|CTE\| > 1,8 m pasan de 7 a 1 por vuelta y las rectas siguen tranquilas; no subir a 80 | V18, V33, V35 |
| `--throttle-max` | 1.0 | Gas a fondo (producción 0,85: acelera un 15-20 % menos) | V24, V25 |
| `--brake-decel-straight` + `--brake-overspeed-straight-ms` | 8 y 2.5 | En recta (\|κ\| < 0,004 y \|CTE\| < 1 m) frena a ≈ 8-11 m/s² y no al 40 % de lo que da el coche | V31, V32 |
| `--reference` | `sugo_smooth.json` o `sugo_optima_a1mu9.json` | Línea que sigue el teacher | V14, V32, V33 |

Reglas de `aislado.py` para estas opciones: sin `--ident` exigen `--teacher-only` y un
`--experiment` con prefijo `a2_` (el nombre por defecto borraría el buffer `teacher_<banda>`); con
`--max-gear 2` la banda máxima es 115 km/h.

### Escalera medida (vuelta lanzada, línea suavizada salvo la última fila)

| Banda | Límite lat. | Cambios | Vuelta medida / prevista | \|CTE\| máx. | Deriva máx. | Decisión |
| --- | --- | --- | --- | --- | --- | --- |
| 80 | 7,5 | 2.ª | 162,8 / 163,9 s | 0,71 m | 1,0° | V23 |
| 90 (gas 1,0) | 7,5 | 2.ª | 148,9 / 149,6 s | 0,85 m | 1,3° | V25 |
| 100 | 9 | 2.ª | 135,4 / 135,7 s | 1,42 m | 2,9° | V27 |
| 110 | 9 | 2.ª | 128,0 / 127,9 s | 1,42 m | 3,4° | V28 |
| 120 | 9 | 2.ª-3.ª | 123,4 / 122,6 s | 1,77 m | 1,6° | V30 |
| 125 | 9 | 2.ª-3.ª | 121,8 / 120,6 s | 1,59 m | 3,5° | V31 |
| 125 + frenada fuerte | 9 | 2.ª-3.ª | 120,4 / 120,6 s | 1,56 m | 2,5° | V32 |
| 125 + frenada + **línea `a1mu9`** | 9 | 2.ª-3.ª | **118,7** / 117,6 s | **2,27 m (no cumple ≤ 1,8)** | 3,4° | V33 |
| ídem con `--lat-gain-v0-kmh 70` | 9 | 2.ª-3.ª | 118,7 / 117,6 s | 1,89 m (no cumple) | **5,1° (no cumple ≤ 4)**; 40 ticks con ruedas fuera | V35 |

Criterio de volante para subir de banda (V19, provisional): 2 vueltas completas seguidas, sin
salirse, con rectas de volante rms ≤ 0,04, ≤ 1 inversión/100 m y |CTE| rms ≤ 0,25 m, y curvas con
tasa ≤ 0,2/s, |CTE| máx. ≤ 1,8 m y deriva máx. ≤ 4°. Referencia: la IA a ritmo real hace 97,9 s.

### Qué está probado y qué no

- **Probado:** teacher en 2.ª hasta 110 km/h y con 3.ª hasta 125 km/h, dos vueltas limpias por
  banda; frenadas a fondo desde 100, 110 y 115 km/h con bajada de marcha 3.ª → 2.ª → 1.ª
  (G3, V29: 11,5-11,8 m/s², sin bloqueo); frenada fuerte en recta hasta 123 km/h (V32: 11,6 m/s²);
  el solver acierta el tiempo de vuelta con el coche de A1 en cada banda (−0,2 % a +1,0 %).
- **Sin validar:** frenadas desde más de 115 km/h; aceleración por encima de 135 km/h (G1b);
  4.ª marcha; límite lateral por encima de 14,6 m/s² sostenidos (A1.3b); cualquier otra pista o
  coche; los bordes reales (D1b: semivía de 0,85 m y margen de 0,3 m supuestos).

## Reglas de la sesión (no olvidar)

- **El usuario lanza el juego, yo nunca.** No ejecutar `aislado.py` ni `learn_driver.py` con
  argumentos válidos, ni para «probar» la CLI: lanza una sesión real y borra el buffer del
  experimento (incidente c0_log, memoria `feedback-no-ejecutar-aislado-para-probar`). Para
  comprobar una línea de comandos: `build_argv` y `a2_error` de `aislado.py` desde Python.
- **Una sola variable por sesión** y primero el volante, después la velocidad (V19): es lo que ha
  funcionado en toda la escalera.
- Antes de cada sesión arriesgada (techo alto, frenadas desde más de 115 km/h, arcos, mapeo de
  bordes) confirmar que el usuario está delante del juego y en seco, y que corta con Ctrl+C si el
  coche oscila.
- Dependencias en un solo sentido: `PCARS2-AI` ← `circuito_virtual` ← `experimental`.
  `circuito_virtual` no importa de `experimental`.
- Documentos de `circuito_virtual/` y `experimental/` en **LF**; en `PCARS2-AI/` los `.py` son
  CRLF salvo los tests nuevos (usar una utilidad que respete cada archivo). Para escribir archivos
  largos usar Write y no scripts de Python con `\n` dentro de cadenas en la línea de comandos.
- El usuario reformatea los docs con markdownlint: no comprobar texto con búsquedas literales
  frágiles (usar regex tolerante a espacios).
- Camino sólido a largo plazo, sin prisa. Si hay que elegir, recomendar y no listar todo.
- Comando de Python del usuario: `C:\Users\doski\projectIA\.venv\Scripts\python.exe` y **rutas
  absolutas** (su terminal puede estar en `circuito_virtual`, no en la raíz).

## Siguiente sesión

### 1. Resultado de `--lat-gain-v0-kmh 70` con la línea `a1mu9` (V35, hecho)

Log `20261101T171900Z`. Mejora el seguimiento pero **no cumple el criterio de V19**:

| Medida | V33 (v0 = 60) | V35 (v0 = 70) | Criterio |
| --- | --- | --- | --- |
| Vuelta lanzada | 118,7 s | 118,7 s | previsto 117,6 s |
| \|CTE\| máx. en curva | 2,27 m | 1,89 m | ≤ 1,8 m |
| Tramos con \|CTE\| > 1,8 m por vuelta | 7 | 1 (2484-2494 m, vuelta 2) | 0 |
| Deriva máx. | 3,4° | **5,1°** (921-931 m, las dos vueltas, 96 km/h, 2.ª) | ≤ 4° |
| Ticks con ruedas fuera | 0 | **40** (2 episodios, ruedas izquierdas) | 0 |
| Rectas (rms, inversiones, \|CTE\| rms) | 0,010 / 0,20 / 0,18 | 0,012 / 0,28 / 0,19 | OK |

Las ruedas fuera: vuelta 1, 1444-1454 m, hierba a 125 km/h con el coche 1 m a la izquierda de una
línea que va de −0,4 a +0,8 m en 60 m (el coche va por detrás desde 1425 m); vuelta 2, 759-771 m,
terreno 48 a 69 km/h con la rueda izquierda a ≈ −1,05 m (pasillo comprobado ≈ −1,0 m; ahí el pasillo es más
estrecho que el coche más el margen y la línea deja ≈ 0,2 m).

Se queda `--lat-gain-v0-kmh 70` en la receta. **No subir a 80**: lo que falla ya no es ganancia
sino el retraso del coche donde la línea cambia de lado, y más ganancia sube la deriva.

### 2. Rehacer la línea (la única variable de la próxima sesión)

Trabajo sin juego, en `linea_optima.py` (hoy solo hay `--margen`, `--paso-nudos`,
`--max-barridos`, `--coche-a1-mu`):

1. **Penalizar el salto de curvatura** (hoy 0,00175, un 25 % más que la suavizada) y/o limitar la
   velocidad de cambio de `n` (m por m de recorrido) para que el coche pueda seguirla a 125 km/h.
2. **Margen al borde donde hoy se relaja:** `pasillo_centro` recorta `lo`/`hi` a 0 para que el eje
   quepa; donde el pasillo comprobado mide menos de `2 · semivía + 2 · margen` (759-771 m: cota
   izquierda del centro ≈ +0,07 m) la línea queda a ≈ 0,2 m de la rueda al borde. Decidir si se
   estrecha la semivía supuesta o se ensancha el pasillo con sesiones de mapeo (D1b) en esos
   tramos. En 1444-1454 m la línea sí tiene margen: allí falla el seguimiento (punto 1).
3. **Pasillo ampliado:** añadir el log de V35 (`bordes_logs.py actualizar`) y regenerar con
   `linea_optima.py --coche-a1-mu 9 --max-barridos 80` (≈ 70 s) a otro nombre, sin pisar
   `sugo_optima_a1mu9.json` hasta compararlas.
4. Comparar tiempo previsto (117,6 s con la actual; se acepta perder ≤ 0,5 s), salto máximo de
   curvatura y margen mínimo a los bordes.

Después, una sesión con la receta de V35 (v0 = 70) y la línea nueva en `--reference` y un
`--experiment` con otro nombre (p. ej. `a2_optA1mu9b_125_g3_lat9_slip5_v70_ff0_pv03_gas1_fr8`).
Analizarla con `resumen_sesion.py <log> --previsto <tiempo previsto de la línea nueva>`
(en Windows con tubería: `PYTHONIOENCODING=utf-8`, si no falla por la codificación al imprimir
`≤`). Éxito: |CTE| máx. ≤ 1,8 m, deriva ≤ 4°, 0 ticks con ruedas fuera, rectas tranquilas.

#### Qué decidir con el resultado

| Resultado | Qué hacer |
| --- | --- |
| Cumple todo, incluidos 0 ticks fuera | Pasar al punto 1 de «Después» (techo a 150 km/h y frenadas desde más de 115 km/h) |
| Cumple el CTE pero la deriva sigue > 4° en 921-931 m | Limitar el gas en esa salida (curvatura y deriva) o bajar el límite lateral del solver en ese tramo; una sola variable |
| Sigue con ruedas fuera | Subir `--margen` de la línea y revisar la semivía (D1b); no tocar el teacher |
| Aparece balanceo en rectas | Ctrl+C; volver a `--lat-gain-v0-kmh 60` |

## Después (en este orden)

1. **Techo y frenadas por encima de 115 km/h** (necesarios para bandas > 125): sesión del techo
   a 150 km/h (G2) y G3 desde 130 y 140 km/h.

   ```text
   C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --ident acel --speed-band 60 --ident-cap-kmh 150 --max-gear 3 --ident-straights 1 --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_smooth.json --experiment a1_acel_g3_150_60 --laps 3
   ```

   Éxito: llega a 150 km/h sin cortes por CTE (> 2,5 m), rumbo (> 0,30) ni fuera de asfalto; volante
   ±0,05; sin daño. En G1b la 3.ª llegó a 134,9 km/h con 6323 rpm y el par ya bajaba (127,6 →
   119,8); el cambio sube a 3.ª hacia 108 km/h. Si la recta 1 (3132-3393 m, 260 m) se queda corta
   para frenar, mirar `--ident-end-margin-m`. Luego las bandas 130, 140 y 150 de A2.0.
2. **Medir el límite lateral del coche (A1.3b)**: el teacher ya pide 13-15 m/s² sostenidos con
   `--lat-accel-limit 9`, en la cota validada de D21 (≥ 14,6). Subir más exige arcos en 3.ª y 4.ª
   (D23). Riesgo de daño de motor (P26): tres de tres sesiones de arcos lo dieron hacia los 607 s;
   `aislado.py` ya pasa `--stop-on-damage`; sesiones cortas.
3. **A/B de la ayuda de bloqueo opuesto (D12, P20):** el log no muestra intervención
   (`game_steer` ≈ `raw_steer`, diferencia media 0,017) pero no se sabe si actúa sin reflejarse.
   Misma sesión con la ayuda desactivada (ajuste del juego, se aplica al empezar una sesión
   nueva; anotarlo en el nombre del experimento).
4. **Completar el reglaje del diferencial:** del trasero solo se ve «DDL por embragues: Sí» y rampa
   en deceleración de 30°; faltan precarga, embragues, potencia de rampa y todo el delantero
   (pedir captura). El freno de motor está en 8. No tocar el reglaje: A1 y A2 están medidos así.
5. **Datos de agarre sin leer:** `telemetry_udp.py` salta los bytes 224-295 del paquete de física
   (72 bytes entre `tyre_tread_temp` y `ride_height`), que cuadran con temperaturas de capa,
   carcasa, llanta y aire interno y temperatura izquierda/centro/derecha de la banda por rueda
   (inferencia por tamaño, sin confirmar; un hilo de Reiza dice que van en el UDP). Comprobar
   guardando esos bytes en bruto en una sesión corta.
6. **D1b: mapeo de bordes con sesiones** (necesita visto bueno del usuario). Diseño en
   `docs/PLAN.md`, sección «D1b»: `src/sesion_mapeo.py` (sin escribir) no arranca el juego;
   escribe referencias desplazadas en `pistas/sugo_gp/desplazadas/` e imprime los comandos de
   `aislado.py` (`--teacher-only --speed-band 30 --reference <archivo> --experiment
   mapa_<lado>_<k>`), una ronda por lado y avance de 0,4 m (0,2 m cerca de muros). Antes de la
   primera ronda, revisar la guardia de superficie (una o dos ruedas en hierba son `edge_surface`,
   tres son `off_surface`). Calibrar de paso la semivía de 0,85 m. Éxito: los dos bordes medidos en
   ≥ 90 % de la vuelta con incertidumbre ≤ 0,3 m. **Hoy el coche pasó el 16,7 % del tiempo fuera del
   pasillo comprobado sin pisar nunca fuera del asfalto (V33): el pasillo real es más ancho.**
7. **A3, segunda pista:** repetir A2 con otra pista y otra IA para saber si el factor de ritmo y
   las envolventes se generalizan. Requiere `circuito_virtual/pistas/<pista>/` con mapa y
   referencia suavizada.
8. **Rivales:** ver si el paquete de tiempos trae la posición de los rivales (hoy solo se lee al
   participante propio; el relay de memoria compartida del Telemetry Tool dice dar «posición y
   velocidad de otros coches»), antes de D5.
9. **Técnica de curva y PPO residual:** el teacher aún mantiene casi constante la velocidad en la
   curva; la técnica del manual (frenar fuerte, soltar de forma modulada, mínimo en el ápice,
   gas solo con la deriva y la guiñada dentro de límites) es el paso 4 de V17. El PPO va después y
   como corrección acotada sobre el teacher (V17); antes, revisar el estado de `ppo_guard`,
   `ppo_anchor` y `ppo_bootstrap`.

## Ideas y referencias (resumen; el detalle está en V16-V33)

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
