# Técnica de conducción: lo que dicen los manuales, lo que hace el teacher y lo que falta

Documento vivo. Recoge las técnicas de conducción deportiva que queremos que el teacher domine (y que luego aprenda el BC/PPO), las compara con lo que hace hoy con datos de nuestros logs, y ordena lo que falta. Las decisiones y las cifras de sesiones concretas están en `DECISIONES.md` (V64-V66); el estado y lo siguiente, en `PENDIENTE.md`.

**Aviso sobre los datos (corregido en V67).** En los logs de `log_schema` 1 y 2 el campo `vehicle.lat_accel` es la aceleración **longitudinal** (`local_acceleration[2]`; correlación 1,000), un nombre heredado (H1); la lateral de verdad es `vehicle.local_accel[0]` (correlación 0,995 con velocidad · guiñada). Desde `log_schema` 3 (sesiones posteriores al 2026-11-02) `lat_accel` es la lateral real y hay un `long_accel` explícito (positivo al acelerar). Para leer cualquier log, antiguo o nuevo, use `session_log.tick_accels(tick['vehicle'])`, que devuelve (lateral, longitudinal) a partir de `local_accel` sin depender del esquema. `resumen_sesion.py` ya usaba el eje correcto; varios scripts sueltos del 2026-11-02 usaron el malo y sus cifras se corrigieron en V66. Toda cifra de este documento usa la lateral real y la deceleración positiva al frenar.

## 1. Fuentes

| Fuente | Qué aporta | Qué no cubre |
| --- | --- | --- |
| [The Art of Braking and Car Control](https://www.porschenorthhouston.com/static/dealer-12179/DE_-_The_Art_of_Braking.pdf) (Porsche Club of America, Lone Star Region, 6 páginas) | Frenar en línea recta; frenada «invertida»; secuencia freno → soltar → gas → asentar la suspensión → girar; terminar de frenar antes de girar | Cifras de presión; trail braking; curvas lentas/rápidas |
| [Técnicas de conducción deportiva, parte 2: frenar](https://8000vueltas.com/2015/03/23/tecnicas-de-conduccion-deportiva-parte-2-frenar) (8000vueltas) | Círculo de adherencia; zona de frenada; tiempos muertos; presión; ABS; frenada en recta y en apoyo; trail braking; telemetría | Cifras de presión o distancia |
| [Técnicas de conducción deportiva, parte 1: acelerar](https://8000vueltas.com/2015/03/05/tecnicas-de-conduccion-deportiva-parte-1-acelerar) (8000vueltas) | Salida de parado; deslizamiento óptimo ≈ 10 %; tiempo de cambio de 0,4-0,6 s; puntos de cambio | Acelerar en curva (lo deja para la parte 3) |
| [Técnicas de conducción deportiva, parte 3: trazado de curvas](https://8000vueltas.com/2015/04/15/tecnicas-de-conduccion-deportiva-parte-3-trazado-de-curvas) (8000vueltas, abril de 2015) | Secuencia de la curva; punto de giro; vértice; salida con tiempo de espera; tipos de curva (decreciente, creciente, horquilla, ese); mirar lejos; suavidad | Cifras (solo dos ejemplos) y ejercicios |

La parte 3 solo está enlazada desde un comentario de la parte 2 (no desde el artículo) y no hay parte 4 ni índice de la serie. Ninguna de las tres fuentes da cifras de presión de pedal ni tiempos de espera: todo lo numérico tendrá que salir de nuestros datos.

## 2. Principios de las fuentes

1. **El agarre es un presupuesto** (círculo de Kamm): frenar, girar y acelerar se suman vectorialmente y la suma no puede pasar del borde del círculo. Frenar al límite y girar a la vez se sale del círculo (8000vueltas). Cuanto más giro, menos freno disponible.
2. **Lo más eficaz es frenar en línea recta** (PCA). «Termina de frenar antes de empezar a girar» siempre que se pueda.
3. **Frenada «invertida»** (PCA): pisar fuerte al principio, cuando el coche va recto, y soltar gradualmente («un tiempo de vals abajo, dos-tres arriba»). Por qué: el coche llega al giro estable y equilibrado; el cambio de marcha se hace pronto, con el coche asentado; si se ha frenado tarde se puede seguir frenando; sin ABS el posible bloqueo ocurre al principio, cuando ya se iba a soltar. Lo que importa más es **cómo se suelta** que cómo se pisa.
4. **Secuencia de la curva** (PCA): freno en recta → soltar el freno (el peso pasa atrás) → gas progresivo («squeeze») → suspensión asentada → girar. En el vértice, a gas y con el par llegando al suelo.
5. **Trail braking** (8000vueltas): alargar el freno más allá del giro, hasta casi el vértice, soltando poco a poco mientras se mete volante. Frena más tarde, entra más rápido y carga el eje delantero (menos subviraje). Es técnica de pilotos muy buenos (frenan «en apoyo» recorriendo el perímetro del círculo), sirve sobre todo en curvas de radio decreciente y poco en codos de 90° que exigen girar de golpe. Las dos fuentes no se contradicen del todo: PCA lo enseña como norma segura («termina antes»), 8000vueltas como técnica avanzada.
6. **Tiempos muertos**: minimizar el tiempo sin gas ni freno al pasar de uno a otro; nunca solapar los dos pedales (8000vueltas).
7. **Presión**: tanto freno como aguante el neumático sin llegar al bloqueo. El bloqueo delantero anula el giro; el trasero desestabiliza. Frenar justo antes de que actúe el ABS da más que con ABS activo, y ambos más que bloquear.
8. **Frenada regresiva** (con carga aerodinámica): mucha presión a velocidad alta y menos al bajar. En coches sin apoyo aerodinámico apenas aplica; la suspensión blanda pide subir la presión de forma progresiva, la dura permite pisar de golpe.
9. **Zona, no punto, de frenada**: la adherencia cambia con combustible, neumáticos y asfalto. Se busca vuelta a vuelta: frenar con la misma intensidad un poco más tarde hasta pasarse, y retroceder un punto.
10. **Cambios de marcha**: bajar mientras se frena en recta, ni antes de frenar ni al final; en apoyo es un punto crítico que puede desestabilizar. Subir en 0,4-0,6 s por cambio; el punto de cambio es donde la potencia de las dos marchas es igual (por encima de la potencia máxima).
11. **Acelerar**: el neumático da el máximo con ≈ 10 % de deslizamiento; los golpes de gas desestabilizan; la transferencia de peso hacia atrás ayuda a la tracción trasera.
12. **Medir con telemetría**: un diagrama g-g muestra si se combina o se pasa por el centro del círculo al cambiar de fase. El piloto malo se mueve en condiciones aisladas (solo frena o solo gira); el bueno recorre el perímetro.
13. **Mirar lejos** (parte 3): «prácticamente el 50 % de la conducción»; mirar la salida de la curva y no clavar la vista en el vértice, sobre todo en curvas rápidas.
14. **Suavidad**: conducir suave, no lento; reduce la transferencia de pesos y mantiene el neumático en el límite. Con solo el 50 % de adherencia un volante brusco al acelerar o frenar descoloca el coche.
15. **Punto de giro** (parte 3): normalmente coincide con soltar el freno (salvo trail braking). *Adelantado* (instinto de principiante): obliga a un vértice adelantado y a reducir mucho. *Tardío*: por frenar tarde o poco; si se va pasado, **es mejor seguir frenando con el coche recto que girar a velocidad excesiva**. *Ideal*: el que da la trazada más rápida del conjunto, no la de mayor velocidad de paso.
16. **Vértice**: el geométrico es la trazada de mayor radio; la real suele **retrasarlo** para frenar más tarde, girar con menos radio y enderezar antes para acelerar. Los coches pesados y potentes frenan muy tarde y se enderezan cuanto antes; los ligeros y poco potentes se acercan a la trazada geométrica.
17. **Salida con tiempo de espera** (parte 3): al soltar el freno se puede dar un poco de gas para estabilizar y ganar tracción, **sin contundencia hasta salir del giro**; las curvas rápidas casi no tienen espera y las cerradas (una rotonda de 180°) exigen esperar más. Después: abrir volante progresivamente, dejando que el coche vaya al exterior, y gas decidido, **evitando el ciclo «dar gas – levantar»**.
18. **Tipos de curva** (parte 3): *radio decreciente* («curva trampa»): entrada y vértice muy tardíos; *radio creciente*: punto de giro y vértice adelantados sin riesgo, pero son más rápidas de lo que parecen; *horquilla*: punto de giro y vértice tardíos y mucha espera antes de acelerar; *ese o chicane*: tratar cada parte por separado falla en la segunda, hay que **sacrificar una parte** y se prioriza la que precede o sigue a la recta más larga (los mismos metros a mayor velocidad media cuestan menos tiempo; ejemplo del autor: 5 km/h más en una recta de 250 km/h frente a 120-125 km/h en la otra parte).
19. **Mojado** (parte 3): evitar la goma depositada en el asfalto, que en seco da agarre y en mojado resbala.

## 3. Lo que hace hoy el teacher, con datos

Sesiones comparadas (línea suavizada, 125 km/h, vuelta 2): producción `130600Z` (receta de V64, línea `a1mu9c12`) y técnica de pedales `140704Z` (V65; línea suavizada). Cifras con el eje lateral correcto.

| Aspecto | Fuente | Teacher hoy | Dato | Brecha |
| --- | --- | --- | --- | --- |
| Capacidad de frenada usada | 7 | Supone 8 m/s² en recta y 4 m/s² en curva; el coche da 11,5-11,8 sin bloqueo (V55) | deceleración máx. 13,2 (producción) y 10,0 (técnica); mediana en frenada 5,8 y 5,4; tiempo de freno con ≥ 10 m/s²: 10 % y 0 %; pedal máx. 0,82 y 0,58 | Se frena al 50-70 % de lo que da el coche |
| Salto de la consigna al entrar en la curva | 1, 2 | `braking_on_straight` cambia la deceleración supuesta de 8 a 4 m/s² cuando \|κ\| pasa de 0,004 | En `140704Z` vuelta 2, 225 → 230 m: el objetivo baja de 105 a 90 km/h en 5 m y el exceso pasa de +2,4 a +4,9 m/s | El freno se prolonga dentro de la curva en lugar de terminar antes del giro |
| Frenar ya girando | 2, 5 | Se frena en la curva | Energía de frenada con > 4 m/s² laterales: 68 % (técnica). De las 8 frenadas, 4 empiezan en recta (lateral 0-2 m/s²) y acaban a 10-11 m/s² laterales; otras 4 (S, curvas encadenadas) ya empiezan girando (4-6 m/s²) | Tras el giro se sigue frenando |
| Círculo de adherencia al frenar | 1, 12 | No hay presupuesto combinado | Combinada √(lat² + dec²) en frenada: mediana 10,5 y p90 11,8 m/s² (72 % y 81 % de 14,6) | Se usa ~ 3/4 del círculo al frenar |
| Tiempo muerto | 6 | Frena solo si el exceso pasa 1,5 m/s | Sin gas ni freno antes de frenar: 0,04 s (producción); **0,27 s de media, máx. 1,15 s, ≈ 9 m** (técnica) | La técnica de pedales introdujo tiempo muerto |
| Forma de la frenada «invertida» | 3 | Pedal proporcional al exceso sobre una parábola | Máximo del pedal en el 35 % (producción) y 26 % (técnica) de la frenada; sube 0,24 → 0,43 → 0,50 en 10 m | Hay pico temprano, pero a un valor bajo |
| Gas progresivo desde el vértice | 4, 11 | `--pedal-technique` (V65): el gas solo sube, 1,5/s | Inversiones del gas: 45 → 24 por vuelta; rebotes antes de frenar 7 de 15 → 2 de 8 | Hecho a medias; sin tope por el círculo |
| Cambio de marcha | 10 | Automático | Subidas 17, bajadas 12-14 por vuelta; 0,17 s sin marcha al subir y 0,20 al bajar; baja la velocidad 5,1-6,5 km/h al bajar | Subida mejor que los 0,4-0,6 s de la fuente; falta ver cuándo caen las bajadas respecto a la frenada |
| Bloqueo / ABS | 7 | Limitador por deslizamiento (V44-V55) | Cerrado: 11,4-11,8 m/s² desde 150 km/h con `--brake-slip-limit 0.25 --brake-slip-hold 0.85`; ABS del juego en 0 ticks | Hay herramienta, no se usa en A2 |
| Puntos de frenada | 9 | Los fija la consigna por parábola, iguales cada vuelta | La vuelta 2 es idéntica a la 3 y la 4 | No busca el límite vuelta a vuelta |
| Neumáticos | 11 | Sin estado térmico | 82 → 46 °C (delanteros) en 4 vueltas a 125 km/h; no explica por sí solo los fallos (V64) | A ritmo real se calentarían; sin medir |

## 4. Modelo objetivo de una curva

Fases (la fuente que respalda cada una, entre paréntesis):

1. **Aproximación** a la velocidad de la banda (gas).
2. **Corte y freno sin tiempo muerto** en el punto de frenada, que se calcula con la capacidad real y no con una cifra conservadora (6, 7, 9). Menos de 0,1 s entre soltar el gas y pisar el freno.
3. **Frenada invertida en línea recta** (3): el pedal llega pronto a su máximo (límite del deslizamiento, ≈ 11-11,7 m/s²) y empieza a bajar. Objetivo: acabar la parte principal antes del giro (2, 3, 5).
4. **Suelta progresiva con el giro** (5): el freno disponible en cada instante es el que deja el círculo: `a_frenada = √(a_máx² − a_lat²)`. La suelta termina en el vértice (velocidad mínima) y es **continua con la consigna**, sin saltos.
5. **Vértice**: freno 0, gas empieza (4).
6. **Gas con tiempo de espera y progresivo** (4, 11, 17): tras el vértice un gas ligero de estabilización durante un tiempo que crece con el ángulo de la curva (nada en curvas rápidas, más en horquillas y rotondas), y después subida decidida con tope por el círculo (`a_acel = √(a_máx² − a_lat²)`, menos lo que consume la resistencia) hasta la salida; a fondo con el volante recto. Sin ciclos «gas – levantar».
7. **Cambios**: bajadas durante la parte recta de la frenada, subidas rápidas; nunca en apoyo si se puede evitar (10).

Decisión pendiente (a discutir con el usuario): empezar por la versión «PCA» (terminar casi todo el freno antes de girar y soltar con el giro) y dejar el trail braking completo para cuando el resto esté medido, porque es lo que las dos fuentes consideran avanzado.

## 5. Lo que falta, en orden

| Id | Qué | Por qué | Criterio de éxito |
| --- | --- | --- | --- |
| F1 | **IMPLEMENTADA (V68, §8; sin probar en el juego).** **Frenada de entrada continua y a capacidad real**: deceleración supuesta continua entre recta y curva (sin el salto 8 → 4), basada en el círculo; punto de frenada sin margen de 1,5 m/s y sin tiempo muerto; límite por deslizamiento en vez de topes de pedal | Es la brecha mayor (deceleración al 50-70 %, 68 % del freno dentro de la curva, tiempo muerto 0,27 s) | Tiempo muerto ≤ 0,1 s; deceleración media en las frenadas de recta ≥ 9 m/s²; sin salto de la consigna > 2 km/h por metro; energía de frenada con > 4 m/s² laterales ≤ 40 %; tiempo de vuelta menor que el de `140704Z`; \|CTE\| y deriva como en esa sesión |
| F2 | **Suelta con presupuesto del círculo** (trail controlado) | Cierra la fase 4 | La velocidad mínima coincide con el vértice (± 20 m) y el lateral no sube de 14,6 |
| F3 | **HECHO (V72-V73, `--exit-circle 14.6`).** **Tope del gas por el círculo** en la salida con el lateral medido | C11 salía con 0,93-1,00 de gas con 11-12 m/s² laterales | **Cumplido:** C11 de 2,1-2,24 a 1,39-1,71 m; casi todas las curvas bajan; +0,23 s por vuelta |
| F4 | **Perfil de velocidad planificado** (solver de `circuito_virtual` con las tablas de A1) como referencia del teacher en lugar de la parábola con constantes | Unifica 4, 5 y 6: da el freno, el vértice y el gas con el mismo presupuesto | Consigna y perfil del solver difieren < 3 km/h en las frenadas |
| F5 | **Puntos de frenada adaptativos por curva**: retrasar el punto vuelta a vuelta hasta el límite y retroceder | Fuente 9 | Convergencia en ≤ 5 vueltas sin salirse |
| F6 | **Cambios de marcha respecto a la frenada**: ver cuándo caen las bajadas y cuánto cuestan | Fuente 10 | Ninguna bajada en apoyo con > 6 m/s² laterales |
| F7 | **Estado térmico de los neumáticos** (calentamiento, ritmo) | A ritmo real se calientan; hoy se enfrían | Se decide al medir un ritmo más alto |
| F8 | **Herramientas de medida**: ampliar `pedales_sesion.py` con g-g, tiempo muerto, energía de frenada en curva y deceleración. *Hecho: `pedales_sesion.py` mide ya tiempo muerto, deceleración, energía con > 4 m/s² laterales, uso del círculo y, con `--consigna`, el salto de la consigna sin juego (cifras de partida en §7.1); falta el diagrama g-g gráfico. Hecho (V67): el campo `lat_accel` del log pasa a ser la lateral real (`log_schema` 3), hay `long_accel` y `tick_accels` lee cualquier log sin depender del esquema.* | Fuente 12; evitar repetir el error del eje | Tests y una línea por sesión en el resumen |
| F9 | ~~Leer la parte 3 de 8000vueltas (trazado)~~ **Hecho:** principios 13-19 y filas F10-F13 | Era la fuente más importante para el gas en curva | Sección incorporada |
| F10 | **Tiempo de espera en la salida**: gas ligero tras el vértice con una duración que depende del ángulo de la curva y subida decidida después (hoy el gas sube desde 0 con pendiente fija 1,5/s) | Principio 17 | Menos inversiones del gas y sin deriva > 4° a la salida; tiempo de vuelta menor |
| F11 | **Clasificar las curvas de la línea** (radio decreciente, creciente, horquilla, ese) a partir de κ(s) y adaptar punto de frenada y de giro a cada tipo | Principio 18 | Tabla de curvas de Sugo con su tipo; la consigna cambia solo donde el tipo lo pide |
| F12 | **Eses: prioridad por la recta más larga**. Comprobar si la línea óptima y la consigna ya sacrifican una parte de la S de 400-600 m y de la de 2380-2560 m a favor de la recta que sigue | Principio 18 | Velocidad de paso y de salida de cada parte comparada con la del solver |
| F13 | **Horizonte de mirada**: la consigna mira 150 m y el volante 0,3 s; ver si hace falta mirar más lejos en las curvas rápidas y en las que están encadenadas. **V79:** primer paso, `--profile-peak-min-m` recorta los picos cortos entre curvas del perfil (el sube-baja de C5-C6, C9, C10 y C12-C14 era lo que pedía el perfil); implementado, sin probar en el juego | Principio 13 | Sin sorpresas de curva (consigna que cae > 10 km/h en < 10 m); sin gas, freno y gas entre curvas cercanas |

## 6. Cómo se usa este documento

- Cada sesión de técnica se juzga con los criterios de la tabla 5 además de los de V19 (`resumen_sesion.py`) y con `pedales_sesion.py`.
- Al cerrar una fila, se anota la sesión y la cifra aquí y la decisión (V…) en `DECISIONES.md`.
- Una sola variable por sesión (V19).

## 7. Preparación de la próxima sesión: F1 (frenada de entrada)

*Diseño original; el estado actual, con los ajustes que salieron de la simulación (margen del perfil, mando del círculo, anticipación de baches), está en §8.*

### 7.1 Cifras de partida (vuelta 2, `pedales_sesion.py`; la consigna con `--consigna`)

| Sesión | Frenadas | Rebotes | Inversiones | Tiempo muerto medio / máx. | Deceleración mediana / p90 / máx. | ≥ 10 m/s² | Pedal máx. | Energía con > 4 m/s² laterales | Círculo mediana / p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `124357Z` suavizada, producción | 17 | 9 | 43 | 0,06 / 0,28 s | 6,3 / 10,0 / 12,8 | 10 % | 0,81 | 67 % | 73 / 82 % |
| `130600Z` `a1mu9c12` (v0 60, sin tope), producción | 15 | 7 | 45 | 0,04 / 0,10 s | 5,8 / 10,0 / 13,2 | 10 % | 0,81 | 72 % | 72 / 83 % |
| `140704Z` suavizada + técnica de pedales | 8 | 2 | 24 | 0,28 / 1,15 s | 5,4 / 9,2 / 10,0 | 0 % | 0,58 | 68 % | 72 / 81 % |

Consigna de velocidad del teacher sin juego (`--consigna`): mayor caída **16,8 km/h en 1 m en 810 m** (119,7 → 102,9 km/h) con `sugo_smooth.json` y 16,6 km/h en 811 m con `a1mu9c12`; **16 puntos de la línea con caída > 2 km/h por metro**. Es el salto de `braking_on_straight` (|κ| = 0,004: la deceleración supuesta pasa de 8 a 4 m/s²). Las 8 frenadas de `140704Z` con su tabla: `pedales_sesion.py <log> --vueltas 2 --eventos`.

### 7.2 Diseño propuesto (opt-in; solo se implementa con el visto bueno del usuario)

Objetivo: una sola consigna **continua** en la distancia que incluya el presupuesto del círculo, y un pedal que la siga a capacidad real. Cubre F1 y la mayor parte de F2 (la suelta con el giro sale del propio círculo).

1. **Perfil de consigna v\*(s) por barrido hacia atrás**, calculado una vez por referencia y parámetros y guardado en caché (sustituye a la parábola de deceleración constante evaluada en cada tick). Con `vlim(s)` como hoy (√(a_lat / |κ|), κ suavizada ±7 m):
   - `v*(i) = min(vlim(i), √(v*(i+1)² + 2 · a_frenada(i) · 1 m))`, dando dos vueltas al circuito para cerrar el bucle.
   - `a_frenada(i) = a_b · √(max(0, 1 − (v*(i+1)² · |κ(i)| / a_círculo)²))`, con `a_b` la deceleración en recta (`--brake-decel-straight`, hoy 8; objetivo 10-11 con el limitador de deslizamiento) y `a_círculo` = 14,6 (D21). Con la carga lateral del límite (9 m/s²) el factor es 0,79: con `a_b` = 11 quedan ≈ 8,7 m/s² de freno disponible en la entrada de la curva (con `a_b` = 8, 6,3), en lugar de los 4 que supone hoy.
   - La consigna es `min(banda, v*(s))`: sin saltos (la caída máxima por metro queda acotada por `a_frenada`).
2. **Freno por avance (feed-forward) más corrección**: deceleración necesaria `a_nec = (v² − v*(s+10 m)²) / (2 · 10)`; pedal = tabla de V55 (pedal ↔ deceleración medida en `resumen_sesion.py`: 0,40-0,55 → 8,3-8,9; 0,55-0,70 → 9,6-9,9; 0,70-1,00 → 11,6-11,7 m/s²) más un término proporcional al exceso sobre `v*(s)`. Sin margen de 1,5 m/s y con el gas cortado en el mismo instante: tiempo muerto ≤ 0,1 s. El pedal es máximo al principio (cuando `a_nec` es mayor) y baja con el círculo al meter volante: forma «invertida» de la fuente 3.
3. **Fases y razones** como en V65 (`lift_lock`, `brake_overspeed`, `accel_exit`); `approaching` pasa a calcularse con el mínimo de `v*` por delante. Los parámetros de V65 (`lift_band_ms`, `lift_drop_ms`, `trail_offset_ms`) se revisan, no se duplican.
4. **Opciones nuevas**: `--brake-profile` (activa el perfil continuo; solo con `--lat-accel-limit`), `--brake-circle` (14,6) y reutiliza `--brake-decel-straight`. Todas apagadas por defecto; se cablean en `learn_driver.py`, `aislado.py` y las reglas de `a2_error` como las de V65.
5. **Ya existe el solver** (`circuito_virtual/src/perfil_velocidad.py`, tablas de A1): F4 sería cargar su perfil en lugar de recalcularlo. La dirección de dependencias (`PCARS2-AI` ← `circuito_virtual`) obliga a pasar el perfil como archivo; F1 con el cálculo local es el paso previo y sirve para comparar.

### 7.3 Tests que escribir antes de una sesión (en `PCARS2-AI/tests/`, con el coche de juguete de `test_pedal_technique.py`)

- La consigna no cae más de 2 km/h por metro en ningún punto de Sugo (la de hoy cae 16,8).
- Velocidad de entrada a las curvas (exceso sobre la consigna al empezar a frenar) no mayor que la de producción con aceleración del juguete ×1,0, ×1,3 y ×1,6 (la regresión de V65 7).
- Tiempo muerto medio ≤ 0,1 s y deceleración media en las frenadas de recta ≥ 9 m/s² en el juguete.
- Con el juguete, la energía de frenada con lateral estimado (v² · |κ|) > 4 m/s² es menor que la de producción.
- Opciones apagadas ⇒ pedales idénticos a producción (como `test_technique_off_matches_explicit_off`).

### 7.4 Sesión de juego y cómo se juzga

Una variable respecto a `140704Z` (suavizada, receta de `124357Z`, `--pedal-technique`): añadir `--brake-profile` (y `--brake-slip-limit 0.25 --brake-slip-hold 0.85`). Primera vuelta con el usuario atento (Ctrl+C si el coche llega a una curva sin levantar). Se juzga con `resumen_sesion.py` (V19) y `pedales_sesion.py <log> --vueltas 2,3,4 --eventos`:

| Criterio | `140704Z` | Objetivo |
| --- | --- | --- |
| Tiempo muerto antes de frenar | 0,28 s | ≤ 0,1 s |
| Deceleración mediana en frenada / ≥ 10 m/s² | 5,4 m/s² / 0 % | ≥ 7 m/s² / ≥ 25 % del tiempo |
| Pedal máx. | 0,58 | ≥ 0,8, sin bloqueo de ruedas (regla de `PENDIENTE.md`: rps de cada eje frente al otro) |
| Energía de frenada con > 4 m/s² laterales | 68 % | ≤ 40 % |
| Salto de la consigna (sin juego) | 16,8 km/h por m | ≤ 2 |
| Rebotes de gas antes de frenar / inversiones | 2 de 8 / 24 | 0 / ≤ 11 |
| Tiempo de vuelta | 120,1 s | menor |
| \|CTE\| máx., deriva, S de 400-600 m | 1,72 m, 2,9°, 1,6 m | iguales o mejores (V19) |

### 7.5 Sesiones que se pueden lanzar ya, sin código nuevo

- **A. Separar línea y técnica** (una variable respecto a `130600Z`): `a1mu9c12` con la receta 60 / sin tope y `--pedal-technique`. Pregunta: ¿la técnica arregla los fallos de las zonas rápidas (hasta 1,94 m en 2972-3005 m, ruedas fuera en 2290 y 2820-2900 m)? Experimento `a2_optA1mu9c12_125_g3_lat9_slip5_v60_ff0_pv03_gas1_fr8_pedal_l4`.
- **B. Margen lateral** (la propuesta del usuario, una variable respecto a `140704Z`): `--lat-accel-limit 10` con la suavizada y `--pedal-technique`. Sube la velocidad en curva un 5 % y pide ≈ 15-16 m/s² laterales (por encima de los 14,6 de D21): solo con el usuario atento. Experimento `a2_suave_125_g3_lat10_slip5_v60_ff0_pv03_gas1_fr8_pedal_l4`.

Los comandos completos están en `PENDIENTE.md`, «Comandos vigentes».

### 7.6 Decisiones que necesita del usuario

1. ¿Empezar por «terminar de frenar antes de girar» (PCA) con el círculo, dejando el trail braking completo para después? (Recomendado: el círculo ya da una suelta con el giro.)
2. ¿Implementar F1 con el perfil local (7.2) o esperar a F4 (perfil del solver como archivo)? (Recomendado: local primero, para poder comparar.)
3. Valor de `a_b`: 8 (hoy) o 10-11 con limitador de deslizamiento. (Recomendado: 10 con `--brake-slip-limit 0.25 --brake-slip-hold 0.85`, probado en A1 hasta 150 km/h.)
4. ¿Se hace el commit antes de empezar? (Hay cambios sin comitear de V64-V67.)

## 8. F1 implementado (V68): qué hay, cómo se mide y las dos sesiones

### 8.1 Qué se implementó (opt-in, apagado por defecto)

`--brake-profile` (con `--pedal-technique`; `--brake-circle` opcional) en `teacher_controller.py`, `learn_driver.py` y `aislado.py`. Sigue el diseño de §7.2 con estos ajustes que salieron de la simulación:

- **Perfil v\*(s)** por barrido hacia atrás, dos vueltas, en caché: `v*(i) = min(v_lim(i) + offset, √(v*(i+1)² + 2 · a_frenada(i) · 1 m))`, con `a_frenada = a_b · √(1 − (a_lat / círculo)²)` y `a_b` = `--brake-decel-straight`. **`brake_profile_offset_ms` = 1,0**: la ley de siempre toma las curvas por encima del límite lateral (frena al pasar un margen de 1,5 m/s); sin ese margen el perfil exacto era 2 s más lento en el juguete. Con 1,0 el juguete entra a las curvas como la producción (exceso 2,5 frente a 2,4 m/s) y tarda 0,2 s más; con 1,5 entraba 1 m/s más rápido.
- **El radio del círculo es el mando** entre trail braking completo y «terminar de frenar antes de girar»: 14,6 (D21) deja que el freno conviva con el giro hasta el límite; ≈ 10 casi lo impide. Con `a_b` 8 en el juguete: círculo 14,6 / 12 / 11 / 10 / 9,5 → frenada con el coche girando 73 / 69 / 67 / 61 / 58 % y +0,2 / +0,4 / +0,4 / +0,5 / +0,7 s. Con `a_b` 10: 82 / 79 / 75 / 71 / 68 % y +0,07 / +0,1 / +0,2 / +0,25 / +0,6 s. (La producción: 83 %.) **Se propone 11** como primer valor.
- **Freno por avance**: deceleración necesaria `a_nec = (v² − v*(s+10 m)²) / 20`; pedal = tabla medida (`PEDAL_DECEL_TABLE`, de V55-V66) más 0,12 de pedal por m/s de exceso sobre el perfil; sin margen de 1,5 m/s (el disparo por exceso pasa a 0,3 m/s porque el margen ya está en el perfil) y sin esperar: el gas se corta en el mismo instante. **Anticipación de baches**: con perfil, una curva por delante cuenta si su límite está al menos 1,5 m/s por debajo de la velocidad (`brake_profile_lift_drop_ms`; los baches de la curvatura de Sugo hacen mínimos de ≈ 3 m/s que con 3,0 no se anticipaban).
- **Funciones nuevas**: `braking_profile`, `profile_at`, `profile_info`, `pedal_for_decel`, `_smoothed_kappa` (refactor sin cambio de comportamiento de `_lateral_speed_limits`).

### 8.2 Medido sin juego (línea suavizada, `pedales_sesion.py --consigna … [--perfil]`)

| Consigna del teacher | Mayor caída | Puntos con caída > 2 km/h por metro | Deceleración implícita máx. |
| --- | --- | --- | --- |
| La de siempre (`a_b` 8) | 16,8 km/h en 1 m (810 m) | 16 | 144,6 m/s² |
| Perfil, círculo 11, `a_b` 8 | 1,16 km/h en 1 m (2020 m) | 0 | 8,0 m/s² |
| Perfil, círculo 14,6, `a_b` 8 | 1,17 km/h en 1 m | 0 | 8,0 m/s² |
| Perfil, círculo 11, `a_b` 10 | 1,39 km/h en 1 m | 0 | 10,0 m/s² |

Con el coche de juguete (pedal ↔ deceleración de la tabla medida; sin agarre, subviraje ni marchas), vuelta de Sugo a 110 km/h, producción frente a perfil con `a_b` 8 y círculo 14,6: tiempo muerto 0,04 → 0,02 s; frenadas 16 → 13; el exceso de velocidad de entrada a las curvas, igual (+2,4 → +2,5 m/s). Tests: `PCARS2-AI/tests/test_brake_profile.py` (11) y 2 más en `experimental`; `PCARS2-AI` 530, `experimental` 106, `circuito_virtual` 65.

### 8.3 Sesión F1-1 (una variable respecto a `140704Z`): el perfil

Receta de `140704Z` + `--brake-profile --brake-circle 11` (`--brake-decel-straight 8`, sin limitador). Primera vuelta con el usuario atento. Comando:

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --teacher-only --speed-band 125 --max-gear 3 --lat-accel-limit 9 --steer-ff-gain 0.003 --steer-ff-v0-kmh 0 --steer-preview-s 0.3 --steer-slip-gain 5 --lat-gain-v0-kmh 60 --throttle-max 1.0 --brake-decel-straight 8 --brake-overspeed-straight-ms 2.5 --pedal-technique --brake-profile --brake-circle 11 --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_smooth.json --experiment a2_suave_125_g3_lat9_slip5_v60_ff0_pv03_gas1_fr8_perfil_c11_l4 --laps 4
```

Se juzga con `resumen_sesion.py` y `pedales_sesion.py <log> --vueltas 2,3,4 --eventos`:

| Criterio | `140704Z` | Objetivo F1-1 |
| --- | --- | --- |
| Tiempo muerto antes de frenar | 0,28 s (máx. 1,15) | ≤ 0,1 s |
| Energía de frenada con > 4 m/s² laterales | 68 % | ≤ 55 % |
| Deceleración máxima en frenada | 10,0 m/s² | ≥ 8 m/s² (con `a_b` 8 no se espera más; el pedal máx. ronda 0,5-0,6) |
| Velocidad de entrada a las curvas (exceso al empezar a frenar) | referencia | no mayor que en `140704Z` |
| Rebotes de gas antes de frenar / inversiones | 2 de 8 / 24 | 0 / ≤ 11 |
| Tiempo de vuelta | 120,1 s | ≤ 120,4 s |
| \|CTE\| máx., deriva, S de 400-600 m | 1,72 m, 2,9°, 1,6 m | iguales o mejores (V19) |

### 8.4 Sesión F1-2 (después de F1-1): deceleración a capacidad real

Con el círculo 10 y 6 vueltas (más muestras de vueltas frías; V70): `--brake-decel-straight 10` y el limitador de deslizamiento (`--brake-slip-limit 0.25 --brake-slip-hold 0.85`, ya cerrado en V55). Objetivo: deceleración mediana ≥ 7 m/s², ≥ 25 % del tiempo de freno con ≥ 10 m/s², pedal máx. ≥ 0,8, sin bloqueo de ruedas (rps de cada eje frente al otro), mismo tiempo o menor. Comando:

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --teacher-only --speed-band 125 --max-gear 3 --lat-accel-limit 9 --steer-ff-gain 0.003 --steer-ff-v0-kmh 0 --steer-preview-s 0.3 --steer-slip-gain 5 --lat-gain-v0-kmh 60 --throttle-max 1.0 --brake-decel-straight 10 --brake-overspeed-straight-ms 2.5 --brake-slip-limit 0.25 --brake-slip-hold 0.85 --pedal-technique --brake-profile --brake-circle 10 --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_smooth.json --experiment a2_suave_125_g3_lat9_slip5_v60_ff0_pv03_gas1_fr10_perfil_c10_slip_l6 --laps 6
```

### 8.5 Qué vigilar y qué puede salir mal

- **Primera vuelta**: que el coche levante y frene a tiempo en cada curva; si llega a una sin frenar o se pasa, Ctrl+C. La regresión de V65 7 (consigna congelada que tapaba la curva) no aplica al perfil, que se calcula de la curvatura, pero el juguete no sustituye al juego.
- **Si frena demasiado pronto/poco**: el mando es `--brake-circle` (más alto = frena más tarde y más dentro de la curva) y, en código, `brake_profile_offset_ms`.
- **Si el volante sufre al frenar girando** (lazo del volante): comparar \|CTE\| y deriva en las frenadas con las de `140704Z`.
- **El juguete no modela**: agarre, subviraje, cambios de marcha, transferencia de peso. Lo que dice sobre el tiempo de vuelta es solo un indicio.

### 8.6 Resultado de F1-1 (`160048Z`, V69) y siguiente paso

| Criterio | `140704Z` | Objetivo F1-1 | F1-1 |
| --- | --- | --- | --- |
| Tiempo muerto antes de frenar | 0,28 s | ≤ 0,1 s | **0,03 s** |
| Energía de frenada con > 4 m/s² laterales | 68 % | ≤ 55 % | **55 %** |
| Deceleración máxima | 10,0 m/s² | ≥ 8 | **12,5** (pedal 0,79; con `a_b` 8 se esperaba 0,5-0,6) |
| Rebotes de gas / inversiones | 2 de 8 / 24 | 0 / ≤ 11 | 6 de 16 / 31 (no) |
| Tiempo de vuelta | 120,1 s | ≤ 120,4 s | 120,65 s (no) |
| V19 | cumple | cumple | no (CTE 2,07 m; deriva 4,5°; rectas 0,268) |

Dos clases de frenada: las **6 de recta** salen como en las fuentes (pedal alto al principio, pico al 13-28 % de la frenada, 16-37 % de la energía con el coche girando); las **10 cortas encadenadas** entre curvas empiezan ya girando con 3-10 m/s² laterales, de ahí los rebotes. El lateral sube (p99 12,4-12,8; hasta 65 ticks por vuelta > 13 m/s²) y con él el \|CTE\| y la deriva en las S.

**Por qué el círculo 10:** el perfil estima el lateral con v² · κ de la línea (≈ 10 m/s² en el límite con `--lat-accel-limit 9` y offset 1,0); el coche hace 14,0-14,8, ≈ 1,45 veces. En unidades de la línea el círculo real es 14,6 / 1,45 ≈ 10. Con 11 la combinada de 2397 m llegó a √(11,5² + 10,5²) = 15,6 m/s².
Orden: F1-1b (círculo 10) → F1-2 (`a_b` 10 + limitador de deslizamiento) → después `--lat-accel-limit 10` (sesión B de `PENDIENTE.md`) con la ley de frenada que quede.

## 9. Curvas numeradas de Sugo (V70)

Catálogo en `circuito_virtual/pistas/sugo_gp/curvas.json` (regenerar con `python circuito_virtual/src/curvas.py`). Los números salen de la curvatura del eje del mapa, desde la línea de meta en el sentido de la marcha, y se ven en el informe HTML de cada sesión, en `resumen_sesion.py` (`[C#]`) y en `pedales_sesion.py --eventos` (columna `curva`). «Ese con» marca dos curvas de sentido contrario a menos de 100 m una de otra.

| Curva | Sentido | Ápice (m) | Tramo (m) | Radio mín. | Tipo | Ese con |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | derecha | 259 | 231-312 | 44 m | radio constante | |
| C2 | derecha | 377 | 324-434 | 46 m | radio creciente | C3 |
| C3 | izquierda | 530 | 501-607 | 52 m | radio creciente | C2 |
| C4 | izquierda | 764 | 710-805 | 31 m | radio constante | |
| C5 | izquierda | 871 | 833-887 | 53 m | radio constante | C6 |
| C6 | derecha | 922 | 907-941 | 51 m | radio creciente | C5 |
| C7 | derecha | 1145 | 1125-1201 | 44 m | radio creciente | |
| C8 | derecha | 1308 | 1252-1368 | 36 m | radio constante | |
| C9 | derecha | 2040 | 2024-2124 | 34 m | radio constante | |
| C10 | izquierda | 2313 | 2254-2349 | 64 m | radio constante | |
| C11 | izquierda | 2427 | 2404-2491 | 64 m | radio creciente | |
| C12 | derecha | 2736 | 2656-2787 | 83 m | radio constante | |
| C13 | derecha | 2859 | 2787-2947 | 94 m | radio constante | |
| C14 | derecha | 2994 | 2947-3113 | 106 m | radio creciente | |

Las **S** del circuito, en este catálogo: C2-C3 (377 → 530 m) y C5-C6 (871 → 922 m); C4-C5-C6 (764-922 m) es la sucesión izquierda-izquierda-derecha donde la vuelta 4 de `161918Z` rompió la trayectoria. Las zonas rápidas con error de seguimiento constante son C11 (2427 m), C13 (2859 m) y C14 (2994 m).

### 8.7 Resultado de F1-1b (`161918Z`, V70)

Círculo 10: energía de frenada con el coche girando 49 % (55 % con 11), tiempo muerto 0,03 s, pedal 0,80; tiempo 120,6 s (no mejora) y V19 no se cumple por la S de C4-C6 en la vuelta 4 (\|CTE\| 2,56 m, lateral 15,0 en C5) y por C14 (2,0 m constante). Los dos fallos son del lazo del volante y no de la frenada (V64, V70). El siguiente paso de frenada es F1-2 (arriba, con círculo 10 y 6 vueltas).

### 8.8 Resultado de F1-2 (`170252Z`, V71)

La frenada de F1 cumple sus objetivos: deceleración mediana 6,8-7,1 m/s² (5,4 con la técnica de V65), 24-27 % del tiempo de freno con ≥ 10 m/s² (0 %), pedal máx. 0,93, tiempo muerto 0,02 s, 47 % de la energía girando (68 %), estable en 6 vueltas. El tiempo de vuelta no cambia (120,45-120,53 s): por curva, F1-2 y `140704Z` difieren +0,28 s en total, y las rectas están en el tope de la banda. **El tiempo ya no depende de cómo se frena** sino de la velocidad de paso en curva (`--lat-accel-limit`; en C4, R 31 m, el coche hace 16-17 m/s² con el límite 9), del tope de la banda y de las salidas. Quedan en rojo C11 (gas a fondo en la salida con 11-12 m/s² laterales: F3/F10) y C14/C13 (error de seguimiento constante a más de 100 km/h: `--steer-ff-cap-kmh 100`).

### 8.9 Resultado del tope de la anticipación (`174237Z`, V72)

`--steer-ff-cap-kmh 100` baja C14 de 2,0 a 0,95 m y C13 de 1,65 a 1,2 m y devuelve las rectas al criterio (cte_rms 0,212); no mueve la frenada ni el tiempo (120,55 s). Queda C11 (gas a fondo con 11-12 m/s² laterales), que corrige F3 (`--exit-circle 14.6`, tope del gas = `gas_max · √(1 − (a_lat / R)²)`). Aviso nuevo: con el perfil de frenada el coche pisa fuera en C4 (R 31 m) unos 25 ticks por vuelta.

### 8.10 Resultado del tope del gas por el círculo (`181618Z`, V73)

C11 baja de 2,1-2,24 a 1,39-1,71 m y casi todas las curvas bajan (el gas en la salida es más suave); cuesta +0,23 s por vuelta. La pareja de vueltas 3-4 cumple V19 (la primera con el perfil de frenada); queda la deriva de C5 en las vueltas 1-2 (4,0-4,8° en el cambio izquierda-derecha de la S). El tiempo (120,8 s) no es mejor que el de la receta de partida: la técnica da una conducción limpia, no más rápida; el siguiente paso para ganar tiempo es la velocidad de paso en curva (`--lat-accel-limit 10`).
