# Estudio: límites del coche y simulador aprendido

> **Estado (2026-10-26): investigación y debate, nada implementado.** Tres ideas (A, B y C) para atacar
> el cuello de botella del proyecto: el juego corre a tiempo real (~58 pasos/s) y hay pocas horas disponibles.
> Las cifras de "Lo que hay hoy" están medidas en este repositorio; el resto son hipótesis a
> comprobar, y cada una trae un experimento con criterio de éxito o descarte.

---

## 0. Por qué estas tres ideas

| Cuello de botella | Idea | Qué sustituye |
| --- | --- | --- |
| El profesor sube la velocidad por bandas artificiales (20 → 80 km/h) y el BC solo vio hasta 60 | **A. Límites del coche** → perfil de velocidad físico | Las bandas y el objetivo de velocidad fijo |
| 1 millón de pasos de PPO = ~5 h de juego real, y la mayoría de RL necesita muchos más | **B. Simulador aprendido** | Entrenar solo contra el juego |
| No hay datos a más de ~60 km/h, y el BC no sabe conducir ahí | **C. Rampa continua de velocidad del BC** | La escalera L1→L7 por bandas y la subida por tiempo |

Las tres comparten una necesidad: **datos del coche a más ritmo**, que hoy no existen (ver 1.2).
A alimenta a B (un modelo físico de partida hace que el simulador necesite menos datos) y **C es la
forma más barata de generar el primer lote de datos** para las dos, además de mejorar el BC directamente.
Junto con el PPO protegido que ya existe, son las tres vías abiertas del proyecto.

---

## 1. Lo que hay hoy (medido el 2026-10-26)

### 1.1 Datos

- `logs/learning/*.jsonl`: 87 sesiones, **9,05 millones de ticks** a ~60 Hz, 5 GB. Los más recientes traen
  un bloque `vehicle` (volante aplicado por el juego, `yaw_rate`, `lat_accel`, `terrain`, `tyre_rps`);
  los antiguos no (aprox. un tercio de los ticks lo tiene).
- Cada tick: `speed_kmh`, `throttle`, `brake`, `steering`, `gear`, `rpm`, `lap_distance`, `cte`,
  `heading_err`, `signed_cte`, `teacher_reason`.
- Telemetría UDP: aceleración local `(long, vert, lat)` en m/s² (índices 0, 1, 2), velocidad angular,
  velocidad local, giro de las ruedas. El código usa el eje 2 como lateral y el 0 como longitudinal
  (`obs_universal.py`); **verificarlo contra una curva conocida antes de fiarse** (verificado en C0: es al revés, ver la corrección de 1.2).
- `data/archive/online_buffer_raw_*.jsonl` (unos 2,4 millones de filas, solo observación de 17 dim + acción)
  y `data/curated_buffer.npz`. Sirven para imitación, pero **no para simulador**: no traen el estado
  completo del coche.
- `src/steering_curve.py`: curva **estática** del volante, medida con 639 250 ticks a más de 25 km/h
  (retardo de 3 ticks compensado). Es la primera pieza de un modelo de planta ya medida.
- `src/refs/sugo_ai.json`: trayectoria de la IA con el limitador de box. Vale como **línea**, no como
  perfil de velocidad (59,9 km/h constantes, 1ª marcha).

### 1.2 Lo que cubren esos datos: poco ritmo

> **Corrección (2026-10-26, ver DECISIONES.md, H1):** el campo `lat_accel` de los logs es el eje 2 de `local_acceleration`, que resulta ser la aceleración **longitudinal**; la lateral es el eje 0. La tabla siguiente es, por tanto, de aceleración longitudinal. Para la lateral hay que usar `v · yaw_rate` (disponible en los logs con bloque `vehicle`). La conclusión general (poco ritmo, velocidad por debajo de ~61 km/h) se apoya en la velocidad y no cambia, pero hay que rehacer el rango de agarre lateral.

Muestreo de 1 de cada 6 ticks (1,5 millones):

| Velocidad | `|lat_accel|` p99 | `|lat_accel|` máx. |
| --- | --- | --- |
| 20-30 km/h | 6,9 m/s² (0,70 g) | 14,9 |
| 40-50 km/h | 6,1 m/s² (0,62 g) | 15,1 |
| 50-60 km/h | 5,2 m/s² (0,53 g) | 16,3 |
| 60-70 km/h | 4,8 m/s² (0,48 g) | 9,5 |

- Velocidad: mediana 22,8 km/h, p99 **61 km/h**, máx. 89 km/h (casos aislados).
- Gas por encima de 0,9: **0,0 %** de los ticks. El profesor nunca acelera a fondo.
- Freno por encima de 0,5: 12,1 % de los ticks, todos dentro del rango de hasta ~60 km/h.
- Los máximos por encima de 1,2 g a baja velocidad probablemente son golpes o trompos y no agarre (sin comprobar).

**Conclusión: con estos datos no se pueden medir los límites del coche.** Todo lo que hay está en el
régimen de conducción tranquila (≤ 0,7 g), muy por debajo de lo que un monoplaza con carga aerodinámica
aguanta. Hay que generar datos nuevos (secciones 4 y 5).

---

## 2. Idea A: extraer los límites del coche (profesor físico)

### 2.1 Qué es

Calcular, para cualquier pista, **la velocidad máxima posible en cada metro** a partir de su curvatura
y de unos pocos parámetros del coche, y usarla como objetivo del profesor en lugar de una banda fija.
Es el método clásico del problema de vuelta mínima con trayectoria fija:

1. **Límite lateral por curvatura:** `v_lim(d) = sqrt( a_lat_max(v) / |κ(d)| )`, con
   `a_lat_max(v) ≈ μ·g·(1 + k·v²)` (el término `k·v²` recoge la carga aerodinámica).
2. **Pasada hacia atrás (frenadas):** `v_i = min(v_i, sqrt(v_{i+1}² + 2·a_freno(v)·Δs))`.
3. **Pasada hacia delante (aceleraciones):** limitada por la potencia y la marcha, `a_acel(v, marcha)`.
4. **Círculo de fricción** cuando se combinan: `(a_lat/A_lat)² + (a_long/A_long)² ≤ 1`.
5. Tiempo de vuelta estimado: `Σ Δs / v_i`.

La curvatura ya la da `ReferenceLine.curvature(d)` (resolución de 1 m; habrá que suavizarla).
Como el límite solo depende de la curvatura, **sirve para cualquier pista** y ya encaja con la
observación universal.

### 2.2 Qué hay que medir (parámetros)

| Parámetro | Cómo medirlo | Estado |
| --- | --- | --- |
| `μ`, `k` (agarre lateral y carga aerodinámica) | Círculos a radio constante subiendo la velocidad hasta el subviraje | Sin datos |
| `a_freno(v)` | Frenada a fondo, recta, desde varias velocidades (40, 80, 120 km/h…) | Sin datos (freno solo a baja velocidad) |
| `a_acel(v, marcha)` | Gas a fondo en recta marcha a marcha | Sin datos (gas nunca > 0,9) |
| Resistencia al avance | Dejar rodar con gas 0 y freno 0 | Quizá medible con los logs actuales (tramos con gas 0 y freno 0); sin comprobar |
| Respuesta dinámica del volante | Barrido de frecuencia (chirp) a velocidad constante | Solo curva estática |

### 2.3 Experimentos, en orden

| # | Experimento | Éxito si… | Descarte si… |
| --- | --- | --- | --- |
| A0 | Analizar los logs actuales (hecho, sección 1.2) | Confirma el régimen cubierto | — |
| A1 | Sesiones de identificación con el mando virtual: círculos, frenadas y aceleraciones (scripts cortos con `DS4Controller`, ~20 min cada uno) | Curvas `a(v)` limpias con poca dispersión | El mando no permite llegar al límite (la cadena de pedales/volante lo impide) |
| A2 | Ajustar el perfil con esos parámetros y **predecir el tiempo de vuelta** de las mejores vueltas existentes (IA a ritmo real, o tuyas) | Error de tiempo < 3 % y perfil de velocidad correlado con el real | Error > 10 %: faltan efectos (pendiente de la pista, bordillos, temperatura) |
| A3 | Validar en una segunda pista | Mismo error con los mismos parámetros | Los parámetros no transfieren |
| A4 | Usar el perfil como objetivo del profesor y regenerar el dataset | Vuelta limpia a ritmo > actual | El BC no sigue el perfil sin salirse |

### 2.4 Riesgos

- El agarre depende de neumáticos (temperatura, presión, desgaste), combustible, pista y clima. Hoy el
  desgaste y el consumo están **desactivados** en el juego (`CONFIGURACION_JUEGO.md`), lo que ayuda; si
  se activan, los parámetros dejan de ser constantes.
- El reglaje del coche cambia los límites: cada reglaje requiere medirlo de nuevo.
- Conducir **en el límite** con un mando virtual es difícil (resolución del volante, retardo, curva no
  lineal). Los límites medidos pueden ser conservadores.
- La IA del juego no necesariamente conduce al límite; los foros indican que su dificultad varía por
  pista y coche. No tomarla como cota superior sin comprobarlo.
- Un perfil de vuelta mínima es una cota teórica: el tiempo real será peor (sobre todo con mando).

---

## 3. Idea B: simulador aprendido (RL basado en modelo)

### 3.1 Qué es

Entrenar una red `f(estado, acción) → estado siguiente` con la telemetría del propio coche y dejar que
el agente practique dentro de ella a la velocidad de la CPU (cientos o miles de pasos por segundo, frente
a ~58 del juego). El juego real se usa para recoger datos y **validar**, no para todo el entrenamiento.

### 3.2 Diseño propuesto: aprender solo lo que no se sabe

Separar el problema en dos para que lo aprendido sea pequeño y no dependa de la pista:

- **Parte aprendida (dinámica del coche en ejes del propio coche):**
  estado `(v_long, v_lat, yaw_rate, volante real, rpm, marcha, [acel])` y acción `(gas, freno, volante)`
  → estado siguiente. Esta parte **no depende de la pista**, así que generaliza entre circuitos.
- **Parte exacta (cinemática):** integrar la posición y el rumbo con el estado, y calcular `CTE`,
  `heading_err`, curvatura y velocidad futura con las funciones que ya existen en `ReferenceLine`
  y `build_obs_universal`. Se construye la observación como en el juego.
- Primer escalón sencillo: un modelo de bicicleta con parámetros ajustados (conecta con la Idea A);
  después, una red que aprenda el **residuo** de ese modelo.

### 3.3 Qué hace falta

- **Datos del estado completo en secuencia.** Los tick logs más recientes traen `yaw_rate`,
  `lat_accel`, `game_steer`, `game_throttle`, `game_brake`, `terrain` y `tyre_rps`, pero **ni
  siquiera ellos guardan la velocidad lateral ni la aceleración longitudinal**, que la telemetría sí
  da. Lo más probable es que haya que ampliar el log de cada tick antes de B1.
- **Datos que visiten situaciones variadas**, incluidas las malas (trompos, salidas, frenadas
  fuertes). Un modelo entrenado solo con conducción limpia es inútil para entrenar recuperaciones.
- **Retardo y planta del mando:** ya se compensa el volante con una curva estática; el modelo debe
  incluir el retardo de ~3 ticks y el efecto de `HoldBrake` entre actualizaciones (no es dinámica del coche).

### 3.4 Experimentos con puertas de decisión

| # | Experimento | Pasa si… | Si falla |
| --- | --- | --- | --- |
| B0 | Revisar los logs: ¿hay estado suficiente y en qué proporción? | Hay > 1 millón de ticks con estado completo | Ampliar el log y recoger más sesiones |
| B1 | Modelo de **un paso** (red pequeña) y error de predicción en validación | Error de `v_long` y `yaw_rate` por debajo de la resolución de la telemetría | Revisar variables, retardo, unidades |
| B2 | **Rollouts largos** (1-2 s): predecir 60-120 pasos encadenados y comparar con la realidad | Posición lateral con error < 0,5 m a 2 s y sin deriva creciente | Modelo híbrido (residuo sobre bicicleta) o horizonte corto |
| B3 | Entrenar una política **en el simulador** y probarla en el juego | Conduce vueltas limpias con poco o ningún ajuste en el juego | Explotación de errores del modelo: añadir conjunto de modelos y penalizar la incertidumbre |
| B4 | Ciclo: simulador → juego → más datos → simulador | El rendimiento en el juego mejora por iteración con pocas horas de juego | El coste de mantener el modelo supera la ventaja |

### 3.5 Riesgos

- **Explotación del modelo:** la política aprende a aprovechar errores del simulador que el juego no
  reproduce. Mitigación: conjuntos de modelos, horizontes cortos y validación continua en el juego.
- **Cobertura:** fuera de los estados vistos el modelo inventa. Los datos de hoy llegan a ~60 km/h;
  entrenar por encima requiere datos por encima (relación con A y con regrabar la IA).
- **Coste de desarrollo:** es la idea más grande y más investigativa de las dos. No hacerla antes de
  tener B0-B2 resueltos y la Idea A al menos en A1-A2.
- Un pasatiempo con pocas horas debe elegir una sola: **A es más barata y da frutos antes**.

---

## 4. Idea C: rampa continua de velocidad del BC (propuesta para debatir)

> Propuesta del 2026-10-26: empezar el aprendizaje del BC a 60 km/h, **sin límite de vueltas**, y subir
> 5 km/h cada 5 o 10 vueltas, como experimento para ver hasta dónde llega y de paso generar datos para
> el simulador y para medir la física. Todavía hay que estudiarla y debatirla (4.6).

### 4.1 Qué es

Usar el aprendizaje en pista que ya existe (`learn_driver`: el BC conduce, el profesor corrige y el BC se
ajusta entre vueltas) pero con **una sola etapa continua** en lugar de la escalera L1→L7 por banda, y con
una **puerta** para subir la velocidad objetivo solo cuando las vueltas salen limpias. Es la misma lógica
de `SpeedGate` (en `ppo_guard.py`, reglas puras sin SB3) llevada a vueltas en lugar de episodios.

### 4.2 Qué mide y qué no (cuenta con el profesor actual)

La regla del profesor limita la velocidad en curva de forma proporcional al objetivo
(`velocidad en curva = objetivo × max(0,4, 1 − 12·|curvatura|)`, en `teacher_controller.py`).
Con la curvatura de Sugo, la aceleración lateral implícita en las curvas más cerradas sería:

| Objetivo | Velocidad mínima en curva | Aceleración lateral implícita (máx.) |
| --- | --- | --- |
| 60 km/h | 33 km/h | 0,38 g |
| 80 km/h | 44 km/h | 0,68 g |
| 100 km/h | 55 km/h | 1,06 g |

(Calculado el 2026-10-26 sobre `sugo_ai.json`. La rama de la regla que usa la velocidad de la
referencia no se activa hoy, porque esa referencia es plana.)

- Con el techo actual del currículo (80 km/h) los datos llegarían a ~0,7 g: aún lejos del límite de un
  monoplaza. Para acercarse a ~1 g hace falta un objetivo de ~100 km/h.
- Lo que obtendrías es **el estilo del profesor a más velocidad, no el límite del coche**. Aun así aporta:
  datos por encima de 60 km/h, un BC que sabe conducir ahí (lo necesitan también el PPO y el simulador) y
  **el punto donde se rompe el propio profesor** (overrides, CTE altos, salidas), que es un dato real.
- Los límites verdaderos siguen pidiendo las sesiones de identificación de la sección 5.

### 4.3 Diseño propuesto (a debatir)

- **Ciclo tipo F1 (acordado el 2026-10-26):** vuelta de salida desde parado (no puntúa) → **2 vueltas
  lanzadas** con el modelo congelado (las que juzga la puerta) → parada en meta y ajuste fino → nuevo ciclo.
  Así la puerta solo evalúa vueltas lanzadas de un mismo modelo y la recta de meta se recorre lanzado, que
  es donde se alcanza la velocidad máxima. La vuelta de salida no se tira: sus datos (aceleración desde
  parado) van al log y sirven para la Idea A. Hoy `learn_driver` para en meta en **cada** vuelta
  (`--learn-every 1` por defecto, freno de `LapTransitionGuard` durante el ajuste).
- **Puerta por ciclos:** **2 ciclos limpios seguidos** (4 vueltas lanzadas y dos ajustes) → +paso; un ciclo
  con fallos → se repite el ciclo a la misma velocidad (el ajuste ya se ha hecho); **3 ciclos seguidos sin
  limpiar** → bajar un paso o parada de seguridad. Estado de la velocidad alcanzada guardado en disco para
  retomar (como `estado_gate.json`).
- **Qué falta en el código:** `--learn-every 3` ya da la parada cada 3 vueltas; falta que la vuelta de
  salida no cuente en la racha de `learn_progress` (hoy cuenta todas) y la lógica de la puerta por ciclos.
- **Parámetros:** vueltas lanzadas por ciclo (2), ciclos para subir (2), paso (5 km/h; 2,5 es más fino),
  techo (80 del currículo frente a ~100-110).
- **Log ampliado por tick, antes de lanzarla:** velocidad lateral, aceleración longitudinal y velocidad
  local. Hoy ni los logs recientes lo guardan, y es lo que necesita B. Sin esto, la tanda de datos se
  desaprovecha para el simulador.
- **Qué entrena el BC:** hoy el buffer se filtra por etapa y banda exacta, y en una rampa continua eso no
  sirve. Con una sola red y el objetivo de velocidad como entrada, lo coherente es entrenar con **todas
  las velocidades vistas, equilibradas** (puntos 3 y 4 de `AUDITORIA_CODIGO.md`, 8.3, todavía pendientes).
- **Perturbaciones controladas** (opcional, más adelante): ruido suave en tramos seguros para que el
  simulador vea algo más que conducción limpia.
- **Tiempo (estimaciones):** una vuelta ~3,5 min más la pausa del ajuste. Con el ciclo tipo F1 (3 vueltas,
  ~10,5 min más el ajuste) y 2 ciclos por escalón, ~21 min por +5 km/h: de 60 a 100, 8 escalones ≈ 3 h
  como mínimo, más los ciclos repetidos.

### 4.4 Experimentos

| # | Experimento | Éxito si… | Si falla |
| --- | --- | --- | --- |
| C0 | Ampliar el log por tick y verificar que las columnas nuevas salen con valores coherentes (un par de vueltas) | Se registran y los ejes cuadran con una curva conocida | Corregir antes de gastar horas |
| C1 | Rampa 60 → 80 km/h con puerta, N = 5 | Llega a 80 con vueltas limpias, o **registra con claridad el escalón donde se rompe** | Si se rompe pronto, analizar si es el profesor, el BC o la compensación del volante |
| C2 | Subir el techo a ~100-110 | Los datos cubren hasta ~1 g de aceleración lateral implícita | El coche no aguanta lo que pide el profesor: recortar el techo y anotar el límite observado |
| C3 | Analizar los datos nuevos: aceleración lateral y longitudinal frente a velocidad, error del BC frente al profesor por velocidad | Salen curvas útiles para A1 y para B0 | Faltan variables: ampliar el log |
| C4 | Re-destilar el BC nuevo a PPO (`ppo_bootstrap.py`) y repetir la noche protegida | El PPO parte de un conductor que sabe 65-100 km/h | — |

El resultado del experimento no es solo llegar arriba: es **saber dónde está el escalón de rotura y tener
los datos hasta ahí**.

### 4.5 Riesgos

- Mide el estilo del profesor (suave, sin gas a fondo ni frenadas límite), no el límite del coche.
- Los datos serán muy parecidos entre sí; hay que curarlos (dedupe, límite de `maintain_speed`).
- **El BC puede olvidar las velocidades bajas** si solo ve la banda actual (riesgo ya señalado en `AUDITORIA_CODIGO.md`, 8.2; no medido).
- A velocidades altas, golpes y salidas son más probables; con una sesión larga sin vigilancia hay que
  conservar las paradas de seguridad actuales (`StuckOffTrackAbort`, guardias de CTE).
- El objetivo de velocidad es el del profesor, no la velocidad óptima: subirlo no asegura mejores tiempos.
- Cambia la estructura del aprendizaje en pista que hoy funciona (L1→L7, `learn_progress`): riesgo de
  romper algo que va bien. Conviene hacerlo como modo aparte y no sustituir el actual.

### 4.6 Preguntas para debatir

- ¿5 o 10 vueltas por escalón? ¿Paso de 5 o de 2,5 km/h?
- ¿Techo en 80 (el del currículo) o en ~100-110 para llegar a ~1 g?
- ¿Qué cuenta como vuelta limpia a alta velocidad? ¿Los mismos umbrales de CTE y overrides, o más holgados?
- ¿Antes de la rampa conviene hacer las sesiones de identificación (frenadas, círculos), para fijar el
  techo con el límite real y no a ciegas?
- ¿Se hace de día con la sesión vigilada, o de noche con puerta y parada automática, como el PPO protegido?
- ¿Se sustituye la escalera de bandas o se mantiene como modo alternativo?

---

## 5. Datos a generar (comunes a A, B y C)

Cada una es una sesión corta y automatizable con el controlador actual, sin necesidad de conducir:

1. **Dejar rodar:** a varias velocidades, gas 0 y freno 0, 10 s (resistencia al avance).
2. **Frenadas a fondo:** desde 40, 60, 80, 100, 120 km/h en recta, 5 repeticiones.
3. **Aceleraciones a fondo:** desde parado, marcha a marcha, recta larga.
4. **Círculos:** a radio constante (curva larga o rotonda de la pista), velocidad creciente hasta el subviraje.
5. **Barridos de volante:** senoidal de frecuencia creciente a velocidad constante (para la dinámica del volante).
6. **Vueltas rápidas:** IA al 100 % grabada con el espectador y, si se puede, tus mejores vueltas.
   (Sirven también para validar A2 y alimentar B.)
7. **Ruido controlado:** entradas aleatorias suaves en tramos seguros, para que el simulador vea más
   que la conducción limpia.

Registrar siempre: estado completo del coche por tick, el comando enviado y el volante aplicado por el
juego, reglaje y condiciones (clima, temperatura) en la cabecera de la sesión.

### 5.1 Qué campos de la API registrar (revisado el 2026-10-26)

El log por tick de hoy (`record_tick` + `vehicle_diag` en `session_log.py`) guarda velocidad escalar,
`lap_distance`, CTE, comandos, marcha, rpm, volante/gas/freno aplicados, `yaw_rate`, `lat_accel`,
`terrain` y `tyre_rps`. Del paquete 0 se **parsean pero no se registran**, y hacen falta para A y B:

| Campo (`TelemetryFrame`) | Para qué | Idea |
| --- | --- | --- |
| `local_velocity` (3) | `v_long`, `v_lat` y ángulo de deriva: estado básico del simulador | B |
| `local_acceleration` long y vert | `a_freno(v)`, `a_acel(v, marcha)`, carga vertical | A, B |
| `angular_velocity` roll y pitch | Transferencia de carga, saltos y bordillos | B |
| `position`, `orientation` | Integrar y validar la cinemática; pendiente de la pista | B, A2 |
| `ride_height`, `suspension_travel` (4) | Efecto de la carga aerodinámica (`k·v²`) | A |
| `tyre_temp`, `tyre_tread_temp` (4) | Agarre según temperatura (riesgo 2.4) | A |
| `fuel_level`, `brake_bias`, `aero_damage` | Condiciones que cambian los parámetros | A, B |
| `raw_throttle`, `raw_brake` | Separar la planta del mando de la del coche | B |

Del paquete 0 **sin parsear** (offsets en `pcars2_udp_data_reference.md`): `sTyreFlags` (rueda en el
suelo), `sTyreHeightAboveGround`, `sSuspensionVelocity`, `sAirPressure`, `sBrakeTempCelsius`,
`sEngineTorque`, `sCrashState`. Los más útiles: contacto de ruedas y par motor (A3 de aceleración).
El paquete 4 (`sGameStateData`: temperatura de pista y ambiente, lluvia, viento) tampoco se parsea; basta
con guardarlo en la cabecera de la sesión.

Otros dos detalles: `t_s` es el reloj del PC, no un contador de la física, y `lap_distance` del UDP es un
entero en metros. Para el simulador conviene registrar el número de tick de física (o el tiempo del juego)
para medir bien `Δt`.

**Shared memory de PCARS2 (y AMS2):** además del UDP, PCARS2 publica una memoria compartida en Windows
(misma máquina, que es nuestro caso) con los mismos datos en `float` y por fotograma del juego, con
número de secuencia; por ejemplo, la distancia en vuelta en `float` y no en metros enteros.
Automobilista 2 usa el mismo motor (Madness) y expone el mismo formato de UDP y de shared memory, pero
**solo da datos cuando el juego que corre es AMS2**: no saca nada extra de PCARS2. Sería una vía si algún
día se portara el proyecto a AMS2 (el parser serviría casi tal cual). Qué campos añade AMS2 sobre PCARS2:
sin comprobar.

---

## 6. Relación entre las ideas y orden recomendado

```
C: rampa del BC (log ampliado) ──► datos a más velocidad ─┬──► BC nuevo ──► PPO (noche protegida)
                                                          ├──► A1-A2 (analizar aceleraciones)
                                                          └──► B0 (datos para el simulador)
Sesiones de identificación (sección 5)
        │
        ├──► A: parámetros del coche ──► perfil de velocidad físico ──► profesor nuevo ──► BC ──► PPO
        │                 │
        │                 └──► prior físico para B
        └──► B: simulador aprendido ──► entrenamiento rápido de la política
```

Orden sugerido por rentabilidad con poco tiempo:

1. **C0** (ampliar el log) y **C1** (rampa del BC): es lo más barato y genera datos para todo lo demás.
2. Regrabar la IA a ritmo real y generar las sesiones de identificación (sección 5).
3. A1 → A2: medir parámetros y predecir tiempos de vueltas conocidas. Es la prueba de fuego.
4. C4: re-destilar el BC nuevo y repetir la noche protegida de PPO.
5. A4: profesor con perfil físico y BC nuevo.
6. B0 → B2 en paralelo con lo anterior solo si A2 sale bien; B3 y B4 después.

(Es una propuesta de orden: la Idea C todavía se está debatiendo, ver 4.6.)

---

## 7. Preguntas abiertas

- ¿Qué parte del límite se puede alcanzar de verdad con un mando virtual? ¿Se necesita un mapeo de
  volante distinto a altas velocidades?
- ¿Cómo de bien describe la dinámica de este coche un modelo de bicicleta con carga aerodinámica? ¿Hace
  falta transferencia de carga o un modelo de neumático?
- ¿Se puede reconstruir la velocidad lateral y la aceleración longitudinal de los logs antiguos?
- ¿Los parámetros del coche son estables entre sesiones (temperatura de neumáticos, combustible)?
- ¿La dificultad "máxima" de la IA alcanza el límite del coche, o está por debajo?

---

## 8. Lectura sugerida

Títulos de memoria; **verificar autores y años antes de citar**.

- Problema de vuelta mínima con perfil de velocidad hacia delante/atrás y círculo de fricción:
  trabajos de control de coches de carreras (p. ej. los de Kapania y Gerdes sobre trayectorias y
  perfiles de velocidad).
- RL basado en modelo con conjuntos: *PETS* (Chua et al., 2018) y *MBPO* (Janner et al., 2019).
- Simuladores aprendidos y planificación en el espacio latente: la familia *Dreamer* (Hafner et al.).
- RL residual sobre un controlador clásico: Johannink et al., 2019.
- Carreras con RL en videojuegos: *Gran Turismo Sophy* (Wurman et al., *Nature*, 2022) y el proyecto
  de código abierto TMRL para Trackmania (github.com/trackmania-rl/tmrl).

---

## 9. Resumen de una línea

**Antes de entrenar más, generar datos a más ritmo y medir el coche:** la Idea C (rampa del BC con puerta y
log ampliado) es el primer paso barato y alimenta a las demás; la Idea A convierte unas pocas sesiones de
identificación en un profesor con ritmo real para cualquier pista; la Idea B, más ambiciosa, convierte
los millones de ticks en un simulador que acelere el aprendizaje, pero solo merece la pena si C, A y el
análisis de datos (B0-B2) salen bien.
