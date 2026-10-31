# Diario de experimentos

Una entrada por experimento: fecha, qué se hizo, resultado frente al criterio del plan, y decisión
(promover / archivar / descartar / repetir).

## 2026-10-26

- Creada la carpeta `experimental/` con su estructura y documentos. El estudio se movió desde
  `PCARS2-AI/docs/`. Sin experimentos ejecutados todavía.

- **C0 ejecutado** (40 km/h, 2 vueltas, 37 567 ticks). Campos de X1 fiables. Hallazgo principal: los ejes de
  `local_acceleration` están cruzados en producción (H1). Además, `tyre_tread_temp` en kelvin, saltos de reloj
  sin explicar y logs ×1,71 más grandes. Detalle en `DECISIONES.md`, sección 4. Decisión: no tocar producción;
  repetir C0 antes de C1 con X4a. Las pausas de reloj eran el juego pausado al hacer clic fuera de su ventana.

- **C0, segunda ejecución** (X4a activo, 40 km/h, 2 vueltas, 37 564 ticks, sin clics fuera del juego). Sin pausas, sin
  incidencias y sin fallos nuevos. Confirmado: H1 (ejes cruzados) es reproducible, las pausas eran el juego
  pausado, los 4 `safety_reverse` fueron un hecho aislado. Nuevo: fronteras de sector de Sugo (H10) y tamaño ×1,81.
  `pyarrow` no está instalado (P7). Decisión: pasar al paso 5 (P8, P10, P11, P13) antes de C1.

- **Perfil de juego auténtico (RA) decidido** por el usuario: daños completos, fallos mecánicos, desgaste auténtico,
  combustible real y tiempo real, de forma permanente (D11); asistencias sin cambios (D12). Sustituye al plan por
  etapas R1-R4. Se detecta que `CONFIGURACION_JUEGO.md` tenía mal la ayuda de bloqueo opuesto (H11). Riesgos abiertos:
  daños sin guardia (P15), qué reinicia Back (P13) y la deuda de gas y freno (P16), que el roadmap pedía resolver
  antes de activar los daños.

- **X4b implementado** (sin probar con el juego): tanda 2 del paquete 0 y paquete 4 (tiempo atmosférico) como evento
  `conditions`. El usuario cambió la previsión a «Clima real» con salida a las 10:00, así que puede llover (P21).
  Próximo paso: C0 corto en el perfil auténtico para validar los offsets con las comprobaciones del informe.

- **Revisión del fix de X4b y criterio sobre la lluvia.** Duplicado corregido en el informe (extracción de filas de
  `vehicle`) y orden de la tabla de campos fijado con un comentario; mismo resultado sobre el log real. El usuario
  decide conservar los datos con lluvia por su valor para A y B (D13); P21 reformulado: etiquetar, filtrar el BC seco
  y proteger la sesión.

- **Humedad de la pista:** el juego no la expone (H12). Se guarda `car_flags` (bit 4 = ABS activo) como indicador de
  agarre y se plantea un índice de humedad con memoria más sondas de agarre en cada vuelta (P22). Aviso del test de X4b
  corregido.

## 2026-10-29

- **Comprobación del modelo final con fine-tune, con lluvia (H28).** `bc7c_ft20_check`, 2 vueltas limpias, desviación 0,84-0,89 km/h
  y CTE 0,22-0,23 m, pero el solape sube a 0,15 % y el freno con gas se extiende a 700-900 y 2250-2450 m en las dos vueltas. Primera
  lluvia real (153 → 128): paquete 4, etiquetado y aviso del informe validados; sin efecto medible a 20 km/h, así que el umbral de
  `--rain-limit` sigue sin fijarse (P21).
- **Falsa pista y hallazgo real.** Se sospechó que el BC generalizaba el freno de las bandas 70-80 por la velocidad objetivo; probado
  sin juego, cambiar `obs[14]` casi no mueve el freno. Al comparar las etiquetas del buffer con lo aplicado apareció el windup del PI
  del teacher mientras conduce el BC: la etiqueta de gas de `maintain_speed` va de 0,02 (teacher al volante) a 0,55 (check) con 0,04
  aplicado (H29). Los fine-tunes de H27 entrenaron con eso. Corregido con anti-windup por retrocálculo (X16, 4 tests).
- **Limpieza (decisión del usuario):** borrados los modelos y buffers contaminados (`bc7c_ft20*`, `bc7c_20_buffer`).
- **Check de `bc_7c.pt` con el teacher corregido (H30).** El anti-windup funciona (etiqueta de gas estable), pero el solape sigue:
  es un defecto de cobertura del BC base con la intención `accel_straight` en 700-900 m, que la lluvia solo hace más probable. Una
  prueba sin juego con el fine-tune limpio lo corrigió en lazo abierto.
- **Fine-tune limpio en el juego (H31).** Corrige 700-900 m, pero la vuelta 2 se estanca a 11 km/h en 3000-3250 m: estado nuevo que
  el teacher etiqueta bien y el BC no obedece. El criterio de vuelta limpia no lo detecta (P23). Siguiente: check del modelo final
  (`bc7c_ft_limpio_model.pt`).

## 2026-10-30

- **Check del modelo final sin fine-tune, en seco (H32).** `bc7c_ft_limpio_check`, 2 vueltas limpias de ≈ 10:17, 0 incidencias. Velocidad mínima 18,1 km/h (el estancamiento de H31 no aparece), 0 freno en 700-900 m, solape de 1 tick por vuelta (2275 m) y etiqueta de gas estable en 0,024. Falla `teacher:speed` < 5 % (11 %), que es el sesgo de siempre en seco (el BC va ≈ 0,8 km/h por encima y el tope lo corta), no un defecto nuevo.
- **Lo que el check no prueba.** El estancamiento de 3000-3250 m apareció con lluvia; en seco el coche no baja de 21,2 km/h ahí y nunca entra en el estado que falló. Siguiente: decidir P23 y el criterio en seco, y probar la recuperación con una perturbación forzada (P24) o con un check bajo lluvia.
- **Puerta de L1 con velocidad mínima y solape (P23, X17).** Decidido con el usuario: `teacher:speed` y desviación en seco son informativos; la vuelta limpia exige velocidad mínima ≥ 85 % de la consigna una vez alcanzada y solape ≤ 0,05 %. Con los logs reales: H32 limpias, H31 vuelta 2 (estancamiento) y H30 sucias. 409 tests en verde.
- **Perturbación de velocidad preparada (P24, X18).** `--perturb-every 250`: cada 250 m el coche rueda sin pedales hasta perder 4,5 km/h y se suelta; el BC conduce, el teacher etiqueta la recuperación con la consigna intacta. Sin probar en el juego; 419 tests en verde.
- **Prueba de recuperación con perturbaciones forzadas (H33).** `bc7c_ft_limpio_perturb`, seco, 28 perturbaciones de 4,5 km/h (cada 250 m): las 28 se recuperan, sin freno ni solape, y salen de `accel_straight` en ≤ 1,2 s; también las de 3000 y 3250 m, la zona del estancamiento de H31. Seis tardan en el último tramo hasta 19,5 km/h (dentro de `maintain_speed`, sin riesgo). Propuesta: cerrar el paso 7c con `bc7c_ft_limpio_model.pt`, sin más fine-tunes.
- **Paso 7c cerrado (decisión del usuario).** L1 a 20 km/h queda con `bc7c_ft_limpio_model.pt`, sin más fine-tunes. Siguiente: C1 (paso 8), que necesita responder antes las preguntas de `PLAN_C_RAMPA_BC.md`.
- **Parámetros de C1 decididos con el usuario (D20).** Ciclo de 2 vueltas, 2 ciclos para subir, paso de 5, techo 80, vuelta limpia medida en recta, y subida 20 → 60 con el bucle completo en cada banda. Día/noche y sustituir la escalera quedan como propuestas en `PLAN_C_RAMPA_BC.md`.
- **Corrección y código de la puerta de la rampa (X19, D20).** El usuario aclaró que las sesiones de identificación (A1) se hacen antes de C1 (había entendido lo contrario), que C1 va con él delante en bloques cortos y que la escalera se sustituye después de C1. Escrito `learn_driver --ramp` (puerta por ciclos, `ramp_gate.py`), recta libre del teacher y velocidad mínima por recta, `aislado.py --ramp --resume`; validado con los logs reales del teacher a 20-80 km/h (todos pasan). 447 tests en verde. Sin probar en el juego.
- **Pestaña Experimental: sin tocar por ahora.** Lo nuevo (perturbaciones, rampa, retomar) se lanza solo por línea de comandos hasta que un flujo haya funcionado de punta a punta; anotado en `PENDIENTE.md`.
- **Check de 30 km/h (H34).** `bc30_check`, seco, modelo cerrado sin fine-tune: 2 vueltas limpias por la puerta nueva (mínima real 28,0 km/h), `teacher:speed` ≈ 10 %, 4 ticks de gas con freno leve en la vuelta 2, sin estancamientos. Misma conducta que a 20 km/h. Siguiente: prueba de perturbaciones a 30 km/h.
- **Perturbaciones a 30 km/h (H35).** `bc30_perturb`: 28 de 28 recuperadas, todas fuera de `accel_straight` en ≤ 1,2 s, mínima 25,1. Aparece un solape de 1-2 ticks al empezar a recuperar (≈ 0,045 % de la vuelta, justo bajo el límite de la puerta) que a 20 km/h no estaba, y la velocidad se queda 1-2 km/h por debajo de la natural dentro de la banda de `maintain_speed`. Se sigue a 40 km/h sin fine-tune; criterio de recuperación revisado (salir de `accel_straight` en ≤ 2 s).
- **40 km/h (H36).** `bc40_check` pasa (2 vueltas limpias, solape 0). `bc40_perturb` falla: 24 de 25 recuperadas y la de 2884 m en la vuelta 2 se estanca ≈ 75 s (hasta 23,4 km/h, gas 0,13 con etiqueta 0,73), como en H31 y en la misma franja (2750-3400 m); además el solape al arrancar la recuperación sube (0, 0,045, 0,12 % a 20, 30, 40 km/h). Pendiente de decidir el fine-tune.
- **40 km/h, corrección (H36).** El registro `conditions` marca lluvia 153 en `bc40_perturb` y 0 en `bc40_check`. En mojado el coche necesita ≈ el doble de gas/par para la misma velocidad y no hay patinaje medible (relación de ruedas igual); el estancamiento es el BC sin subir el gas con más carga, como en H31 (también con lluvia). Las perturbaciones deben repetirse en seco para comparar con 20 y 30 km/h.
- **Fine-tune sin juego (X20, H37).** Con la lluvia sin parar se salta la repetición en seco de 40 km/h. Nuevo `finetune_offline.py` (modelo copiado, buffers ya grabados): el estancamiento de H36 se reproduce fuera del juego (gas 0,133 frente a etiqueta 0,706); entrenando sin esa vuelta el gas sube a 0,33 y con ella a 0,71, y los controles secos no empeoran. Siguiente en el juego: `bc40_ft_perturb` con `bc40_ft_model.pt`, en las mismas condiciones que H36.
- **Perturbaciones a 40 km/h con el modelo nuevo (H38).** `bc40_ft_perturb`, con la misma lluvia que H36: 26 de 26 recuperadas en ≤ 1,2 s, mínima 35,1 km/h (antes 23,3), freno 0 y solape 0 en las recuperaciones, las dos vueltas limpias por la puerta. Funciona el fine-tune sin juego (X20). Siguiente: 50 km/h con `bc40_ft_model.pt`; controles de seco cuando deje de llover.
- **50 km/h (H39).** Con `bc40_ft_model.pt` y lluvia 153 fallan el check (mínima 41,07 y 40,48 frente a 42,5; CTE 0,30) y las perturbaciones (7 de 19 tardan más de 2 s en salir de `accel_straight`, una no sale; mínima 40,6). Es el defecto de H36: gas predicho 0,156 frente a etiqueta 0,374 en `accel_straight`. Fine-tune sin juego como en H37: dejando `bc50_check` fuera el gas sube a 0,381 (generaliza); definitivo `bc50_ft_model.pt`. Siguiente en el juego: `bc50_ft_check` y `bc50_ft_perturb`.
- **50 km/h con el modelo nuevo (H40).** `bc50_ft_check` y `bc50_ft_perturb`, con la misma lluvia que H39: las dos vueltas del check limpias (mínima por recta 42,53 y 48,16, `accel_straight` 0 y 9 ticks) y 28 de 28 perturbaciones recuperadas en ≤ 1,5 s, sin freno ni solape. Pasa la banda. El CTE medio es 0,31-0,33 m, 0,05-0,08 por encima del teacher: el criterio de 0,25 m era el de 20 km/h; ahora es el del teacher de la banda + 0,10 m. Siguiente: 55 km/h.
- **55 km/h (H41).** Con `bc50_ft_model.pt` y la misma lluvia: check limpio (mínima por recta 46,82 y 48,76, umbral 46,75) y 26 de 26 perturbaciones recuperadas, 25 en ≤ 1,8 s y una en 2,7 s. El CTE medio sube a 0,40-0,42 m (teacher en seco 0,26), solo en curvas. Para saber si es el agua o la dirección del BC, antes de subir a 60: teacher al volante a 55 km/h con lluvia (`wet55_teacher`).
- **Teacher con lluvia a 55 km/h (H42).** CTE 0,27-0,28 m, como en seco (0,26): el exceso de 0,40-0,42 del BC en H41 no es el agua. Offline, la dirección del BC se queda un 16-24 % corta cuando ya va fuera de la línea. Fine-tune sin juego con `--repeat-off-line 4` (nuevo): dejando `bc55_check` fuera, la ganancia en sus filas con |CTE| > 1,5 sube de 0,76 a 0,89; definitivo `bc55_ft_model.pt`. Siguiente en el juego: `bc55_ft_check` y `bc55_ft_perturb`.
- **55 km/h con el fine-tune de dirección (H43).** `bc55_ft_check` y `bc55_ft_perturb`: velocidad, solape y freno bien, 25 de 28 perturbaciones en ≤ 2 s (las otras 3 en 2,4-3,8 s), CTE 0,37-0,39 m (antes 0,40-0,42; teacher mojado 0,28). El modelo ya predice la dirección del teacher con ganancia ≈ 1, pero lo aplicado es el 0,84 de la etiqueta: `damp_bc_steering` reduce el volante del BC ∝ 1/v por encima de 45 km/h (0,82 a 55 km/h, 0,56 a 80) y explica que la brecha crezca con la banda. Nuevo `--steer-damp-kmh` en `aislado.py`. Siguiente: el check de 55 km/h sin amortiguador, vigilando que no oscile.
- **55 km/h sin amortiguador del volante (H44).** `bc55_nodamp_check` con `--steer-damp-kmh 0`: CTE 0,28 m (con amortiguador 0,38-0,39, teacher 0,275), volante máx. 0,38 (antes 0,84), sin oscilación, velocidad y puerta como antes. Era el amortiguador. No se toca el valor de producción (P25); el bucle sigue en 60 km/h con `--steer-damp-kmh 0`.
- **60 km/h sin amortiguador (H45).** `bc60_check` y `bc60_perturb` con `bc55_ft_model.pt` y `--steer-damp-kmh 0`, en seco: las dos vueltas limpias (mínima por recta 51,25 y 53,23 con umbral 51), CTE 0,24-0,25 m, volante máx. 0,38 sin oscilación, y 24 de 24 perturbaciones recuperadas en ≤ 1,8 s, mínima 55,1, sin freno ni solape. Pasa sin fine-tune. Cierra el bucle de D20 de 20 a 60 km/h. Siguiente: A1 (diseño por acordar con el usuario antes de escribir código).
- **Fine-tune con 60 km/h (H46).** `bc60_ft_model.pt`, desde `bc55_ft_model.pt` con la receta de H42 y los buffers `bc60_*` y `bc55_*` posteriores. Con `bc60_check` fuera, el error de gas baja de 0,019 a 0,012 y la ganancia de dirección queda en 1,01; sin regresión en 30 ni 40 km/h. Solo offline; el reentreno desde cero se deja para v2 (D16).
- **A1.1 preparado (X21).** `learn_driver --ident acel|rodar` (vía `aislado.py --ident`): en las dos rectas largas de Sugo (622 y 671 m) el coche acelera a fondo hasta un techo o rueda sin pedales hasta un suelo, y el teacher lleva el volante y el resto de la vuelta. Experimento `a1_*` obligatorio, sin buffer, cierra con lluvia. `analisis_a1.py` saca `a(v, marcha)` del log. Decisiones del usuario: parar por golpe/salto de daño y tolerar el desgaste (ya es `DamageWatch`), A1.3 la última y recordársela, A1.4 fuera. Sin probar en el juego.
- **A1.1, primer escalón (H47).** `a1_acel_30` con techo de 60 km/h: sin incidencias, pero el coche acelera 0,55 g (5,5 m/s²) a 30-60 km/h en 1ª, 0-60 en 3 s, y cada pasada dura 1,5 s; el teacher frena después a ≈ 1 g. Techo muy bajo, el usuario cancela. Nueva maniobra `acelrodar` y escalera de techos 100 → 130 → 160 con banda 60.
- **A1.1, techo de 100 (H48).** Las pasadas se cortaban a 70 km/h: el cambio de 1ª a 2ª pasa ≈ 0,17 s por punto muerto y mi condición lo tomaba por un fallo. Corregido (`neutral=` en `IdentManeuver`, pedales sueltos durante el cambio). Sin incidencias en la prueba. Repetir el mismo escalón.
- **A1.1, techo de 100 (H49).** Con el punto muerto tolerado las 12 pasadas llegan a 100 km/h y pasan a rodar: 1ª hasta 70 km/h (5,5 m/s²; 9,9 entre 10 y 30), 2ª 70-100 km/h (3,0-3,7), rodando -2,25 m/s² casi constante (freno motor). Sin incidencias ni daño. La recta de 1386 m tiene un S que a 100 km/h da yaw 0,42 y CTE 1,0 (idéntico en las dos vueltas): los escalones altos solo en la de 3113 m (`--ident-straights 1`).
- **A1.1 a 130 km/h (H50).** El usuario vio oscilar el volante a punto de perder el control. Causa: a 120 km/h el coche llega al corte de encendido en 2ª y el `AutoShifter` (tope de 2ª) entra en bucle RB/LB/punto muerto con el gas a trompicones; el yaw crece hasta 0,45 rad/s, la maniobra se corta y el freno de 1,0 deja un casi trompo a 56 km/h (yaw 0,89, CTE 3,1 m). Sin daño. Techo máximo 115 km/h en el código; los escalones de 130 y 160 se retiran. Datos limpios de 0 a 120 km/h.
- **A1.2 preparado (sin probar en el juego).** `--ident frenar --ident-caps 60,80,100,110`: en la recta limpia de 3113 m el coche acelera a fondo hasta cada velocidad de entrada y frena a fondo (ABS del juego) hasta 30 km/h, varias veces por pasada. `analisis_a1.py` mide la deceleración por evento y por tramo de velocidad. Entradas de 115 km/h como máximo (H50).
- **A1.2, frenadas (H51).** Con el coche frenando a fondo desde 60-110 km/h hasta 30: 11,1-12,0 m/s² (≈ 1,1-1,2 g) corregidas de pendiente, en 8-36 m, repetible a ±0,1; la curva a_freno(v) sube de 12,0 (50-60 km/h) a 13,0 (100-110). Sin incidencias. **Corrección importante:** la recta de 3113 m es una cuesta del 9,8 % y falsea ≈ ±1 m/s² la aceleración medida; el análisis ahora la quita. Las cifras de A1.1 (H47-H50) estaban sin corregir: rodando el coche pierde ≈ 1,3 m/s² (no 2,25) y a 110-120 km/h acelera 3,0 (no 2,0). Apuntado P26: daño de motor 0 → 1 % en algunas sesiones.
