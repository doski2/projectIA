# Ajuste unificado de las curvas (diseño para revisar, 2026-11-12)

Estado: **propuesta, sin código**. Parte del diseño del 2026-11-08 (PENDIENTE, «Siguiente», punto 8) y de lo aprendido después: V106 (bajada de C5 por el piano), V122-V123 (el techo de patinazo lo pone `exit_adapt` y está cerca del límite útil) y la filosofía de los ajustes (memoria `feedback-filosofia-adapt-por-curva`: por curva, pasos pequeños, parar en el límite físico, no bajar por una vuelta suelta).

## 1. Qué hay hoy y qué falla

Tres adaptadores que heredan de `LatAdapter`: `lat_adapt.py` (límite lateral), `exit_adapt.py` (radio del círculo de gas de salida) y `brake_adapt.py` (deceleración de la frenada). Cada uno lleva un multiplicador por curva, su mapa JSON, cinco opciones y sus propios umbrales. Problemas vistos en sesión:

| Problema | Dónde se vio |
|---|---|
| Baja una curva por **una vuelta suelta** (y se congela 2 vueltas) | V106: C5 bajada a ×0,744 por un patinazo de 3 de 7 vueltas; C7 y C8 bajadas por un \|CTE\| de una vuelta y el mapa no se guardó |
| Mide el patinazo **con la rueda en el piano** | V106: el pico de C5 venía del piano de 865-885 m |
| Patinazo en **razón bruta** (depende de los radios de las gomas) | V122: `spin_bad` 1,005 ≈ 6,7 % real solo porque la razón libre es 0,942 |
| **No recuerda** dónde le fue mal: vuelve a subir al mismo nivel y vuelve a bajar 8 % | Oscilaciones de C3 y C5 en V89 y V106 |
| No distingue **«tope propio»** (el multiplicador máximo) de **«límite físico»** | C2, C3 y C6 en ×1,3 en V99 y V106 |
| Los **topes** son multiplicador × base y `cap` a la vez (redundante) y `--brake-decel-straight` no admite más de 11 | V99: el coche frena a 13,2 m/s² |
| Los tres adaptadores **se pisan**: la misma deriva de una curva puede bajar a la vez el lateral y el gas | Criterios distintos sobre las mismas métricas |
| El mapa **no guarda el reglaje** | Cambios de diferencial, frenos y gasolina sin rastro en el mapa |

## 2. Propuesta

### 2.1 Un solo adaptador con tres magnitudes en valores absolutos

`PCARS2-AI/src/curve_adapt.py`, clase `CurveAdapter`. Por curva (C1-C14 de `curvas.json`) lleva tres **magnitudes**, cada una en sus unidades y con su rango:

| Magnitud | Qué es | Unidad | Rango por defecto | Hoy |
|---|---|---|---|---|
| `lat` | límite lateral del perfil de velocidad en la curva | m/s² | 8,0-14,6 (D21) | base 9,5 × 0,7-1,5, cap 14 |
| `exit` | radio del círculo que topa el gas en la salida | m/s² | 12,6-23,4 | base 18 × 0,7-1,3 |
| `brake` | deceleración de la frenada que prepara la curva | m/s² | 6,6-13,2 (V99) | base 11 × 0,6-1,15 |

- Cada magnitud tiene **una sola** cota superior absoluta (`--curve-adapt-max lat=14.6,exit=23.4,brake=13.2`); desaparecen `max-scale` y `cap`.
- Internamente se sigue pasando al teacher un multiplicador por metro (`set_lat_scales`, `set_exit_scales`, `set_brake_scales`), calculado como valor / base: **el teacher no cambia**.
- `aislado.py`: `--brake-decel-straight` admite hasta 13,5.

Cada magnitud es un **canal** (`LatChannel`, `ExitChannel`, `BrakeChannel`) con tres cosas propias: qué ticks le tocan (su fase), qué métricas acumula y cuándo cuenta como «limpia» o «mala» por sus señales propias. Todo lo demás (vueltas, persistencia, memoria, condiciones, mapa, registro) es común y está una sola vez.

### 2.2 A quién se culpa: cada síntoma va a la fase donde ocurrió

Hoy una deriva alta en C9 puede bajar a la vez el lateral y el gas. En el nuevo, cada tick de una curva cae en **una** fase, la del teacher en ese instante:

- **frenada** (`entry_phase`, pedal de freno pisado) → canal `brake`;
- **paso por curva** (ni frenando ni en salida) → canal `lat`;
- **salida** (`exit_phase`) → canal `exit`.

Las métricas comunes (|CTE| máx., deriva máx., ruedas fuera) se acumulan **por fase**, y la «curva mala» por un síntoma común solo baja la magnitud de la fase donde estuvo el pico. Además, cada canal tiene sus señales propias:

| Canal | Señal propia de «mala» | Señal propia de «limpia» |
|---|---|---|
| `brake` | velocidad al soltar el freno > 1,0 m/s sobre el perfil | < −0,3 m/s, pedal < 0,9 y limitador ≥ 0,8 (como hoy) |
| `lat` | — (solo las comunes) | — |
| `exit` | **patinazo calibrado** > 6,5 % | patinazo ≤ 5,0 % y el tope recortó el gas en ≥ 20 % de la salida |

### 2.3 Criterio común (V89) y umbrales de subida que no castigan a las curvas que ya van bien

- **Mala:** \|CTE\| > 2,3 m, deriva > 5,5°, o una rueda fuera **que no sea** piano, franja o pintura (terrenos 10, 25, 47, 48 y 49, la lista de `amortiguadores.py`).
- **Limpia con margen (puede subir):** \|CTE\| ≤ 1,8 m, deriva ≤ 4,5°, ninguna rueda fuera.
  - Con esto las curvas rápidas (C12-C14, 3,2-4,1° hoy) y las que salen por dentro (C3, C10, C11) pueden subir, cosa que hoy impide el 3° / 1,2 m de `lat_adapt`.
  - C4, C6 y C9 (4,2-5,0° en la salida) no suben `exit` hasta que la deriva baje, que es lo que pide V123.
- **Patinazo con piano:** los ticks con alguna rueda en esos terrenos no cuentan para el patinazo ni para «ruedas fuera».

Los umbrales son una propuesta: se fijan después de pasar los logs (§ 2.8).

### 2.4 Reglas de cambio: persistencia, memoria del último nivel malo y límite

Por curva y por magnitud, al cerrar cada vuelta:

1. **Bajada solo si se repite:** baja si salió mala en **2 de las 3 últimas vueltas evaluadas** (o en la última si es grave: rueda en la hierba o deriva > 7°, que es seguridad). Paso de bajada 6 %. Tras bajar, 2 vueltas congelada (como hoy).
2. **Memoria:** al bajar se guarda `ultimo_malo` = el valor que tenía al ponerse mala.
3. **Subida con aproximación:** si salió limpia con margen en las 2 últimas vueltas evaluadas, sube `min(4 %, mitad de la distancia a ultimo_malo)`. Si esa distancia es menor que el 1 %, la decisión es **«límite»**: no sube más, porque ahí está el límite físico de esa curva con este reglaje.
4. **Tope propio:** si la subida choca con la cota superior absoluta, la decisión es **«tope»**, distinta de «límite». Así el informe dice qué curvas están limitadas por nosotros y cuáles por el coche.
5. **Una subida por curva y vuelta:** si en una curva pueden subir varias magnitudes, sube solo una por vuelta, por turno (`lat` → `exit` → `brake`), para que cada cambio se pueda leer en la vuelta siguiente. Las bajadas no esperan turno.
6. **Re-sondeo:** `ultimo_malo` se olvida si la curva lleva 6 vueltas seguidas limpias en el límite, o al cargar el mapa con condiciones distintas (desajuste > 0,3). Así, si el agarre mejora, se puede volver a probar.

### 2.5 Patinazo calibrado en línea

La razón de rodar libre se mide en la propia sesión: embrague suelto, gas pedido y del juego < 0,2, sin freno, volante < 0,02, misma marcha ±5 ticks y > 60 km/h (lo mismo que `patinazo_traccion.py`). Es una mediana móvil de los últimos 300 ticks válidos. Hasta tener 50, usa la del mapa cargado o 0,942. Patinazo = razón / razón libre − 1.

### 2.6 Mapa de formato 2: valores, memoria, reglaje y condiciones

```json
{
  "version": 2,
  "pista": "sugo_gp",
  "curvas": {
    "4": {"lat": {"valor": 12.17, "ultimo_malo": null, "estado": "sube"},
          "exit": {"valor": 15.23, "ultimo_malo": 16.2, "estado": "limite"},
          "brake": {"valor": 11.0, "ultimo_malo": null, "estado": "igual"}}
  },
  "maximos": {"lat": 14.6, "exit": 23.4, "brake": 13.2},
  "razon_libre": 0.942,
  "reglaje": {"diferencial_deg": 60, "frenos": "55/45", "tc_pct": 10, "abs_pct": 75, "gasolina_l": 12},
  "conditions": {"rain": 0, "track_c": 16, "ambient_c": 12, "tyre_start_c": 84.0, "compound": "Lisos/Lisos/Lisos/Lisos", "tyre_ref_c": 50.4},
  "tyre_by_lap": {"2": 58.0},
  "meta": {"experiment": "...", "lap": 10, "clean_tail": true}
}
```

- **Reglaje:** el UDP no lo trae (salvo el reparto de frenada), así que se lee de `pistas/<pista>/reglaje_vigente.json`, que escribe el usuario al cambiar el garaje. Va a la cabecera del log (la tarea 8c, `log_schema` 5) y al mapa. Al cargar un mapa con otro reglaje: se aplica, se avisa y se olvida `ultimo_malo` (la memoria es de ese reglaje).
- **Condiciones:** el mismo recorte por desajuste de pista y gomas que hoy («solo puede frenar, nunca acelerar»).
- **Formato 1:** `--curve-adapt-load` acepta también los tres mapas actuales y los convierte (multiplicador × base del mapa = valor absoluto). La primera sesión sale de `seco_b140_lim95_cap14_c121314_t21.json`, `seco_b140_exit18_t21.json` y `seco_b140_dec11_t21.json`.
- **Guardar:** como hoy, al cerrar una vuelta, solo si las dos últimas no tuvieron ninguna bajada. Escritura atómica.

### 2.7 Opciones y registro

- `--curve-adapt` (aprende), `--curve-adapt-load <mapa>` (repetible para los de formato 1), `--curve-adapt-save <mapa>`, `--curve-adapt-fixed`, `--curve-adapt-only lat,exit` y `--curve-adapt-max lat=14.6,exit=23.4,brake=13.2`.
- Las opciones antiguas (`--lat-adapt*`, `--exit-adapt*`, `--brake-adapt*`) siguen funcionando como alias: construyen un `CurveAdapter` con solo ese canal y sus valores de hoy. Los comandos de PENDIENTE no se rompen.
- Un evento `curve_adapt` por vuelta: por curva y magnitud, el valor, la decisión (sube / baja / igual / congelada / límite / tope / sin datos / fijo), el **porqué** (qué umbral, en qué fase) y las métricas.
- **Log (`log_schema` 5), por tick:** la fase del teacher (`entry` / `mid` / `exit`), `exit_bound`, la velocidad del perfil `v*(s)` y el patinazo calibrado. Sin esto los logs no se pueden volver a pasar por el código con fidelidad.

### 2.8 Validación sin juego antes de la primera sesión

1. **Tests:** se portan los de `test_lat_adapt.py`, `test_exit_adapt.py` y `test_brake_adapt.py` al canal correspondiente (mismos casos, mismos resultados con los umbrales de hoy) y se añaden tests nuevos para la persistencia 2 de 3, `ultimo_malo` y el paso que se acorta, «límite» frente a «tope», el turno de subida, el filtro de piano, el patinazo calibrado, el mapa de formato 2 y la carga de los de formato 1.
2. **Repetición de logs** (`experimental/common/repetir_ajuste.py`): pasa un log por `CurveAdapter` vuelta a vuelta y dice qué habría decidido. En los logs de `log_schema` 4 la fase sale de `teacher_reason` (`brake_overspeed` = frenada, `accel_exit` = salida) y no hay `exit_bound` ni `v*`: el canal `exit` supone que el tope recortaba y el canal `brake` no se puede juzgar. Casos que tiene que cumplir:
   - `222926Z`: **no** debe bajar C2-C7 (diseño del 2026-11-08);
   - `20261109T221139Z` (V106): **no** debe bajar C5 por el piano ni C7 y C8 por una vuelta suelta;
   - `225939Z` y `000717Z`: comparar decisiones con las del código actual y explicar cada diferencia;
   - V120-V122 (mapa congelado): con `--curve-adapt` simulado, que C6 salga «tope» y C4 / C9 no suban `exit` por la deriva.
3. ruff y basedpyright limpios.

### 2.9 Protocolo de sesión «aprender, congelar, medir»

- **Aprender:** 10 vueltas con `--curve-adapt` desde los mapas actuales (formato 1); guarda al final si la cola está limpia.
- **Medir:** 8 vueltas con `--curve-adapt-fixed` y el mapa guardado; se juzga con `metricas_volante.py` (vueltas 4-6 y 4-8) frente a 1:46.960 (V122).
- **La primera vez, escalonado:** si en la sesión de aprender oscila alguna curva, se repite con `--curve-adapt-only lat`, luego `lat,exit` y luego las tres.
- **Después:** cada cambio de reglaje (barra trasera, amortiguadores, presiones) va con su «aprender y medir», porque el mapa congelado no aprovecha el cambio (V99).

## 3. Lo que queda fuera

- `--steer-adapt` (punto 5b): con este esquema sería un cuarto canal (ganancia de la anticipación por curva; C2 es el primer caso, V121), **después** de que los tres funcionen.
- El teacher, el perfil de velocidad y el limitador de frenada no cambian.

## 4. Decisiones del usuario (2026-11-12, noche)

1. **Persistencia: 2 de las 3 últimas vueltas evaluadas** (más la bajada inmediata por seguridad de § 2.4).
2. **Umbrales comunes: los decide Claude.** Se empieza con los propuestos (mala 2,3 m / 5,5°, limpia 1,8 m / 4,5°) como **provisionales**, y se fijan con la repetición de logs de § 2.8: si un caso obligatorio no se cumple, se mueve el umbral y se apunta por qué.
3. **Reglaje: sí**, `pistas/<pista>/reglaje_vigente.json` escrito a mano por el usuario al cambiar el garaje.
4. **Código antiguo: se retira** (`lat_adapt.py`, `exit_adapt.py`, `brake_adapt.py` y sus tests, una vez portados) para no confundir ni acumular código sin uso. Las opciones antiguas quedan como alias en `learn_driver.py` y `aislado.py`, que construyen el `CurveAdapter` con un solo canal; los mapas de formato 1 se siguen pudiendo cargar.

## 5. Orden de trabajo (sin juego salvo el último paso)

1. `curve_adapt.py` con los tres canales y las reglas comunes, más los tests portados y los nuevos.
2. `log_schema` 5: fase, `exit_bound`, `v*` y patinazo calibrado por tick, y el reglaje en la cabecera.
3. `repetir_ajuste.py` y los casos de § 2.8.
4. Integración en `learn_driver.py` (opciones nuevas y alias) y `aislado.py` (opciones y tope de `--brake-decel-straight`).
5. ruff, basedpyright y tests completos; comando de la sesión «aprender» validado sin ejecutar `aislado.py`.
6. Con juego: la sesión «aprender» y después la de «medir».
