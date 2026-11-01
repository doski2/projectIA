# Plan A: límites del coche (profesor físico)

Contexto: sección 2 y 5 de [ESTUDIO_SIMULADOR_Y_LIMITES.md](ESTUDIO_SIMULADOR_Y_LIMITES.md).
Código: `experimental/identificacion/` · Estado: **A1.1 en código** · Depende de: C0 (log ampliado)

## Hipótesis

Con unos pocos parámetros (`μ`, `k`, `a_freno(v)`, `a_acel(v, marcha)`) se puede calcular el perfil
de velocidad
máxima de cualquier pista y predecir tiempos de vuelta con error < 3 %.

## Pasos

| #   | Paso                                                                                                                                                                                 | Éxito si…                              | Estado                                                                                                                           |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| A0  | Analizar los logs actuales                                                                                                                                                           | Hecho: solo cubren ≤ 0,7 g y ≤ 61 km/h | Hecho                                                                                                                            |
| A1  | Sesiones de identificación (dejar rodar, frenadas, aceleraciones, círculos, barridos), por fases: A1.1 rodar + aceleración, A1.2 frenadas, A1.3 arcos, A1.4 barridos (fuera hasta B) | Curvas `a(v)` limpias                  | En curso: A1.1 hecho con datos limpios de 0 a 120 km/h (H47-H50); A1.2 hecho (H51); A1.3 hecha (H53-H56): cota inferior del límite lateral ≥ 14,6 m/s² (D21) |
| A2  | Ajustar el perfil y predecir tiempos de vueltas conocidas                                                                                                                            | Error < 3 %                            | En curso: A2.1 hecho (H57), falta A2.0 (D22) |
| A3  | Validar en una segunda pista                                                                                                                                                         | Mismos parámetros, mismo error         | Pendiente                                                                                                                        |
| A4  | Usar el perfil como objetivo del profesor                                                                                                                                            | Vuelta limpia a mayor ritmo            | Pendiente                                                                                                                        |

## Riesgos a vigilar

Agarre variable (neumáticos, combustible, clima), reglaje, dificultad de llegar al límite con mando
virtual.
Ver sección 2.4 del estudio.

## La lluvia como variable (D13)

Con «Clima real» habrá sesiones con lluvia. Para A no son datos a descartar: el agarre máximo
depende de la humedad
y la pérdida con neumáticos de seco es parte de lo que se quiere medir. Condiciones:

- Ajustar los parámetros (`μ`, `k`, `a_freno(v)`, `a_acel(v, marcha)`) **por nivel de lluvia**, no

  con una mezcla.

- El UDP da la densidad de lluvia, no la humedad de la pista: usar una lluvia acumulada reciente y

  comprobarla
  contra el agarre medido en las curvas.

- Las sesiones de identificación (A1) se hacen **primero en seco** para tener una referencia limpia.

## Diseño de A1.3: arcos con velocidad creciente (aprobado por el usuario el 2026-10-31; código en X22)

Es la fase que más puede salirse: se busca el límite lateral del coche. Se lanza con el usuario
delante del juego, en seco, en bloques de 3-4 vueltas, y solo después de confirmarlo (decisión del
usuario 2026-10-31).

- **Zona:** las curvas de 228-600 m de Sugo (radios ≈ 51-55 m, H52), entradas desde la recta de

  3113-3784 m (670 m). El teacher las toma a 60 km/h con 7 m/s² laterales y a 80 km/h con 11-13 (≈
  1,3 g), así que el límite está cerca.

- **Mecanismo:** una consigna de velocidad local. Dentro de la ventana [3200 m → 600 m] se sustituye

  la consigna del teacher por la velocidad de la pasada y se desactiva su límite lateral; el teacher
  conserva el volante, la línea y su PI de velocidad. No se imponen pedales (a diferencia de
  A1.1/A1.2). Cambio mínimo en `learn_driver.py` (`--ident arco`, `--ident-arc-speeds`).

- **Rampa:** 80, 85, 90, 95, 100, 105, 110 km/h, una pasada por vuelta (≈ 3:35 a banda 60). Techo

  110, por debajo de los 115 de H50: en 2ª el motor se acerca al corte de encendido a 120. Cada
  pasada solo se lanza si la anterior fue limpia. La primera que dispara un criterio de corte da el
  límite, y la sesión se cierra tras el aterrizaje. Para retomar: `--ident-arc-speeds` con la lista
  que falte.

- **Criterios de corte (cualquiera):** |CTE| > 2,5 m (la rutina llega a 1,5, H52); rueda fuera del

  asfalto (`off_surface`/`off_track`); error de rumbo > 0,30 rad (el casi trompo de H50 llegó a
  0,35); `safety_override` o `cte_takeover` del teacher; evento de daño con `stop`
  (`--stop-on-damage`).

- **Aterrizaje suave:** al cortar, la consigna baja 6 km/h por segundo hasta la banda, manteniendo

  desactivado el límite lateral para que el teacher no frene a fondo con el volante girado (lo que
  casi hizo trompear el coche en H50). No hay freno de emergencia automático.

- **Medidas (`analisis_a1.py`):** lateral del eje 0 de `local_accel` (p95 y máximo por pasada),

  velocidad en curva, CTE, volante y rumbo máximos, temperaturas y desgaste de neumáticos por pasada
  (el agarre cambia con ellos), y el ajuste de lateral frente a v² para ver dónde deja de crecer.

- **Riesgos:** (1) salirse y golpear: el corte por CTE llega a 2,5 m del eje, no es un seguro contra

  el muro; (2) el agarre cambia a lo largo de las 7 vueltas (neumáticos que se calientan y se
  gastan); (3) el volante del teacher no está validado por encima de 80 km/h en curva; (4) a ≈
  90-100 km/h el coche puede estar ya en el límite y no avisar.

- **Por decidir:** velocidad de partida (80) y paso (5); techo (110); umbral de CTE (2,5); si se

  prefiere una primera tanda 80-90 y revisar antes de seguir.

## Resultado de A1.3 (2026-11-01, H53-H56, D21)

- **Referencia validada:** el coche aguanta ≥ 14,6 m/s² (≈ 1,49 g) laterales en seco con control, a 85 km/h en las curvas de 228-600 m de Sugo GP (p95 13,4 m/s² a 85, 12,05 a 80). El lateral crece con v² y no se aplanó: el techo real no está medido.
- **Por qué se para en 85 km/h:** a 90 el corte salta por el CTE (2,54 m) con el lateral aún en 12,8 m/s², igual que a 85 en ese punto. Es el seguimiento de la línea del teacher, no el agarre. El corte de 2,5 m coincide con el refuerzo de ganancia del volante (×2,25), que provocó un bandazo.
- **De qué dependerá el límite (dicho por el usuario):** presión de los neumáticos, ajustes de suspensión y técnica de conducción (mantener acelerador en el vértice o dejar rodar). Cada cambio de estos reabre la cota.
- **Para medir el techo real (más adelante):** volante con anticipación por curvatura, o una línea más ancha o más rápida.

## Diseño de A2: perfil de velocidad y predicción de vueltas (aprobado por el usuario el 2026-11-01, D22)

No necesita el juego para ajustar y probar el perfil, pero sí para conseguir los datos que le faltan (ver «Lo que falta»). Código nuevo solo en `experimental/identificacion/` (`perfil_velocidad.py`, `analisis_a2.py`), sin tocar `PCARS2-AI/src`.

- **Modelo:** el perfil clásico de adelante y atrás sobre la línea de referencia de Sugo (`sugo_ai.json`, curvatura `κ(d)` y altura por metro). (1) Límite lateral `v_lat(d) = sqrt(a_lat / |κ(d)|)` con `a_lat = μ + k·v²` (D21: `μ` ≥ 14,6 m/s² como punto de partida, `k` sin medir). (2) Pasada hacia delante con `a_acel(v, marcha)` de A1.1 más la pendiente (`g · grade`, ya en llano en las tablas). (3) Pasada hacia atrás con `a_freno(v)` de A1.2. (4) Tiempo de vuelta `Σ Δd / v`.
- **Éxito (estudio, A2):** error de tiempo de vuelta < 3 % y perfil de velocidad correlado con el real; descarte si > 10 %.
- **A2.1, con los logs que ya hay, sin jugar:** comprobar solo el tramo longitudinal. Con las vueltas de A1 (la recta de 3113 m acelerando de 60 a 80-90 km/h y la frenada de vuelta a 60 al llegar a 600 m) predecir la velocidad por metro y comparar. Es una prueba del solver, no de la hipótesis: el teacher nunca pasó de 90 km/h en curva, así que el límite lateral casi no actúa.
- **Lo que falta (hallazgo al preparar A2):** (1) **no hay ninguna vuelta a ritmo real**: la más rápida es de 165 s (teacher a 80 km/h) y la referencia `sugo_ai.json` son vueltas de 214 s; a 60-90 km/h ni el motor, ni los frenos, ni el agarre llegan al límite, así que predecir esas vueltas solo mide la regla de velocidad del teacher. (2) **`a_acel(v, marcha)` solo existe hasta 120 km/h en 1ª y 2ª** (el AutoShifter del teacher llega a 2ª, H50), y una vuelta rápida de un monoplaza pasa de 150 km/h en 3ª-5ª. (3) El agarre de un monoplaza crece con la velocidad (alerones): con los puntos de A1.3 (80-85 km/h) no se puede separar `k` de `μ`.
- **A2.0, datos de ritmo real (revisado por D22):** el usuario no grabará vueltas; **el agente rueda a ritmo creciente guiado por el perfil del modelo** (el teacher en modo físico, con la consigna de velocidad y el límite lateral que da el solver) y se compara el tiempo y el perfil de velocidad predichos con los medidos. Sirve para tres cosas: (a) `a_acel(v, marcha)` en marchas altas; (b) ajustar `μ` y `k` con la velocidad real en las curvas; (c) validar con vueltas apartadas del ajuste. **Bloqueos, que tocan código de producción y piden visto bueno (excepción a D2):** el AutoShifter solo llega a 2ª y el volante del teacher abre el CTE por encima de 85 km/h (H56).
- **Cómo se interpreta el resultado:** como `μ` de D21 es una cota inferior, el perfil con ese valor predice vueltas más lentas que las reales. Si el usuario pasa por las curvas a más de 14,6 m/s² laterales, la cota sube (se reabre D21 con un valor medido con control). Un error de más del 3 % sin explicación apunta a efectos que no están en el modelo (temperatura de neumáticos, combustible, bordillos, cambios de marcha).
- **Fuera de A2:** A3 (segunda pista) y A4 (perfil como objetivo del teacher).
- **Estado (2026-11-01):** diseño aprobado (D22). A2.1 hecho (H57). Falta A2.0 (bloqueos de arriba).

## Diseño del volante con anticipación por velocidad (A2.0-a; aprobado por el usuario el 2026-11-01; código en X23)

Es un cambio en `PCARS2-AI/src/teacher_controller.py` (código de producción: excepción a D2, X23 si se aprueba). Nace de H58 y es el primer bloqueo de D22.

- **Qué cambia:** en la rama de conducción normal de `compute_steering`, la anticipación `k_curvature · curv + k_lookahead · curv_ahead` se multiplica por `f(v) = 1 + g · max(0, v² − v0²)` (v en m/s). `TeacherConfig` gana `ff_speed_gain` (g, **0 por defecto: el comportamiento de producción no cambia**) y `ff_speed_v0_kmh` (v0 = 60). Con g = 0 o v ≤ v0 el factor es 1 y la salida es idéntica a la de hoy.
- **Valor de partida:** g = 0,003 (m/s)⁻²: factor 1,00 a 60 km/h, 1,65 a 80, 1,84 a 85 y 2,04 a 90 (H58 pide ≈ 3 veces más a 85; se deja la realimentación del CTE como red de seguridad y se sube por escalones). Se afina midiendo, no a ojo.
- **Activación:** `learn_driver.py --steer-ff-gain G` (por defecto 0) y paso en `aislado.py`. Solo las sesiones que lo pidan lo usan; las de producción y las del bucle del BC no.
- **Lo que no se toca:** el refuerzo ×2,25 de la ganancia del CTE a 2,5 m (`LATERAL_WARN_M`) es una red de recuperación y se queda; el amortiguador del volante del BC (`damp_bc_steering`, P25) tampoco.
- **Tests:** (1) con g = 0 la salida coincide con la actual en una batería de estados; (2) con g > 0 y v ≤ v0 también; (3) el factor crece con v² por encima de v0; (4) el signo y el límite [−1, 1] se respetan.
- **Validación en el juego (con el usuario delante):** la misma rampa de arcos de A1.3 (80, 85, 90 km/h, `--steer-ff-gain 0.003`) y comparar con H55-H56. **Éxito si** |CTE| máx. a 85 km/h baja de 2,5 a ≤ 1,2 m y a 90 y 95 no hay corte por CTE; **descarte/ajuste si** aparece oscilación del volante (el factor es de lazo abierto sobre κ de la línea, no de la medida) o el CTE cambia de signo en las salidas.
- **Riesgo:** una anticipación grande mete el coche hacia dentro (CTE de signo contrario) en curvas cortas o de radio variable (las eses de 1450-1500 m). Por eso se sube de 0,003 en pasos.
- **Después:** las marchas por encima de 2ª (segundo bloqueo de D22) y el agarre a más velocidad (`k`), con los datos de A2.0.

## Diseño de las marchas por encima de 2ª (A2.0-b; aprobado por el usuario el 2026-11-01; código en X24)

Segundo bloqueo de D22. Cambia `PCARS2-AI/src/auto_shift.py` y `pcars2_gear.py` (código de producción: excepción a D2, X24 si se aprueba). Sin el cambio no se puede medir `a_acel` por encima de 120 km/h ni rodar a ritmo real.

- **Qué pasa hoy (H50):** el cambio sube con RB cuando `rpm / max_rpm > 0,87` y la marcha es menor que `TEACHING_MAX_GEAR` (2); `should_downshift_toward_first` baja con LB cualquier marcha mayor que ese tope. A ≈ 120 km/h en 2ª el motor llega al corte (7442 rpm) y el UDP marca `gear` 1 (fallo): el cambio pulsa RB, entra 3ª, el tope la baja con LB, pasa por punto muerto y vuelve a 2ª, en bucle.
- **Qué cambia:** (1) `AutoShifter` y las funciones de `pcars2_gear.py` reciben `max_gear` (por defecto `TEACHING_MAX_GEAR`, **producción idéntica**) en vez de leer la constante; (2) `learn_driver.py --max-gear N` y `aislado.py --max-gear N` lo fijan; (3) si el UDP marca `gear` 1 con velocidad de avance (> 8 m/s) y la última marcha engranada fue ≥ 2, se trata como esa marcha y no se pulsa nada (el fallo del corte de H50); (4) se registra el cambio en el log (`shift` ya sale) para medir la pausa en `gear` 0 de cada subida.
- **Lo que no cambia en esta fase:** la bajada sigue siendo bajo freno con `rpm / max_rpm < 0,40` (`DOWNSHIFT_RPM_RATIO`); no hay reducción por gas (kick-down). Con 3ª a 88 km/h el régimen es ≈ 0,5, así que tras frenar para una curva el coche saldrá en 3ª: la tabla `a_acel(v)` de A2 se mide con esta política y ya la incluye.
- **Escalones de validación en el juego (con el usuario delante, en seco):** G1 `acel` con `--max-gear 3` y techo 135 km/h en la recta de 3113 m (`--ident-straights 1`, 2 pasadas): éxito si hay un solo cambio 2ª → 3ª sin bucle, el `gear` 0 dura ≤ 0,3 s (la subida 1ª → 2ª dura ≈ 0,17 s) y el CTE se queda en ≤ 1 m; G2 techo 150 y 3ª con el corte; G3 `frenar` desde 130 y 150 (bajada, sobrerrevoluciones, distancia). Cada escalón se revisa antes del siguiente y se corta con Ctrl+C si el coche oscila.
- **Cambios de límites del código de A1:** `MAX_CAP_KMH` (115) pasa a depender de `max_gear` (por ejemplo 115 con 2, 150 con 3 y 170 con 4, subiendo solo tras validar el escalón anterior); con `--max-gear` 2 los límites de hoy no cambian.
- **Riesgos:** (1) el corte de encendido en 3ª (el motor llega a 7700 rpm; unos 175 km/h si la relación de 3ª es ≈ 44 rpm por km/h, sin medir); (2) la bajada de marcha bajo freno sin conocer las relaciones: se mide `rpm / velocidad` de cada marcha en G1-G3 antes de permitir bajadas a mayor velocidad; (3) el volante del teacher por encima de 120 km/h no está validado (H56 llega a 90); la anticipación X23 (`--steer-ff-gain`) se prueba en la recta; (4) la pausa de par durante el cambio frena el coche y puede mover el volante.
- **Después:** A2.0 completo (el teacher en modo físico con `lat_accel_limit` ≈ 12,5 y consigna del perfil), y el perfil de A2 con `a_acel(v)` hasta ≈ 150 km/h.

- **A1.3b, arcos en otras marchas (D23, a hacer tras G1-G3):** el usuario recuerda que entrar en la curva en 2ª, 3ª o 4ª cambia el freno motor y el par y con ello el límite lateral. Los arcos de A1.3 se midieron en 2ª. Con `--max-gear 3` y 4 se repiten la rampa de arcos y la comparación con H55-H59 (volante por unidad de curvatura, lateral por unidad de volante).

## Línea suavizada para alta velocidad (A2.0-c; diseño aprobado por el usuario el 2026-11-01; hecha, sin probar en el juego)

Parte de la observación del usuario y de H61. No cambia código de producción: archivo nuevo derivado y herramienta en `experimental/identificacion/`.

- **Qué hace:** `linea_suave.py` lee `sugo_ai.json` y escribe `circuito_virtual/pistas/sugo_gp/sugo_smooth.json` con las posiciones suavizadas (gaussiana σ = 15 m con el cierre de vuelta) **solo donde el trazado es recto** (|κ| de la versión de σ = 60 m < 0,003 y sin curvas reales como la de 904-965 m), con un empalme gradual de unos 30 m en los bordes de cada tramo y el resto de campos (velocidad, marcha, orientación) sin tocar. Imprime el desplazamiento máximo por tramo y la κ antes y después.
- **Uso:** `aislado.py --reference` (hoy fija `src/refs/sugo_ai.json`) pasa la referencia a `learn_driver.py --reference`, que ya existe. El teacher, la seguridad y los análisis la usan sin cambios; `perfil_velocidad.Track.from_reference(path)` ya admite otra ruta.
- **Tests:** (1) una recta con un quiebro sintético de 0,3 m queda con κ < 0,002; (2) una curva de radio 50 m no se toca; (3) el desplazamiento máximo es ≤ 1 m; (4) la longitud de vuelta y el número de puntos no cambian.
- **Validación en el juego (con el usuario delante):** G1 otra vez, con `--reference` la línea suavizada y `--max-gear 3 --ident-cap-kmh 135`: éxito si la maniobra llega a 135 km/h sin corte por CTE en 3300-3345 m y el volante se queda en ±0,05 en la recta. Si no basta, `--steer-ff-gain` (X23) sube y, en segundo lugar, el corte de CTE de la maniobra a 1,5 m solo en rectas (parámetro nuevo, no de producción).
- **Límites:** (1) el CTE de las pasadas medido contra la línea suavizada no es comparable con H55-H60; (2) la cota lateral de D21 no cambia; (3) la línea más rápida en curva (radio mayor, apex) queda para B o para después de A2.
- **Resultado (2026-11-01):** `circuito_virtual/src/linea_suave.py` genera `circuito_virtual/pistas/sugo_gp/sugo_smooth.json` (carpeta no versionada: se regenera con el script). 7 tramos suavizados, desplazamiento máximo **0,73 m**; el quiebro de 3300 m baja de |κ| 0,0068 a 0,0015 con 0,54 m en su tramo (3123-3565 m); la curva de 904-965 m queda como estaba (< 1 cm). `aislado.py --reference` pasa la línea a `learn_driver.py`. 7 tests nuevos (78 en `experimental`). El `ori` de cada punto no se toca (solo lo usa la marcha atrás).
