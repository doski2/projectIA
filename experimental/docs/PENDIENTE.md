# Pendiente para la próxima sesión

> Escrito el 2026-10-28. Detalle completo en [DECISIONES.md](DECISIONES.md) (D19, pasos 7b y 7c, X7-X14).

## Dónde estamos

- El teacher nuevo (un solo eje de pedal, velocidad de curva física, gas por PI) está validado a 40 km/h con el
  teacher al volante: 0 % de freno, 0 % de solape, velocidad 40,1 ± 0,58 km/h, 2 vueltas limpias (H17).
- Decisión D19: rehacer el BC desde cero con datos del teacher nuevo y volver al currículo en **L1 a 20 km/h**.
- Ya hecho en código: `--teacher-only`, registro pasivo, reetiquetado, guardia de daños, límite de lluvia (apagado).

## Lo primero (paso 7c: fine-tune del BC nuevo en L1 a 20 km/h)

La rampa del teacher (7b) está **completa** (20 → 80 km/h, H17-H24). El BC nuevo `experimental/data/bc_7c.pt`
(H25) ya se probó al volante **sin fine-tune** en L1 a 20 km/h (H26): 2 vueltas limpias, 0 incidencias, CTE 0,19-0,21 m,
pero velocidad 20,8 ± 0,9 km/h (teacher 20,07 ± 0,32) con el tope de velocidad actuando el 13 % del tiempo, gas medio
doble que el teacher y solape residual del 0,01-0,03 %.

Lo que falta es el fine-tune (DAgger): conducir el BC con el teacher nuevo etiquetando y reentrenar con lo que sale.
**Lanzamiento (X15, programado y probado con tests; sin probar aún con el juego).** Con el juego en parrilla en Sugo GP,
perfil RA, sin hacer clic fuera del juego, desde cualquier carpeta:
`C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --experiment bc7c_ft20 --speed-band 20 --laps 4 --model-src C:\Users\doski\projectIA\experimental\data\bc_7c.pt --finetune-every 1`
Hace fine-tune tras cada vuelta con la base nueva (teacher nuevo) y el buffer de lo que el BC conduce, y el informe
final compara las vueltas. El modelo resultante queda en `experimental/data/bc7c_ft20_model.pt`; como el último
fine-tune puede perderse al salir, el modelo guardado refleja hasta la penúltima vuelta. Cada vuelta tarda ≈ 7 min
más ≈ 1 min de fine-tune.
Criterio de salida: desviación de velocidad < 1 km/h sin depender del tope (< 5 % de `teacher:speed`), solape 0 %,
CTE ≤ 0,25 m, 0 incidencias.

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
- Lluvia (P21): solo se valida cuando llueva; `--rain-limit` está apagado hasta entonces.
- Pendientes de producción que no son de `experimental/`: guardia de deslizamiento (aviso previo al daño).
