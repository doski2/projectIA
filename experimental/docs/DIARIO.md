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
