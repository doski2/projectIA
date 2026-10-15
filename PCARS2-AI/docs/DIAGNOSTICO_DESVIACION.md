# Diagnóstico: hierba a ~441 m con CTE ~3 m (Sugo L1)

## Qué vimos en los logs (teacher puro, sin BC)

En sesiones F1 / hybrid / aprender el primer `off_surface` ocurre siempre cerca de **441 m** de
`lap_distance`, con:

- **CTE / |signed_cte| ~3,2 m** (no 8 m).
- **heading_err ~0** (el coche va paralelo a la referencia).
- Volante del teacher **~+0,45** (corrigiendo hacia la derecha) durante cientos de metros **sin

  recentrar**.

La referencia `sugo_ai.json` en 441 m es la **posición XYZ del piloto humano** en el momento en que
el juego marcó `lap_distance≈441`. No es una línea teórica distinta: si el humano no tocó hierba, el
centro del coche humano pasó por asfalto ahí.

## Causa raíz (mecánica)

1. **Deriva lateral estable** desde ~250 m: `signed_cte` se queda en **−2,8…−3,5 m** (coche **a la

   izquierda** de la vuelta grabada).

2. El teacher usa PD suavizado (`k_cte=0.12`, `steer_smooth=0.35`). Con rumbo ya alineado, la

   corrección lateral **llega a un equilibrio** lejos del trazado humano.

3. **CTE ~3 m es al centro del coche**, no a las ruedas. Con ~1 m de semi-ancho, una rueda puede

   estar **~4 m** respecto a la misma referencia → UDP `sTerrain=GRASS` en una rueda aunque
   `recover_line` (solo a **6 m**) no haya actuado.

No es un fallo de “la grabación estaba mal”: es **control lateral insuficiente a 20 km/h** respecto
a la misma polyline.

## Cómo comprobarlo

### Sin volver a pista (log antiguo)

```bat
```

Mira la tabla por tramos: si **300–450 m** tienen `signed` ~−3 m **antes** del pico de
`off_surface`, encaja con deriva, no con ref corrupta.

### Con más detalle (próxima sesión)

Desde `PCARS2-AI`, en **PowerShell** hay que usar `.\` delante del `.bat`:

```powershell
```

(CMD clásico: `validar_f1.bat --speed-target 20 --diag-track`)

Tras ~90 s, Ctrl+C. Cada tick lleva `track_diag`:

- `signed_cte` / `cte` en el tick (teacher); en `track_diag` solo si hace falta
- `pos_x`, `pos_z` vs `ref_x`, `ref_z`
- `terrain` [FL,FR,RL,RR] y `wheels_grass`
- `closest_lap_distance` y `lap_distance_mismatch_m` (descarta desfase UDP distancia vs XY)

Eventos `[Safety]` en consola incluyen `terrain` en el JSONL.

## Cambio en código

Perfil por defecto `--safety-profile l1_margin` (F1, imitación y aprender). `--safety-profile
strict` restaura el freno con una sola rueda.

| Situación                                      | Acción                                                                                                                                                                             |          |                                |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------------ |
| `signed_cte`                                   | Positivo = a la derecha de la línea grabada; negativo = a la izquierda. `cte` es el valor absoluto.                                                                                |          |                                |
| `\                                             | signed_cte\                                                                                                                                                                        | > 2.5 m` | `k_cte × 2.25` para recentrar. |
| 1 o 2 ruedas en hierba                         | Motivo `edge_grass`: gas `MAINTAIN_THROTTLE` (0,2, el mismo que el crucero), freno 0 aunque hubiera `brake_overspeed`, más dirección hacia la línea. No cuenta como `off_surface`. |          |                                |
| 3 o más ruedas en hierba, o 3 fuera de asfalto | Freno de safety (`off_surface`).                                                                                                                                                   |          |                                |
| CTE > 6 m, stuck, sin progreso                 | Recuperación como antes.                                                                                                                                                           |          |                                |

En el log `20261010T191358Z` casi todo el tiempo en hierba eran **dos** ruedas; con umbral de dos el
coche seguía frenando igual que en `strict`.

## Qué no arregla el fine-tune

El BC no corrige esto mientras el teacher no mantenga el coche sobre la polyline humana: las
etiquetas buenas son “teacher ya desviado” o frames en safety sin calidad.
