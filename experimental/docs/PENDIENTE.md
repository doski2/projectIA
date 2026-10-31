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

Parámetros de C1 decididos el 2026-10-30 (D20, `PLAN_C_RAMPA_BC.md`): ciclo de 2 vueltas, 2 ciclos limpios para subir, paso de 5,
techo 80, vuelta limpia medida por recta. **Orden:** (1) subir de 20 a 60 km/h con el bucle en cada banda, (2) sesiones de
identificación A1, (3) C1 con `--ramp`. C1 va con el usuario delante, en bloques cortos; las sesiones largas sin vigilar son para el PPO.

1. **Hecho en código, sin probar en el juego (X19):** `learn_driver --ramp` (puerta por ciclos, recta libre, velocidad mínima por
   recta) y `aislado.py --ramp --resume`. Validado con los logs del teacher a 20-80 km/h.
2. **Bucle por banda (D20): hecho de 20 a 60 km/h (H33-H45).** 60 km/h pasa check y perturbaciones en seco con `bc55_ft_model.pt` y `--steer-damp-kmh 0` (H45: mínima por recta 51,25 y 53,23, CTE 0,24-0,25 m, volante máx. 0,38 sin oscilación, 24 de 24 perturbaciones en ≤ 1,8 s). **Todas las pruebas con el BC nuevo llevan `--steer-damp-kmh 0`** (P25: el valor de producción no se toca hasta integrar el BC final). **El modelo más reciente es `experimental/data/bc60_ft_model.pt`** (H46: fine-tune sin juego con los datos de 60 km/h; solo offline, sin probar en el juego; `bc55_ft_model.pt` es el que pasó 55 y 60). Para ponerlo a prueba, el par de 60 km/h, en seco o con lluvia, siempre con `--steer-damp-kmh 0`:
   `C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --experiment bc60_ft_check --speed-band 60 --laps 2 --model-src C:\Users\doski\projectIA\experimental\data\bc60_ft_model.pt --steer-damp-kmh 0`
   y luego `--experiment bc60_ft_perturb ... --perturb-every 250`. **Controles de seco pendientes** (con `bc60_ft_model.pt`): check de 30, 40, 50 y 55 y perturbaciones de 20 y 30, para descartar regresiones. **Con lluvia, cuando la haya: el par de 60 km/h** (H45 fue en seco, con menos exigencia que 40-55). Los buffers de perturbaciones se conservan para el BC de v2 (reentreno desde cero tras A1, D16). **El paso 1 de D20 queda cerrado con H46; el reentreno desde cero se deja para v2.**
3. **A1, sesiones de identificación (`PLAN_A_LIMITES_COCHE.md`), antes de C1.** Fases por riesgo (decisiones del usuario, 2026-10-31): A1.1 rodar + aceleración a fondo, A1.2 frenadas a fondo, A1.3 arcos con límite lateral creciente (**la última y con el usuario delante: recordársela y confirmar antes de lanzarla**), A1.4 barridos de volante (fuera hasta B). Parada por golpe o salto de daño; el desgaste progresivo se tolera (`DamageWatch`, `--stop-on-damage`). **A1.1 está hecho en código (X21) y el primer escalón ya se probó (H47): funciona, pero el coche acelera 0,55 g y frena ≈ 1 g, así que los techos van mucho más arriba.** Juego en parrilla en Sugo GP, perfil RA, sin lluvia (cualquier lluvia cierra la sesión), sin hacer clic fuera del juego; el teacher conduce y solo en las dos rectas largas el coche acelera a fondo hasta el techo y rueda hasta el suelo (`acelrodar`). Cada escalón ≈ 8 min con 2 vueltas; el siguiente solo si el anterior sale limpio (sin salidas de pista ni daño, y sin que el coche haga eses en la recta: el volante del teacher solo está validado hasta 80 km/h; si oscila, Ctrl+C):
   1. **Hecho (H48-H49): techo de 100 km/h.** Funciona; 0-100 km/h en 1ª y 2ª y rodando, sin incidencias.
   2. **Retirados los escalones de 130 y 160 km/h (H50):** a ≈ 120 km/h el cambio automático (tope de 2ª) entra en bucle y el coche casi se va (yaw 0,89 rad/s, CTE 3,1 m). El techo máximo es 115 km/h y el código rechaza más. A1.1 queda con datos limpios de 0 a 120 km/h en 1ª y 2ª. **Opcional, para rellenar:** `... --ident acelrodar --speed-band 60 --ident-cap-kmh 110 --ident-floor-kmh 60 --ident-straights 1 --laps 2` da el rodado desde 110 km/h. **Decisión abierta:** (a) pasar a A1.2 (frenadas) con velocidades de entrada ≤ 110 km/h, o (b) antes, hacer un cambio con 3ª y 4ª para ir más rápido (tope por parámetro, bajada segura contra sobrerrevoluciones, el fallo `gear 1` del UDP al corte) y validar el volante del teacher por encima de 80 km/h. Análisis: `python experimental/common/analisis_a1.py PCARS2-AI/logs/learning/<ts>_sugo_gp_l1_linea.jsonl --json ...`. Pendiente de A1.1: rodar en punto muerto para aislar el aire (A2).
   **A1.2, frenadas a fondo: HECHO (H51).** 13 frenadas desde 60-110 km/h hasta 30: 11,1-12,0 m/s² corregidas de pendiente, curva a_freno(v) de 12,0 (50-60 km/h) a 13,0 (100-110). Sin incidencias. `analisis_a1.py` corrige ahora la pendiente (la recta de 3113 m sube un 9,8 %); las cifras de A1.1 (H47-H50) estaban sin corregir y valen las de H51.
   **SIGUIENTE: A1.3, arcos con límite lateral creciente. RECORDAR AL USUARIO Y CONFIRMAR QUE ESTÁ DELANTE DEL JUEGO ANTES DE LANZARLA (es la fase que más puede salirse; decisión del usuario 2026-10-31). Todavía sin diseñar ni escribir.** Arcos candidatos: 228-457 m (radio ≈ 83 m) y 2678-2937 m (radio ≈ 114 m). Dentro del techo de 115 km/h, a 83 m de radio se llega a 12 m/s² laterales como mucho. Hay que decidir con el usuario el diseño (subir `--lat-accel-limit` del teacher por vueltas y qué lo corta). También pendiente: investigar el daño de motor 0 → 1 % (P26).
4. **C1 (paso 8):** rampa de 60 a 80 con `--ramp`, con el usuario delante y en bloques de 2-3 ciclos (`--resume` entre bloques).
5. **Sustituir la escalera L1→L7** por la rampa, después de que C1 llegue limpio a 80 (la escalera queda detrás de una opción).

Datos que hay que conservar en `experimental/data/` (fuera de git, no se pueden recuperar): `bc_7c.pt`, `bc7c_ft_limpio_model.pt`,
los buffers limpios `bc7c_anti_windup_check_buffer.jsonl`, `bc7c_ft_limpio_buffer.jsonl`, `bc7c_ft_limpio_perturb_buffer.jsonl` y
los de cada banda (`bc30_check_buffer.jsonl`, `bc30_perturb_buffer.jsonl`, ...)
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

## Pestaña Experimental (GUI): todavía no

Hoy la pestaña solo lanza C0 (banda, vueltas, «Conduce el profesor») y el registro pasivo. Lo nuevo (modelo de partida,
`--perturb-every`, `--ramp`, `--resume`) se lanza solo por línea de comandos con `aislado.py`, a propósito: no se ha probado en el
juego y los parámetros pueden cambiar. **No integrarlo hasta que un flujo haya funcionado de punta a punta** (el bucle por banda
—check más perturbaciones— o el primer bloque de C1). Entonces añadir: selector de modelo de partida, banda, casilla de perturbaciones,
casilla de rampa con «retomar» y botón para abrir el informe. Decidir también si queda como pestaña de experimentos o pasa a
producción cuando se sustituya la escalera L1→L7.

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
