# Diario de circuito_virtual

Lo más reciente arriba. Historia anterior en `experimental/docs/DIARIO.md`.

- **2026-11-01 — `--lat-gain-v0-kmh 70` con la línea `a1mu9` (V35).** Mejora el seguimiento (|CTE| máx. 2,27 → 1,89 m; los 7 tramos fuera de criterio por vuelta quedan en 1) con rectas igual de tranquilas, pero no cumple el criterio: deriva 5,1° (V33: 3,4°) en 921-931 m y 40 ticks con las ruedas izquierdas fuera (V33: 0) en dos puntos (uno por retraso del coche ante un cambio de lado de la línea y otro por un pasillo más estrecho que el coche más el margen). Vuelta lanzada 118,7 s, igual que V33. Se deja v0 = 70 en la receta, no se sube a 80 y la siguiente variable es la línea (pasillo ampliado, salto de curvatura y velocidad de cambio de lado limitados, margen al borde sin relajar).

- **2026-11-01 — Cierre de sesión y próxima prueba lista (V34).** `resumen_sesion.py` reúne en un comando todo lo que se miraba a mano (vueltas, criterio de V19, tramos fuera de criterio, frenos, cambios de marcha, ruedas fuera). `PENDIENTE.md` reescrito con la receta completa, la escalera 80 → 125 km/h, el comando exacto de la siguiente sesión (`--lat-gain-v0-kmh 70` con la línea `a1mu9`) y qué hacer con cada resultado. Todo sin commit: 489 tests en `PCARS2-AI`, 82 en `experimental`, 53 en `circuito_virtual`.

- **2026-11-01 — La línea óptima en el juego (V33).** 118,7 s, 1,7 s menos que con la suavizada (previstos 117,6), sin ruedas fuera de la superficie de carrera. El |CTE| máx. llega a 2,27 m en 7 tramos de 105-123 km/h (el criterio es 1,8): la ganancia de CTE a esa velocidad es baja. El coche pasó fuera del pasillo que daban los logs anteriores en el 16,7 % de los ticks, así que el pasillo era una cota inferior: `bordes_logs.py actualizar` añade los 18 logs de hoy. Siguiente: `--lat-gain-v0-kmh 70`.

- **2026-11-01 — Frenada fuerte en recta y línea óptima rehecha (V32).** Con `--brake-decel-straight 8 --brake-overspeed-straight-ms 2.5` el pedal llega a 0,84 y la deceleración a 11,6 m/s² (el límite del coche, sin bloqueo): 120,4 s, 1,4 s menos. El tiempo ya está en lo que prevé el modelo; para bajar más hay que cambiar la línea o el límite lateral. La línea de V15 no sirve para el coche del teacher (+0,4 %); rehecha con su modelo (`--coche-a1-mu 9`): −1,94 % previsto (117,6 s). Siguiente: probarla.

- **2026-11-01 — 125 km/h con 3.ª y los frenos del teacher (V31).** Cumple (|CTE| máx. 1,59 m, deriva 3,5°), 121,8 s frente a 120,6 previstos. El usuario nota que el freno no pasa de ≈ 25 %: pedal máximo 0,28 y 4-5 m/s² de deceleración frente a los 11,5-11,8 de G3 sin bloqueo. El solver da ≈ 1 s de ganancia a 125 km/h con frenada plena. Opciones nuevas en recta: `--brake-decel-straight` y `--brake-overspeed-straight-ms`.

- **2026-11-01 — 120 km/h con 3.ª, cambios y diferencial (V30).** Cumple el criterio (|CTE| máx. 1,77 m, deriva 1,6°), vuelta de 123,4 s (previstos 122,6). El «lag» del cambio 2.ª → 3.ª es de 0,17 s en punto muerto y ≈ 0,1 s de embrague, igual que en G1b y G3; no hay bloqueo de traseras al bajar de marcha (razón traseras/delanteras 0,93-0,96). Diferencial trasero con DDL por embragues «Sí» y rampa de 30° (falta ver el resto) y freno de motor en 8. Siguiente: 125 km/h con `--max-gear 3`.

- **2026-11-01 — G3 hecho: frenadas desde la 3.ª (V29).** 8 frenadas a fondo desde 100, 110 y 115 km/h: 11,4-11,8 m/s² corregidos de pendiente, 28-39 m hasta 30 km/h, bajadas de marcha 3 → 2 → 1 con 0,2 s de punto muerto cada una, |CTE| máx. 0,44 m. Valida `--max-gear 3` para acelerar hasta 135 y frenar desde 115. Corregido `analisis_a1.py` (distancia al cruzar meta, frenada cortada). Siguiente: A2 a 120 km/h con `--max-gear 3` (122,6 s previstos).

- **2026-11-01 — 110 km/h en 2.ª (V28).** Cumple el criterio (|CTE| máx. 1,42 m, deriva 3,4°), sin cambios de marcha ni punto muerto tras el arranque y 6812 rpm como máximo; vuelta de 128,0 s (previstos 127,9). Es el techo práctico de la 2.ª. Para subir hay que medir la frenada y la bajada de marcha desde la 3.ª (G3).

- **2026-11-01 — Límite lateral 9 a 100 km/h (V27).** Cumple el criterio (|CTE| máx. 1,42 m, deriva 2,9°), vuelta de 135,4 s frente a 135,7 previstos. El coche pide 13-15 m/s² sostenidos, ya en la cota validada de D21; más lateral exige medir el límite (A1.3b). Siguiente: tope de 110 km/h en 2.ª con límite 9 (127,9 s previstos).

- **2026-11-01 — 100 km/h limpio (V26).** La banda donde V16 perdió el coche a los 30 s ahora da dos vueltas sin incidencias: |CTE| máx. 0,81 m, deriva 1,6°, volante casi quieto en rectas, 139,4 s (previstos 139,7). Siguiente: subir el límite lateral del teacher de 7,5 a 9 manteniendo 100 km/h (previstos 135,7 s; real esperado ≈ 13,9 m/s²).

- **2026-11-01 — Gas a fondo a 90 km/h (V25).** Con `--throttle-max 1.0` de 8 a 60 km/h tarda 2,12 s (antes 2,48 s; el modelo prevé 2,10 s), el par sube a 124-133 y el volante sigue cumpliendo (|CTE| máx. 0,85 m, deriva 1,3°). Patinaje trasero fuera del arranque ≤ 5 %. La vuelta no cambia (148,9 s) porque a 90 km/h casi todo va en el tope. Siguiente: 100 km/h (139,7 s previstos).

- **2026-11-01 — 90 km/h cumple y el gas se queda en 0,85 (V24).** `a2_suave_90_...`: |CTE| máx. 0,84 m, deriva 1,1°, vuelta de 149,0 s (previstos 149,6). El usuario pregunta si el arranque llega al 100 %: no, el teacher limita el gas a 0,85 en dos sitios y acelera un 15-20 % menos que a gas a fondo (2,50 s de 8 a 60 km/h frente a 2,10 s del modelo). Opción nueva `--throttle-max` (1,0 = a fondo), 486 tests en `PCARS2-AI` y 73 en `experimental`. Pendiente probarla a 90 km/h.

- **2026-11-01 — 80 km/h cumple el criterio del volante (V23).** Con `--steer-preview-s 0.3` el |CTE| máx. en curva baja de 2,15 a 0,71 m, el rms de curva de 0,64 a 0,23 m y la deriva queda en 1,0°; rectas con volante casi quieto (rms 0,007). Vuelta de 162,8 s (previstos 163,9). Primera banda que pasa el criterio de V19. Siguiente: 90 km/h con la misma receta (previstos 149,6 s).

- **2026-11-01 — Anticipación al 100 % y el adelanto de 30 m (V22).** `a2_suave_80_lat7_slip5_v60_ff0`: CTE máx. 2,15 m (antes 2,55) y deriva 1,3° (antes 3,5°), vuelta 163,0 s (previstos 163,9). Quedan 3 tramos sobre 1,8 m; dos son rectas que acaban en curva donde el volante ya gira 30 m antes de la curva (1,8 · κ(d + 30) · 2,48 = 0,097 de volante) y el coche se desvía hacia el interior. Paso 1d: `--steer-preview-s` (curvatura leída a v · T metros). 484 tests en `PCARS2-AI`, 72 en `experimental`.

- **2026-11-01 — Límite lateral 7,5 y el verdadero cuello de botella (V21).** Con 7,5 la deriva máxima baja a 3,5° (cumple) y el solver acierta otra vez el tiempo (163,6 s medidos, 163,9 previstos), pero el |CTE| máx. sigue en 2,55 m. En 830-950 m el coche no está en el límite de agarre (lateral 8-11 m/s², deriva < 1°): es error de seguimiento. La anticipación de volante aplica solo el 48-68 % de lo que la curva pide (9-10,5 de volante por unidad de κ) y el CTE, ya con menos ganancia por V18, pone el resto. Paso 1c: `--steer-ff-v0-kmh 0` con `--steer-ff-gain 0.003` (factor 1 + 0,003 · v²). 481 tests en `PCARS2-AI`, 71 en `experimental`.

- **2026-11-01 — Primera banda limpia: 80 km/h (V20).** Dos vueltas completas sin incidencias (161,4 s la lanzada, igual que los 161,4 s que predice el solver con μ = 10 y tope 80). Rectas con volante tranquilo (rms 0,012, 0,3 inversiones/100 m); las curvas más cerradas (744-778, 869-941 y 1153-1174 m) siguen pidiendo 14-15 m/s² y suben a CTE 2-3,25 m y deriva 5°, así que no se pasa a 90 todavía. Siguiente: límite lateral del teacher más bajo (7,5) en la misma banda, para ver si el CTE máximo baja de 1,8 m. Arreglado en `analisis_volante.py` el cálculo de metros con varias vueltas (4 tests).

- **2026-11-01 — Primero el volante, después la velocidad (V19).** Observación del usuario: el trabajo se centra en la velocidad y olvida llevar el volante recto y con pocas correcciones. Nueva herramienta `analisis_volante.py` (rms, tasa, inversiones por 100 m, CTE, deriva por rectas/curvas y banda) y criterio provisional para subir de banda. A 100 km/h las rectas tienen 13 veces más inversiones de volante y las curvas 6 veces más tasa que la referencia buena de 60 km/h. Escalera 80 → 90 → 100 km/h con las opciones de V17-V18.

- **2026-11-01 — Paso 1 probado y balanceo a 100 km/h (V18).** `a2_suave_100_lat10_slip5` llega a 2693 m (antes 605): el contravolante resuelve la 3.ª curva (deriva de 40° a 4°). Pero de 2504 a 2650 m el coche se balancea ±2,4 m con periodo de 2,3 s y se sale: no es el contravolante (deriva < 4°) sino el lazo del CTE, inestable a 100 km/h con el retardo del coche. Un modelo lineal con las ganancias de hoy da justo ese periodo y ese crecimiento. Paso 1b: ganancia de CTE ∝ (v0/v)² (`--lat-gain-v0-kmh 60`), opt-in, 480 tests en `PCARS2-AI` y 66 en `experimental`.

- **2026-11-01 — Camino acordado y paso 1 del teacher (V17).** El usuario propone probar PPO autónomo; la recomendación (aceptada) es arreglar el teacher por pasos y dejar el PPO como corrección acotada encima. Paso 1 hecho: contravolante por deriva (`slip_steer_gain`, opt-in, `--steer-slip-gain`), con la ganancia de CTE recortada en un derrape. 477 tests en `PCARS2-AI`, 64 en `experimental`. Falta probarlo en el juego.

- **2026-11-01 — A2.0, primer intento fallido (V16).** `a2_suave_100_lat10`: el teacher pierde el coche en la 3.ª curva (506-570 m) de la 1.ª vuelta: subviraje a 94 km/h, gas a fondo con el coche aún girando a 0,8 rad/s, volante a tope en el sentido de la rotación (sin contravolante) y deriva de hasta 37°. La aceleración lateral real fue de 14-19 m/s² con el límite del teacher en 10. Antes de repetir A2.0 hay que arreglar el teacher (volante con guiñada y deriva, gas con el estado del coche, curvatura máxima en la consigna) y plantear la técnica de curva. Cambié `aislado.py` (`--lat-accel-limit`, `--max-gear` con `a2_*`; 63 tests en `experimental`).

- **2026-11-01 — D2 hecho, sin juego (V15).** `src/linea_optima.py` busca la `n(s)` de menor tiempo previsto (B-spline de 20 m, descenso por coordenadas) dentro del pasillo comprobado: 98,96 → 95,46 s con el ritmo de la IA (−3,5 %), −2,8 % con f = 0,85 y −3,3 % con f = 1; la forma casi no cambia con el ritmo. Es modesta porque el pasillo es estrecho (con ±3 m hipotéticos saldría −6,5 %) y parte de la ganancia viene del suavizado de κ (con κ casi sin suavizar, −2 %). Un primer intento con spline interpolante no se movía nunca (soporte global: las colas rozaban tramos de 0,26 m de pasillo); con B-spline local funciona. `solve` va 5 veces más rápido (listas de Python en lugar de `np.interp` escalar). Informe en `pistas/sugo_gp/informes/informe_linea_optima.html`. 51 tests en `circuito_virtual`.

- **2026-11-01 — G1b validado en el juego (V14).** Con la línea suavizada el coche acelera en 3ª hasta 134,9 km/h (techo) en las 3 vueltas, sin cortes: |CTE| máx. 0,2 m y volante ±0,025 en la recta que antes cortaba a 125 km/h. Cambios 1ª→2ª→3ª en 0,14-0,16 s. Aceleración a 110-130 km/h (2,75 → 2,27 m/s²) igual que la de la IA y la de A1. Sin daño de motor.

- **2026-11-01 — A2 con la IA a ritmo real hecho (V12, V13).** Las `lacc` del archivo de la IA valen 0,46 de lo real: se usan la guiñada y la derivada de la velocidad. Con ellas el solver predice 82,4 s sin calibrar (−15,8 %: la IA va a ≈ 70 % de su envolvente) y **97,90 s con un factor de ritmo f = 0,697** frente a 98,06 s (−0,2 %), correlación de v(s) 0,94. La aceleración y la frenada de la IA coinciden con las de A1. El lateral de la IA a 85 km/h (≈ 19,5 m/s²) supera la cota de D21. 43 tests en `circuito_virtual`.

- **2026-11-01 — Más datos en los logs y la IA a ritmo real (V10, V11).** El usuario sospecha que hay más sobre los márgenes en todos los logs y acierta: 59 logs más con terreno (sin posición; se usan con el CTE) elevan los bordes medidos al 15,4 % (izquierda) y 6,8 % (derecha) de la vuelta, con asfalto comprobado de 5,24 m de anchura mediana. Además, **la referencia original de `sugo_ai.json` era una IA a ritmo real (97,7 s, 14 vueltas, hasta 184 km/h) y está en el historial de git**; exportada a `pistas/sugo_gp/ia_ritmo_real.json`. Va por casi la misma línea que la nuestra (±2 m) y con lateral máximo de 11,9 m/s². Sirve para validar A2. 37 tests.

- **2026-11-01 — D1a hecho (V8, V9).** `src/bordes_logs.py` recorre los 47 logs de esquema 2 y saca

  por metro y lado dos cotas (rueda aún en superficie de carrera y rueda ya fuera);
  `src/informe_mapa.py` hace el informe HTML (distinto del de `experimental`). Resultado: asfalto
  comprobado en toda la vuelta, bordes medidos solo en el 1,7 % (izquierda) y el 0,5 % (derecha).
  Diseño de D1b (sesiones de mapeo) en `docs/PLAN.md`, pendiente de visto bueno. 33 tests en
  `circuito_virtual`.

- **2026-11-01 — D0 hecho (V7).** `src/mapa.py`: eje a 1 punto por metro desde la referencia

  suavizada, `sn_a_xz` / `xz_a_sn` (ida y vuelta con error de s ≤ 0,3 cm y de n ≈ 0 con |n| ≤ 6 m),
  curvatura, pendiente, bordes en NaN (D1) y guardado/carga. n positivo a la derecha y κ positiva a
  la izquierda, iguales que en producción (comprobado con `signed_lateral_error` y
  `ReferenceLine.curvature`). `pistas/sugo_gp/mapa.json` de 164 KB. 26 tests en `circuito_virtual`
  (9 nuevos).

- **2026-11-01 — Nace la carpeta (V1-V6).** El usuario decide un mapa virtual de la pista y una

  línea óptima que sirva para cualquier circuito, con los márgenes y la línea ideal en un gráfico, y
  que el comportamiento aprendido
sea una selección del agente dentro del pasillo. Se mueven aquí el solver de perfil de velocidad, el
suavizado de la referencia, sus tests y el plan. Los logs de sesión se quedan en `PCARS2-AI/logs/`.
Suites: 17 aquí, 61 en `experimental`, 471 en `PCARS2-AI`.
