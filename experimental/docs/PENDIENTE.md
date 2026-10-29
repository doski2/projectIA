# Pendiente para la próxima sesión

> Escrito el 2026-10-28, actualizado el 2026-10-29. Detalle completo en [DECISIONES.md](DECISIONES.md) (D19, pasos 7b y 7c, H25-H29, X7-X16).

## Dónde estamos

- El teacher nuevo (un solo eje de pedal, velocidad de curva física, gas por PI) está validado a 40 km/h con el
  teacher al volante: 0 % de freno, 0 % de solape, velocidad 40,1 ± 0,58 km/h, 2 vueltas limpias (H17).
- Decisión D19: rehacer el BC desde cero con datos del teacher nuevo y volver al currículo en **L1 a 20 km/h**.
- Ya hecho en código: `--teacher-only`, registro pasivo, reetiquetado, guardia de daños, límite de lluvia (apagado).

## Lo primero (reabierto el 2026-10-29: etiquetas de gas contaminadas, H28-H29)

El check del modelo final (`bc7c_ft20_model.pt`, H28) **no pasa**: solape 0,15 % (no 0 %) y el freno con gas, que antes estaba en un
solo punto (≈ 875 m), aparece en 700-900 m y 2250-2450 m en las dos vueltas. Se descartó la causa que se sospechaba (la velocidad
objetivo de las bandas 70-80) y se encontró otra: **el PI del teacher acumulaba integral mientras conducía el BC** y la etiqueta de gas
de los buffers del BC al volante quedó inservible (media 0,02 → 0,55 con 0,04 aplicado, H29). Está corregido en el código (X16, sin
commit); los modelos y buffers grabados antes de la corrección no.

1. **Decidir qué se hace con los buffers contaminados** (`bc7c_20`, `bc7c_ft20`, `bc7c_ft20_check` en `experimental/data/`, y los
   modelos `bc7c_ft20_model.pt` y `bc7c_ft20_check_model.pt`). No se han borrado ni movido. Su freno y su volante valen; su gas, no.
2. **Repetir el check desde `bc_7c.pt`** (sin fine-tune, 2 vueltas, ≈ 21 min, juego en parrilla en Sugo GP, perfil RA, sin hacer clic fuera del juego),
   ya con el teacher corregido:
   `C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --experiment bc7c_anti_windup_check --speed-band 20 --laps 2 --model-src C:\Users\doski\projectIA\experimental\data\bc_7c.pt`
   Criterio de H26: desviación < 1 km/h, tope < 5 %, solape 0 %, CTE ≤ 0,25 m, 0 incidencias. Comprobar además que la etiqueta de gas
   de `maintain_speed` en el buffer nuevo se queda cerca de lo aplicado (≈ 0,04) y no deriva a lo largo de la sesión.
3. **Si el solape o la caída de 700-900 m / 2250-2450 m persisten con `bc_7c.pt`** son un defecto del BC base, no del fine-tune:
   entonces ponderar `accel_straight` / `recover_line` / `brake_overspeed` en la pérdida y reentrenar de cero (la pérdida final de H25 es
   0,000035: ajusta casi perfecto lo que ve, así que el fallo es de cobertura, no de peso). Si desaparecen, repetir el fine-tune con etiquetas limpias
   (`--finetune-every 1 --laps 2`) y volver a comprobar.
4. **Después, C1 (paso 8, `PLAN_C_RAMPA_BC.md`):** rampa 60 → 80 con puerta. Antes hay que responder las preguntas de
   «Por resolver antes de C1» (vueltas por escalón, paso, techo, umbrales de vuelta limpia, día o noche). Tampoco está
   decidido cómo se sube desde 20 km/h: el BC solo se ha probado a 20.

Aviso: el `learn_driver` de aislado cierra la sesión solo al cumplir el objetivo de la etapa (aquí tras 2 vueltas limpias),
aunque `--laps` pida más.

Notas que vienen de la rampa:

- Criterio desde 70 km/h: desviación < 1 km/h **en recta**; en vuelta entera ya no sirve porque el teacher frena en curva (H23).
- A 80 km/h: 0,97 km/h en recta (justo en el límite), CTE medio 0,35 m, volante ≈ 3× más movido que a 20 km/h.
- Cambio de marcha 1ª → 2ª a ≈ 71 km/h (6600 rpm), y dos bajadas a 1ª en curva por vuelta (≈ 57 km/h). El BC no cambia
  de marcha (lo hace `auto_shift`); la marcha entra como entrada (`gear_norm`).
- Aceleración lateral p99 de 10 m/s² desde 70 km/h, con `lat_accel_limit` = 6,5: calibrar el límite.

## Después

- **Registro pasivo** (pestaña, «conduces tú»): un golpe controlado para ver los canales de daño y su escala, y un
  rodaje largo para el desgaste de neumáticos (`tyre_wear` sigue en 0). Reiniciar el coche después: Back no repara.
- ~~Paso 7c: dataset y entrenamiento~~ hecho (H25); queda la prueba al volante de arriba.
- Después, C1 (paso 8) y A1 (paso 9). `universal_v2` con los ejes de aceleración corregidos, tras A1 (D16).

## Cosas pequeñas que no hay que olvidar

- **H11 / P17:** actualizar `PCARS2-AI/docs/CONFIGURACION_JUEGO.md` con el perfil RA y la ayuda de bloqueo opuesto
  (Activ.). Comprobar que sigue activada antes de grabar.
- Calibrar con datos reales: umbrales de daño (`--damage-limit 25`, `--damage-jump 10`), `lat_accel_limit` (6,5 m/s²)
  y la frenada supuesta (4 m/s²), valores del PI (`pi_kp`, `pi_ki`, `pi_ff` puede bajar a ~0,1).
- El informe marca «fallo» en `lat_accel` antiguo (esperado por H1): pasarlo a informativo. No detecta un Back.
- Instalar `pyarrow` (P7) y pasar los logs a Parquet (D6): los logs pesan ×2,25.
- Lluvia (P21): el 2026-10-29 llovió (153 → 128) y quedó validado el paquete 4 y su etiquetado (H28); falta el umbral: una sesión vigilada con lluvia a 50-60 km/h y su referencia en seco con el mismo modelo. `--rain-limit` sigue apagado.
- Daño de motor `engine_damage` 0 → 1 a los ≈ 14-16 min en las cuatro sesiones largas de L1, también en seco y sin golpe: es desgaste por tiempo; tenerlo en cuenta al calibrar `--damage-limit`.
- `pi_kt` (anti-windup, X16) está sin ajustar en el juego; hacer commit de X16 tras el check.
- Pendientes de producción que no son de `experimental/`: guardia de deslizamiento (aviso previo al daño).
