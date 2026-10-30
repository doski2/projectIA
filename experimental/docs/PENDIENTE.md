# Pendiente para la próxima sesión

> Escrito el 2026-10-28, actualizado el 2026-10-30. Detalle completo en [DECISIONES.md](DECISIONES.md) (D19, pasos 7b y 7c, H25-H33, X7-X18, P23-P24).

## Dónde estamos

- El teacher nuevo (un solo eje de pedal, velocidad de curva física, gas por PI) está validado en toda la rampa 20 → 80 km/h con el
  teacher al volante (H17-H24). Decisión D19: rehacer el BC con sus datos y volver al currículo en **L1 a 20 km/h**.
- `bc_7c.pt` (H25) es el BC base. Es limpio, porque se entrenó con datos de la rampa.
- **Windup del PI resuelto (H29, X16, commit `e5ace06`):** antes, con el BC al volante, la etiqueta de gas del teacher se inflaba hasta 0,55.
  Ahora se queda en ≈ 0,06 (verificado en el juego, H30). Los buffers y modelos contaminados se borraron.
- **El BC tenía huecos de cobertura en L1 a 20 km/h** (700-900 m en H30, 3000-3250 m en H31). `bc7c_ft_limpio_model.pt` ya no los
  muestra: en seco conduce sin estancarse ni frenar con gas (H32) y se recupera de 28 perturbaciones forzadas de 4,5 km/h repartidas
  por la pista, también en 3000-3250 m (H33). Queda un último tramo lento hasta la consigna en 3 zonas, dentro de `maintain_speed`.
  **Paso 7c cerrado por el usuario el 2026-10-30 con ese modelo, sin más fine-tunes.**

## Lo primero (paso 8: C1)

El paso 7c está **cerrado** (2026-10-30): `bc7c_ft_limpio_model.pt` es el BC de L1 a 20 km/h. Se llegó con el check en seco (H32), la
puerta de L1 con velocidad mínima y solape (X17, commit `d039a0f`) y la prueba de recuperación con perturbaciones (H33, X18,
commit `ae56bc8`: 28 de 28 recuperadas sin freno ni solape).

1. **Cerrar lo que queda de P23 antes de C1:** decidir si la puerta de la rampa 60 → 80 usa la misma velocidad mínima (en curva el
   teacher frena, H23: la mínima de toda la vuelta no vale) y si se añade `accel_straight` con freno.
2. **C1 (paso 8, `PLAN_C_RAMPA_BC.md`):** rampa 60 → 80 con puerta. Antes hay que responder las preguntas de «Por resolver antes de C1»
   (vueltas por escalón, paso, techo, umbrales de vuelta limpia, día o noche). Tampoco está decidido cómo se sube desde 20 km/h: el BC
   solo se ha probado a 20. La prueba de perturbaciones (`--perturb-every`) se puede repetir en cada banda para comprobar la
   recuperación antes de subir.

Datos que hay que conservar en `experimental/data/` (fuera de git, no se pueden recuperar): `bc_7c.pt`, `bc7c_ft_limpio_model.pt`,
los buffers limpios `bc7c_anti_windup_check_buffer.jsonl`, `bc7c_ft_limpio_buffer.jsonl` y `bc7c_ft_limpio_perturb_buffer.jsonl`
(contienen recuperaciones etiquetadas) y los
buffers de la rampa (`c0_log`, `teacher_*`). Los `*_base.jsonl` se regeneran solos.

Aviso: el `learn_driver` de aislado cierra la sesión solo al cumplir el objetivo de la etapa (aquí tras 2 vueltas limpias),
aunque `--laps` pida más. Las esperas del fine-tune (≈ 65 s por ajuste, coche parado en meta) provocan pausas del juego de 0,2-0,6 s: es
la CPU ocupada, no un clic fuera de la ventana, aunque el informe lo diga.

Notas que vienen de la rampa:

- Criterio desde 70 km/h: desviación < 1 km/h **en recta**; en vuelta entera ya no sirve porque el teacher frena en curva (H23).
- A 80 km/h: 0,97 km/h en recta (justo en el límite), CTE medio 0,35 m, volante ≈ 3× más movido que a 20 km/h.
- Cambio de marcha 1ª → 2ª a ≈ 71 km/h (6600 rpm), y dos bajadas a 1ª en curva por vuelta (≈ 57 km/h). El BC no cambia
  de marcha (lo hace `auto_shift`); la marcha entra como entrada (`gear_norm`).
- Aceleración lateral p99 de 10 m/s² desde 70 km/h, con `lat_accel_limit` = 6,5: calibrar el límite.

## Después

- **Registro pasivo** (pestaña, «conduces tú»): un golpe controlado para ver los canales de daño y su escala, y un
  rodaje largo para el desgaste de neumáticos (`tyre_wear` sigue en 0). Reiniciar el coche después: Back no repara.
- C1 (paso 8) y A1 (paso 9). `universal_v2` con los ejes de aceleración corregidos, tras A1 (D16).

## Cosas pequeñas que no hay que olvidar

- **H11 / P17:** actualizar `PCARS2-AI/docs/CONFIGURACION_JUEGO.md` con el perfil RA y la ayuda de bloqueo opuesto
  (Activ.). Comprobar que sigue activada antes de grabar.
- Calibrar con datos reales: umbrales de daño (`--damage-limit 25`, `--damage-jump 10`), `lat_accel_limit` (6,5 m/s²)
  y la frenada supuesta (4 m/s²), valores del PI (`pi_kp`, `pi_ki`, `pi_ff` puede bajar a ~0,1, `pi_kt` del anti-windup).
- El informe marca «fallo» en `lat_accel` antiguo (esperado por H1): pasarlo a informativo. No detecta un Back.
- El informe atribuye las pausas del juego a «clic fuera de la ventana» también cuando coinciden con la espera del fine-tune (CPU):
  distinguirlas.
- Instalar `pyarrow` (P7) y pasar los logs a Parquet (D6): los logs pesan ×2,25.
- **Lluvia (P21):** el paquete 4 y su etiquetado están validados (H28, H30, H31: 153 constante o decreciente, pista 19-20 °C). Falta el
  umbral: una sesión vigilada con lluvia a 50-60 km/h y su referencia en seco con el mismo modelo. `--rain-limit` sigue apagado.
  Con lluvia el mismo modelo pide más gas (0,068 frente a 0,029); no se separó de la temperatura de pista.
- Daño de motor `engine_damage` 0 → 1 a los ≈ 14-16 min en las seis sesiones largas de L1 (H31: la sexta), también en seco y sin golpe: es
  desgaste por tiempo; tenerlo en cuenta al calibrar `--damage-limit`.
- Pendientes de producción que no son de `experimental/`: guardia de deslizamiento (aviso previo al daño).
