# Pendiente de circuito_virtual

Estado al cierre del **2026-11-08** (V1-V100). Lo que no es del circuito (rampa del BC, PPO, daño
de motor P26, controles de seco, reentreno v2) está en `experimental/docs/PENDIENTE.md`. El plan está
en `docs/PLAN.md`, las decisiones en `docs/DECISIONES.md` y la historia en `docs/DIARIO.md`.

**Qué significan las «V»:** cada Vnn es una entrada del registro de decisiones (hoy V1-V100), no una
versión del software. La versión del software es el commit de git, que cada sesión guarda en la
cabecera de su log. Este documento recoge solo el estado actual y lo que sigue; las cifras de sesiones
anteriores son referencia (están en `DECISIONES.md`) y cada sesión nueva se juzga contra el criterio de
volante de más abajo, no contra la anterior.

## Dónde estamos

- **Estado del código (2026-11-08):** todo commiteado en local y **sin subir a GitHub**; solo queda suelto el `1.tzip` de la raíz (se puede borrar). Hoy no hubo cambios de código, solo reglaje del coche, un mapa de agarre hecho a mano (`seco_b140_lim95_cap14_c121314_t21.json`) y documentación. Los logs llevan en la cabecera el hash de `HEAD`: commitear antes de lanzar.
- **Tests en verde:** `circuito_virtual` 79, `experimental` 132, `PCARS2-AI` 601 (ruff limpio en todo lo tocado; en `experimental` quedan los avisos antiguos de `resumen_sesion.py` y `test_resumen_sesion.py`). Se lanzan con `pytest` dentro de cada carpeta.
- **Mejor vuelta: 1:48.898** (`233729Z`, 2026-11-07, banda 150 con el diferencial a 60°). **Receta vigente (V97-V99): banda 150, ≈ 1:49.02 de media** (`233729Z` 1:49.032 y `000717Z` 1:49.019, vueltas 3-8): línea `a1mu9c12`, límite lateral 9,5 con el mapa del agarre de tope 13 y **C12, C13 y C14 a 14 m/s²** (`seco_b140_lim95_cap14_c121314_t21.json`), contravolante `--steer-slip-gain 8`, gas de salida `--exit-circle 18` con su mapa, frenada `--brake-decel-straight 11` con su mapa, los tres ajustes por curva congelados y el coche con el diferencial a 60° y los frenos a 55/45 (comando en «Comandos vigentes»). Referencias: banda 150 con tope 13 1:49.38; banda 145 1:50.264; banda 140 1:51.20 (mejor 1:51.114).
- **Teacher** (`teacher_controller.py`, `learn_driver.py`): cada opción es opt-in y su valor por defecto es el de producción. Los tres ajustes por curva (`--lat-adapt`, `--exit-adapt`, `--brake-adapt`) comparten esquema: un multiplicador por curva que se mide al cerrar cada vuelta y se aplica en la siguiente, con vueltas congeladas y mapa que se guarda y se carga con las condiciones de pista y gomas.
- **Mapas versionados** (`circuito_virtual/pistas/sugo_gp/`; un archivo por condiciones, no mezclarlos): `mapas_lat_adapt/` (`seco_b140_lim95_cap12.json` 16 °C; `…_cap12_t21.json` y `…_cap13_t21.json` 21 °C, `seco_b140_lim95_cap14_c121314_t21.json` es el vigente: el de 13 con solo C12, C13 y C14 a ×1,4737 = 14 m/s², hecho a mano el 2026-11-07, V97), `mapas_exit_adapt/seco_b140_exit18_t21.json` y `mapas_freno_adapt/seco_b140_dec11_t21.json`. Con otras condiciones el programa recorta el margen sobre 1,0 y nunca acelera más que el ajuste normal (V88).
- **Archivos locales no versionados** (4,5 MB cada uno): `circuito_virtual/pistas/sugo_gp/` con `sugo_smooth.json`, `sugo_optima_a1mu9{,b,c15,c12}.json`. Cómo regenerarlos, en «Comandos vigentes».
- **Informes:** `informe_c0.py <log>` genera el HTML con zoom (`informe_zoom.py`); si el usuario cierra antes de que se genere, regenerarlo. **Second Monitor** (segundo monitor) graba cada vuelta; `experimental/common/second_monitor.py --log <log>` la cruza con nuestro log.

## Histórico: noche del 2026-11-06 (seco, pista 21 °C, ambiente 14 °C): de 1:52.234 a 1:51.164 (V89-V91)

**Criterio nuevo (decisión del usuario):** con el límite lateral subido (14-17 m/s²) **V19 ya no vale** en las sesiones con `--lat-adapt` o con un mapa cargado. Se juzga por el **tiempo de vuelta** y las **temperaturas de la pista y de las gomas**; deriva, |CTE| y ruedas fuera quedan como dato y como seguridad (el pasillo mide ≈ 5,4 m, 1,9-2,0 m de |CTE| aún deja margen). Tiempos en minutos y segundos (1:51.164). Detalle y cifras por vuelta en V89-V91 (`DECISIONES.md`).

| Sesión | Qué cambia | Mejor vuelta | Media (vueltas 3 en adelante) |
| --- | --- | --- | --- |
| `192821Z` (control) | mapa de 21 °C congelado, tope 12, exit 14,6, frenada 10 | 1:52.222 | 1:52.3 |
| `203752Z` | exit 16 | ≈ 1:51.9 | ≈ 1:52.0 |
| `210840Z` | tope 13 con `--lat-adapt` aprendiendo | 1:51.533 | 1:51.631 |
| `215729Z` | exit 18, mapa de tope 13 congelado | 1:51.386 | 1:51.484 |
| `222024Z` | frenada 11 | 1:51.249 | 1:51.291 |
| `223943Z` | `--exit-adapt` aprendiendo (10 vueltas) | 1:51.191 | 1:51.286 |
| `231522Z` | `--brake-adapt` aprendiendo | **1:51.164** | 1:51.262 |

- **Lo que ganó tiempo:** el tope 13 del agarre (−0,4 s; converge en la vuelta 3 con el mapa cargado, lateral hasta 16,5 m/s²), el exit 18 (−0,15 s) y la frenada a 11 (−0,19 s; la hierba tras C8 pasa de 90 a 1 tick). Los dos ajustes nuevos, en seco, son seguros y casi neutros.
- **Traseras:** no suben con más gas; se estabilizan en 39-43 °C con la pista a 21 °C (36-38 °C ayer con 16 °C). Delanteras 57-60 / 53-57 °C, el lado interior 2-4 °C más caliente que el exterior.
- **El |CTE| máx. de 1,86-2,02 m en las salidas de C7, C2, C3 y C1** (véase el análisis del volante de abajo: **no sale ancho, sale por dentro**).
- **Análisis del volante (2026-11-07, sin juego, `231522Z` y `223943Z`, vueltas 3-8; comprobado con la posición del coche frente a la línea, no solo con el signo del CTE):** en 13 de las 14 curvas el pico de |CTE| tras el vértice es **hacia dentro** (0,8-1,9 m; C7 +1,9, C1 +1,6-1,9, C11 1,8, C9 1,7, C2 1,0-1,5); solo C3 va **hacia fuera** (1,4-1,7 m en el vértice, entrada con subviraje). Las dos sesiones coinciden a ±0,1 m: es determinista, no ruido. Ninguna rueda sale de la pista en esos tramos (las ruedas fuera de la sesión son las franjas del lado izquierdo de C4-C5, 1400 m y 2440 m). Mecanismo: el gas entra en el vértice (0,4 → 0,7 en 20 m con unos 13-15 m/s² laterales), la deriva sube de 1° a 3-4° (cola fuera), el coche gira más de lo que pide la línea y acumula 4-7° de error de rumbo hacia dentro; el volante cae de 0,33 a 0,06 en 10 m (contravolante −0,1 a partir de 3° de deriva, más rumbo y CTE restando a una anticipación que sigue en 0,19) y la recuperación es lenta (ganancia de CTE ∝ (70/v)²). Experimento natural con las 6 sesiones de la noche (el gas de salida pasó de exit 14,6 a 16 y a 18, con otros cambios a la vez: tope 13 y frenada 11): CTE hacia dentro en C7 1,23 → 1,70 → 1,66 → 1,83 → 1,89 m, deriva 2,0 → 2,9 → 2,5 → 4,4 → 4,3°; C1 0,92 → 1,64 m, 1,6 → 3,3°; C9 0,99 → 1,39 m, 1,8 → 4,3°. Es decir: el exit 18 compró ≈ 0,15 s y costó ≈ 0,5 m de CTE hacia dentro y ≈ 2° de deriva. Causa del volante confirmada solo en parte (hay otros cambios mezclados). La anticipación de volante no es la causa global: la guiñada real frente a la de la línea en el vértice es 0,8-1,05 salvo en C3, C7, C11 y C13 (1,3-1,4).
- **Pico de C3 de la vuelta 4** (deriva 6,4-6,5°, la trasera izquierda un 5 % más lenta que la derecha): salía en las dos sesiones con exit 14,6; con exit 16 y 18 sale 1 vez en unas 40 vueltas (vuelta 8 de `215729Z`). Causa sin demostrar.
- **Second Monitor** trae las temperaturas izquierda / centro / derecha de las gomas, que nuestro UDP lee a 0 (V89).

## Al retomar (cierre del 2026-11-08)

**Dónde se quedó:** récord **1:48.898**; receta vigente (V97-V99) a **1:49.02 de media** (banda 150, mapa de agarre de tope 13 con C12-C14 a 14 m/s², contravolante 8, exit 18, frenada 11), con los tres ajustes por curva **congelados** (mapas aprendidos a banda 140) y este **reglaje del coche en el garaje: diferencial trasero «punto muerto» 60° y equilibrio de frenos 55/45** (presión de frenos 90 %, peso 45/55 y presiones 1,25 / 1,15 bar sin tocar; el log no guarda el reglaje: ponerlo en el nombre del experimento). Todo commiteado en local; **no se ha subido a GitHub** (el usuario dice «sube»). El detalle de cada paso está en `DECISIONES.md` V92-V99.

**Vídeo y bordes (2026-11-08, tarde):** pasillo medido por vídeo de 10,87 m frente a 5,4 m comprobados y −0,62 s previstos para la trazada (V102); lo que queda, con comandos, está en la tarea 1b de «Tareas, por orden». **Aviso:** el piano es superficie legal (D10 de `video_vuelta/docs/DECISIONES.md`).

**Lo ganado el 2026-11-07 (seco, pista 21 °C, ambiente 14 °C, una variable por sesión):** de 1:51.20 a 1:49.02 de media (−2,2 s).

| Paso | Media de las vueltas 3-8 | Efecto | V |
| --- | --- | --- | --- |
| Receta de la noche anterior (contravolante 5, banda 140) | 1:51.284 | referencia | V90 |
| `--steer-slip-gain 8` | 1:51.200 | −0,08 s, vueltas más regulares | V92 |
| Banda 145 | 1:50.264 | −0,94 s (rectas largas) | V93 |
| Banda 150 | 1:49.389 | −0,87 s | V94-V95 |
| Mapa de agarre con C12-C14 a 14 m/s² (congelado) | 1:49.092 | −0,29 s | V97 |
| Diferencial, punto muerto 60° | 1:49.032 | −0,06 s (ruido) | V98 |
| Frenos 55/45 | 1:49.019 | −0,01 s (el perfil sigue en 11 m/s²) | V99 |

**Descartado:** `--lat-adapt` aprendiendo a banda 150 con tope 14 (V96): los umbrales de «curva mala» de V19 (|CTE| 1,8 m, deriva 4,0°) bajan C2-C7 y C9 y la media sube a 1:50.15. **Lo que manda hoy:** la banda de velocidad en las rectas (coincide con el techo de la 3.ª marcha, 151,5 km/h) y los topes de los mapas; las dobles frenadas de C2, C4 y C8 salen del perfil óptimo y no se tocan.

### Antes de lanzar cualquier sesión

0. `git status` limpio (el `1.tzip` suelto de la raíz no cuenta; se puede borrar). Comprobar en el garaje el **reglaje** de arriba y la pista / ambiente (21 / 14 °C); si algo cambia, ponerlo en el nombre del experimento y apuntar el «desajuste de condiciones» que escribe cada ajuste al empezar.

### Tareas, por orden

1. **Sesión A: control del día** (la receta vigente tal cual, 8 vueltas, debe dar ≈ 1:49.0): confirma condiciones y reglaje y es la referencia de B. Comando «RECETA VIGENTE» en «Comandos vigentes». **Grabarla en vídeo (D1c, bordes por vídeo):** cámara de capó o de parachoques, HUD oculto, campo de visión fijo, 1080p y 60 fps con bitrate alto, empezando desde parado (sirve para sincronizar con el log); anotar la ruta del archivo y el nombre del log.
1b. **Vídeo de la vuelta y bordes de la pista (`video_vuelta/`, V101-V102; detalle en `video_vuelta/docs/DECISIONES.md` D2-D10).** **Hecho el 2026-11-08:** gráficos cerrados (`comprobar_graficos.py`, perfil en `video_vuelta/perfiles/graficos.json`); vídeo automático a 30 km/h de 2 vueltas (`capturas/sugo_gp/formula_r/2026-11-08_2/`); cámara calibrada (`calibrar_camara.py`: altura 1,009 m, cabeceo 5,88°, 70° horizontales); detector de línea blanca y proyección sobre el mapa (`bordes_video.py`): **10,87 m de ancho de límite frente a 5,4 m comprobados**; mapa de bordes `mapa_bordes_video.json`; estudio de trazada V102: **−0,62 s previstos con el pasillo unión (lo pisado ∪ vídeo) y margen 0,6** (margen 1,0: +0,24 s, no gana); etiquetas automáticas y primer segmentador (IoU 0,94, `video_vuelta/modelos/pasillo_v1.pt`); segundo vídeo (12.41) comparado (D8); **aviso (D10): el piano (terreno 10, 25...) es superficie legal; las constantes de D6 valen donde el asfalto pasa directo a hierba y el vídeo subestima el límite donde hay piano.** **Para la próxima sesión, por orden:**
   - (a) **Vuelta manual para verificar los 0,18 m** (solo log, sin vídeo; el juego puede ir en ventana: al volver a grabar hay que dejarlo en pantalla completa 1920×1080 y pasar `comprobar_graficos.py`). Lanzar `C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\circuito_virtual\src\sesion_manual.py --lado izq --laps 1` y dar la vuelta **metiendo las ruedas en la hierba**, a un lado y al otro, en tramos de 20-30 m sin piano (cruzar la línea hacia un piano no da cruce). Después `python video_vuelta/src/verificar_limite.py <log de PCARS2-AI/logs/manual/>`: error mediano ≈ 0 = las constantes valen; si no, ajustar `SESGO_CAMARA_M` y `LIMITE_FUERA_M` en `bordes_video.py` y repetir `bordes_video.py` (D6: `--cada 6 --fila-min 440 --z-max 22`) y los estudios de V102.
   - (b) **Grabar 2 vueltas con 90° de campo de visión** (solo cambia eso; siguen valiendo 1920×1080, pantalla completa, HUD y línea de carrera apagados): `Start-Sleep -Seconds 60; C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --teacher-only --speed-band 30 --experiment a2_video_auto_30_fov90_l2 --laps 2` con la grabación de Radeon puesta antes de que acaben los 60 s. Después: manifiesto nuevo (con `campo_de_vision_horizontal_deg: 90`), `sincronia.py --manifiesto`, `calibrar_camara.py --escribir`, comprobar la focal proyectando los límites sobre fotogramas (`etiquetas.py`) y recalcular la máscara de carrocería (`etiquetas.carroceria` está medida para 70°).
   - (c) **Cabeceo del chasis con `ride_height` del log** para corregir el sesgo del borde derecho a alta velocidad (−0,25 m a más de 110 km/h, D8) y repetir D6 con la cámara de D9 (`Camara` por defecto aún lleva 1,02 m y 5,98°).
   - (d) **Prueba de antialiasing** (hoy 0): 20 s de grabación y comparar hasta qué distancia se detecta la línea.
   - (e) **Borde exterior del piano** (la hierba tras el piano): por color o con una clase «legal» en la red.
   - (f) **Segundo circuito** (lo elige el usuario) con el procedimiento de D7: referencia de la IA con `reference_recorder.py --source ai`, mapa, vuelta a 30 km/h, `bordes_video.py`, `crear_dataset.py` y reentrenar validando con una pista no usada. Sin esto la generalización de la red no está probada.
   - (g) **Versión manual a 30 km/h donde solo gira el usuario:** script que lleve gas y freno con el DS4 virtual; sin probar si el juego acepta el gas del DS4 virtual con el volante de otro dispositivo.
   - (h) **Mejoras de la red:** entrada de 512×288 (lo lejano está limitado por 256×144), más fotogramas, y los cuadros de la línea de salida la confunden.
   - (i) **Decidir el margen al borde** (V102: manda más que el ancho) y, con eso, **preguntar** antes de escribir el pasillo unión en `observaciones_logs.json` (archivo versionado) y regenerar la línea (`linea_optima.py`).
   - (j) La sesión A del teacher grabada con las condiciones de D2 sigue sin hacerse (tarea 1).
2. **Sesión B: más deceleración en el perfil** (única variable: mapa de frenada ×1,15 = 12,65 m/s² en las 14 zonas, congelado, con el reparto 55/45; el coche hace 13,2 m/s²). Comando «Sesión B» en «Comandos vigentes». Con el usuario atento y Ctrl+C a mano: puede llegar pasado a alguna curva. Qué mirar: tiempo frente a A y por curva (¿ganan C2 y C11, que perdían con 55/45?), ABS y razón traseras/delanteras, deslizamiento por rueda (`deslizamiento.py`, scratchpad: delante ≈ 19 % y detrás ≈ 3 % hoy), frenada pasada (velocidad a la entrada de cada curva), franja a 1400-1420 m (salida de C8) y el pico de deriva de C5. Si gana pero alguna zona sobra o falta, **sesión C**: el comando de estrés (`--brake-adapt` aprendiendo desde el mapa ×1,15, guardando) y luego congelar el mapa guardado y medir.
3. **Mapa a mano de C10 y C11** (mapa de agarre con C10 ×1,368 = 13 m/s² y C11 ×1,263 = 12 m/s², el resto igual; congelado): hoy C10 y C11 van con 11,0 y 9,5 m/s² de límite mientras el coche hace 14,2 y 13,0; ambos salen 1,6 m por dentro (V97). Una variable.
4. **Código sin juego, con tests: ajuste unificado** (diseño en «Siguiente», punto 8). Es lo que permite que cada cambio de reglaje se evalúe tras reaprender los mapas (V99: el mapa congelado no usaba el freno extra).
5. **4.ª marcha y banda 155** (cada +5 km/h ha dado ≈ 0,9 s, pero a 150 el 3.ª está en el limitador de 6995 rpm): validar primero la aceleración en 4.ª con `--ident acel` a 150-160 km/h y el cambio de marcha; solo después la vuelta.
6. **Presiones** (neumáticos 0,2-0,3 bar por clic; con «SIMÉTRICO» desactivado se ajusta cada lado): las traseras van 17 °C más frías que las delanteras y el lado derecho 3-4 °C más frío que el izquierdo (V98). Una variable por sesión, la última de los reglajes.
7. **Si llueve:** repetir la pareja ajuste / control en mojado; un mapa de seco no se aplica en mojado (V88). `--exit-adapt` y `--brake-adapt` no se han visto en mojado.
8. **Pequeños, sin juego:** (a) leer nosotros las temperaturas izquierda / centro / derecha de las gomas (offsets 256 / 264 / 272 de `sTyreTempLeft` / `Center` / `Right`; nuestro UDP las da a 0; las lee Second Monitor); (b) por qué el lado interior de las delanteras va 2-4 °C más caliente; (c) guardar el reglaje y los mapas aplicados en la cabecera del log (`log_schema` 5); (d) regenerar el informe `informe_lineas_teacher.py`; (e) zona muerta del contravolante a 2° (código); (f) pico de C3: razón RL/RR y freno entrando en bajada.
9. **Trazada (la línea óptima): el siguiente bloque grande tras la frenada y el reglaje** (orden del usuario del 2026-11-07: frenos, volante, banda de velocidad y trayectoria). Límites de la línea actual (`sugo_optima_a1mu9c12.json`): (a) **el pasillo**: se optimiza dentro de lo que se comprobó recorrido (asfalto de 5,4 m de mediana; el centro del coche queda a ±1,25 m con semivía 0,85 y margen 0,6) cuando el ancho real declarado es de 10-12,5 m (V78): la línea no puede usar el exterior ni el piano de salida que el usuario ve en C1 y C4; (b) **el agarre**: el solver supone μ 9 y el coche hace 13-16,5 m/s² (mapa por curva de ×0,88 en C3 a ×1,47 en C12-C14); (c) **el seguimiento**: el coche sale 0,8-1,9 m por dentro de la línea tras el vértice (V92), así que parte de lo que se ve en pantalla no es la línea sino el coche. Orden: (1) D1b, medir los bordes: el usuario conduce a mano con `sesion_manual.py` (dos sesiones de 3 vueltas, una por lado; V77-V78) o se fija una cota prudente del ancho; (2) **estudio sin juego del potencial**: línea con el pasillo ampliado y la μ de los mapas, tiempo previsto por el solver frente al de la línea actual con el mismo solver (si la ganancia prevista es < 0,3 s no merece las sesiones); (3) regenerar la línea (`linea_optima.py`, «Regenerar las líneas locales») y sesión de una variable con los mapas reaprendidos: la línea nueva cambia curvaturas y velocidades de curva, así que **los mapas de agarre, gas y frenada hay que reaprenderlos**, y por eso conviene hacerlo **antes** del BC v2 y del conjunto de datos «oro». La banda, la frenada y el reglaje siguen valiendo mientras tanto. **Estudio de potencial hecho el 2026-11-08 (V100, sin juego, `linea_optima.py` con `--margen` negativo, mismos parámetros que `a1mu9c12`: μ 9, tope 125 km/h, salida en una carpeta temporal): tiempo previsto por el solver 118,447 s con el pasillo actual, 117,665 s con 1 m más por lado (−0,78 s, −0,66 %) y 117,587 s con 2 m más (−0,86 s): casi todo está en el primer metro.** Con 1 m más, la línea mete el vértice más por dentro en C1, C2, C6-C9 y C14 y abre más la salida en C2, C4, C7, C8 y C11; no hay un patrón único de «salida por fuera» (en C1 la salida va por dentro). Es un modelo (μ 9, 125 km/h), el coche no sigue la línea con exactitud y el metro extra solo existe si la pista es de verdad más ancha. **Alternativa a conducir a mano (el usuario no tiene ganas de D1b manual): ensanchado progresivo con el teacher** (`--margen` 0,6 → 0,1 → −0,4), sesiones normales de 8 vueltas y mirar los ticks de hierba (terreno 7) por tramo; `bordes_logs.py actualizar` va ampliando el asfalto comprobado. Riesgo: en 1350-1450 m la línea ya pasa a ≈ 1 m del borde izquierdo (muro): hay que impedir que se ensanche ahí (hace falta una guarda en el código del pasillo) y empezar a banda baja con Ctrl+C a mano.
10. **Más adelante, no ahora:** BC v2 y PPO, después de la trazada (ver «Después»); suspensión y presiones para mantener las gomas en temperatura (cambia los mapas: etiquetarlos con el reglaje).

## Cómo analizar una sesión (el usuario dice «analiza la última sesión»; no pasa nada más)

Todo con `PYTHONIOENCODING=utf-8` y el Python del proyecto; el log más reciente está en `PCARS2-AI\logs\learning\`. Tiempos en minutos y segundos.

1. `experimental\common\estadisticas_vueltas.py <log>`: por vuelta, tiempo, ruedas fuera, velocidad, |CTE|, deriva, laterales, pedales, temperaturas de gomas y frenos y la pista.
2. `experimental\common\resumen_sesion.py <log>`: vueltas, tramos con |CTE| > 1,8 m o deriva > 4° (dato, no veredicto), frenos, cambios de marcha, ruedas fuera. **No decir «no cumple V19» como conclusión** con los ajustes.
3. `experimental\common\second_monitor.py --log <log> [--desde m --hasta m]`: tiempos de la app y temperaturas izquierda / centro / derecha de cada goma por vuelta; empareja la sesión por los tiempos de vuelta (la app arranca antes que el log).
4. `experimental\common\pedales_sesion.py <log> --vueltas 3,5,7`: frenadas, deceleración, inversiones del gas, rebotes.
5. Eventos del log de los ajustes: `lat_adapt`, `exit_adapt` y `brake_adapt` (multiplicadores y decisiones por vuelta, con las métricas de cada curva) y `*_start` (mapa aplicado o ignorado y el desajuste de condiciones).
6. Ruedas fuera: separar el terreno 48 (piano de C4) y 10 (franjas) de la hierba (7) antes de dar una cifra.
7. Si el usuario cierra antes de que se genere el informe: `experimental\common\informe_c0.py <log>`.

## Histórico reciente (V87-V88)

- **2026-11-05 (seco, pista 16 °C):** banda 135 → 1:55.9 y banda 140 → 1:54.9 con la receta de entonces; con `--lat-adapt` y tope 12 en 10 vueltas converge a 1:52.1 (−2,9 s frente al control, V87). El mapa guardado de 16 °C (V88) se reconstruyó de ese log. En mojado (2026-11-04) el ajuste funcionó con una réplica por lado. Cifras completas en V87.
- **Recetas de 125 km/h (V85-V86):** línea óptima `a1mu9c12` a 125 km/h, 1:58.6 estable con la técnica de pedales, `--lat-gain-v0-kmh 70` y el recorte de picos (60 m / 8 km/h); superada por la de 140 km/h. Sus comandos están en el historial de git de este archivo (antes del commit de V90).

## Seco y mojado: no se mezclan

Todo lo de este documento (receta, base de comparación, V19, solver μ 9, previsiones) es **en seco**. Las sesiones en mojado son exploratorias, van aparte y nunca se comparan con la base ni se juzgan con V19.

- **Cómo se distinguen:** el registro `conditions` del log trae `rain` (0 en seco; 153 el 2026-11-04) y las temperaturas. El informe `informe_lineas_teacher.py` los separa por ese campo (tabla en seco y tabla en mojado), no por el nombre. Aun así, el experimento lleva `a2_mojado_` en el nombre.
- **Los datos de seco no se tocan:** los buffers de BC (`c0_log`, `teacher_<banda>`) no incluyen los `a2_*`, y las tablas de A1 / `parametros_a1.json` salen de logs concretos.
- **Primera sesión en mojado** (2026-11-04, `213459Z`, banda 100, límite lateral 6, sin recorte de picos, 2 vueltas): 146,55 / 146,58 s, sin bloqueo ni ABS; la vuelta 1 limpia (|CTE| 0,78 m, deriva 1,2°), la 2 con un patinazo en C5-C6 (|CTE| 4,66 m, deriva 8,3°, hierba y franja a 930-950 m) y salidas en C8 y C10-C11. Hipótesis sin comprobar: sin el recorte el coche acelera entre C5 y C6 y entra en C6 pasado. Si se repite, una variable: añadir `--profile-peak-min-m 60` (el umbral de 8 km/h está calibrado para 9,5, no para 6).
- **Segunda sesión mojada** (`220304Z`, con `--profile-peak-min-m 60 --profile-peak-min-kmh 8`): el recorte arregló C5-C6 (|CTE| de 4,66 a 2,00 m con las gomas igual de frías), pero la vuelta 2 siguió sin quedar limpia por el bamboleo de la recta C6→C7 (|CTE| 2,6 m, deriva 5,6°).
- **`--lat-adapt` (límite lateral por curva, `PCARS2-AI/src/lat_adapt.py`, opt-in):** cada curva (C1-C14) tiene un multiplicador sobre `--lat-accel-limit` que se ajusta al cerrar cada vuelta (el cambio se nota en la vuelta siguiente; la vuelta 1 no cuenta): limpia con margen (|CTE| ≤ 1,2 m, deriva ≤ 3°, 0 ruedas fuera) sube un 4 %; fuera de V19 baja un 8 % y se congela 2 vueltas; topes 0,7 a `--lat-adapt-max-scale` (1,15) y `--lat-adapt-cap` (10 m/s²). El log guarda un evento `lat_adapt` por vuelta. Recalcular el perfil cuesta ≈ 0,06 s.
- **Primera sesión con `--lat-adapt`** (`223106Z`, mojado, límite base 6, máx. 1,4, 6 vueltas): las vueltas 2-4 salieron sucias (|CTE| 2,65-2,86 m, deriva hasta 9,2°) y las 5-6 mucho mejor (1,49 y 1,37 m; 2,4° de deriva; 143,9 y 143,4 s; 104 y 38 ticks fuera). C4, C6 y C8 bajaron a ×0,85 y C1-C3 y C10-C14 subieron hasta ×1,22. **No es una prueba limpia:** la vuelta 4 ya tenía C6 al mismo ×0,85 que la 5 y seguía mal, y las gomas se estabilizaron en ≈ 20 °C. Falta el **control**: las mismas 6 vueltas sin `--lat-adapt`. En la recta C6→C7 el bamboleo nace de salir de C6 con 1,6 m de error, no del gas (razón traseras/delanteras 1,00-1,09); en la vuelta 6 la banda de 100 km/h ya manda (gas 0,56, `maintain_speed`).
- **Control sin `--lat-adapt`** (`225613Z`, mismo comando, mismas condiciones: `rain` 153, pista 13 °C, gomas 19-22 °C en las vueltas 5-6): se queda sucio hasta el final. Vueltas 5-6 con ajuste frente al control: |CTE| máx. 1,49 / 1,37 frente a 2,64 / 2,73 m; deriva 4,2 / 2,4° frente a 7,0 / 6,0°; ticks con rueda fuera 104 / 38 frente a 265 / 301; tiempo 143,9 / 143,4 frente a 145,0 / 145,6 s. En las vueltas 2-4 el ajuste no gana (está aprendiendo). **El ajuste funciona, con una réplica por lado:** conviene repetirlo una vez más antes de darlo por cerrado.
- **Herramienta nueva `experimental/common/estadisticas_vueltas.py <log>...`:** mínimo / media / máximo por vuelta de velocidad, |CTE|, deriva, lateral y longitudinal, gas, freno, |volante|, gomas, frenos y presión, más tiempo, ticks con rueda fuera y la lluvia y temperaturas al empezar cada vuelta. Con ella se ve que **las condiciones empeoran en las 4 primeras vueltas y luego se estabilizan**: gomas (media) 57 → 27 → 22 → 21 → 20 → 19 °C, frenos 274 → 139 °C, presión 1,51 → 1,39 bar. El control llegó a volante 1,00 (tope) en la vuelta 4; con el ajuste, 0,85 en la 3 y 0,27-0,32 en las 5-6.
- **Apuntado: lo mismo para freno, gas y volante** (mismo esquema que `--lat-adapt`: medir cada zona al cerrar la vuelta y ajustar en la siguiente, con topes y opt-in): (a) **freno:** la deceleración `--brake-decel-straight` por zona de frenada, a partir de la actividad del limitador de deslizamiento y de la razón traseras/delanteras; (b) **gas:** control de tracción (reducir el gas con la razón traseras/delanteras o la deriva), aunque en la recta C6→C7 mojada la razón fue de 1,00-1,09 y no habría ayudado ahí, y el tope de salida por zona; (c) **volante:** ganancia dependiente del agarre estimado (hoy solo hay contravolante por deriva y ganancia por velocidad); no antes de ver si el ajuste lateral deja limpias las rectas. Idea del usuario: en seco y con buena temperatura, el ajuste vuelta a vuelta apuraría cada curva y el calor de conducir mantendría las gomas dentro de su ventana; falta medir esa ventana (tabla temperatura de gomas → lateral máximo limpio, de los logs de seco y mojado).
- **Tabla temperatura de las gomas → agarre lateral limpio** (`experimental/common/tabla_gomas.py`; 14 logs secos y 4 mojados de `log_schema` 3, vueltas ≥ 2, > 40 km/h, «limpio» = deriva ≤ 4°, |CTE| ≤ 1,8 m, sin ruedas fuera): **en seco** el lateral limpio es p95 11,0-11,2 y p99 12,2 m/s² en todo el rango 40-59 °C, con solo 1-2 % de ticks no limpios por encima de 7 m/s²: no se ve efecto de la temperatura en ese rango (no hay datos por encima de 60 °C salvo la vuelta 1). **En mojado** el techo es p95 7,7-8,7 y p99 8,4-10,0 m/s², y sube con la temperatura (de 15-19 a 30-34 °C, +1 m/s² en p95): ≈ 70 % del seco. Un límite base de 6 pide ≈ 8,7 m/s² reales (el coche hace ≈ 1,45 veces el límite), coherente con ese techo. Cautela: es agarre **conseguido**, no el máximo posible; depende de lo que el teacher pidió, y en mojado la temperatura va unida al número de vuelta y a si el ajuste estaba encendido (los tramos de 20-34 °C son sobre todo las vueltas 2-4, sucias).
- **Cómo juzgar las sesiones con `--lat-adapt`:** el |CTE| ya no es la métrica principal, porque el ajuste toma las curvas de otra manera para ir más rápido. Se mira, por este orden: tiempo de vuelta, ticks con rueda fuera, deriva máxima, si los multiplicadores se estabilizan (cambios por vuelta), y el |CTE| solo como límite de seguridad (V19, que el propio ajuste respeta: una curva con |CTE| > 1,8 m baja). Dejarlo horas no mejoraría sin techo: converge al borde del criterio y lo frenan los topes (×1,15 y 10 m/s²), la banda y el agarre físico.
- **Qué limita ahora el ajuste (2026-11-05):** en la sesión mojada con ajuste (vueltas 5-6) la regla `maintain_speed` ocupa el **36 %** de los ticks a 100 km/h de media (en la receta seca, 22,5 % a 125 km/h): la **banda de velocidad es hoy el límite que manda**, más que el límite lateral. Subir los límites de las curvas no gana tiempo mientras la banda no se mueva. Otros candidatos, sin borrar nada (son redes de seguridad): el terreno 48 (pintura sobre hormigón, el piano de C4) cuenta como rueda fuera y puede estar bajando C4 para siempre (V78 sigue sin decidir); `edge_grass` y `safety_off_surface` esconden la causa de un bamboleo al cortar el gas (conviene registrar cuándo actúan).
- **Orden previsto para añadir ajustes (uno por vez, cada uno con su pareja ajuste / control):** (1) confirmar el límite lateral con una segunda pareja; (2) banda de velocidad (110 en mojado) con el ajuste lateral encendido; (3) freno: deceleración por zona; (4) gas: tope de salida por curva (`--exit-circle` por zona) y control de tracción solo si el log muestra patinaje trasero; (5) volante: ganancia según agarre, el último y el más delicado. Todo junto solo cuando cada pieza haya ganado sola; esa sesión se compara con la mejor combinación anterior, no con la receta base.
- **Estado de los ajustes (2026-11-07):** el del agarre está validado en mojado (una réplica por lado) y en seco (V87, V90); `--exit-adapt` y `--brake-adapt` (V91) solo en seco, donde son seguros y casi neutros: en mojado queda por ver. El orden previsto para añadir ajustes (agarre → gas de salida → frenos → volante) va por el último.
- **Próxima en seco:** el volante y la banda de velocidad (ver «Al retomar»).

## Estado por tema

| Tema | Estado | Qué falta |
| --- | --- | --- |
| A2.0 con la línea óptima `a1mu9c12` | **Receta vigente (V97): banda 150, 1:49.09 de media, récord 1:49.006** (límite lateral 9,5 con mapa de tope 13 y C12-C14 a 14, contravolante 8, exit 18, frenada 11). Superó la de 140 (1:51.20, V90-V92) y la de 125 km/h (1:58.6, V85-V86) | Volante (salidas por dentro, C3), límite de C10 y C11, diferencial y reglaje (V97), recalcular la línea con el agarre aprendido |
| Techo en 3.ª (G2) | **Limpio hasta 150 km/h** (V93-V95: velocidad máx. 151 km/h, ABS 0, volante rms 0,009 en rectas). El motor llega a 149,9 km/h | 4.ª marcha para pasar de 150 (sin validar) |
| Frenadas fuertes | Limitador por deslizamiento cerrado (objetivo 0,25, memoria 0,85, V44-V55); **11 m/s² en la receta (V90)**, sin bloqueo (ABS 0, razón ≥ 0,94) | Prueba de estrés (frenadas a ×1,15), mojado, tabla de frenada del solver (V55) |
| Técnica de pedales (`--pedal-technique`, `--brake-profile`, `--exit-circle`, `--profile-peak-min-m`; V65-V90) | Terminada y en la receta: frenada con perfil, gas de salida con tope por el círculo (**exit 18**), recorte de picos 60 m / 8 km/h | Inversiones del gas en curva (23-28 por vuelta), rebotes del gas en 1285, 2393 y 2655 m, F10-F13 de `TECNICA_CONDUCCION.md` |
| Curvas numeradas (V70) | `pistas/sugo_gp/curvas.json` (C1-C14, tabla en `TECNICA_CONDUCCION.md` §9); el informe HTML, `resumen_sesion.py`, `pedales_sesion.py` y los tres ajustes las usan. C12-C14 son un solo viraje largo (V78) | Regenerar con `python circuito_virtual/src/curvas.py` si cambia el mapa |
| Registro de sesión | `log_schema` 4 (V87): `lat_accel` lateral real, `long_accel`, capa / carcasa / aire de la goma, compuesto; `tyre_left_c` / `center` / `right` salen siempre 0 | Leer esas tres con Second Monitor o arreglar nuestra lectura (ver «Al retomar» 7a) |
| Modelo del volante | `experimental/common/modelo_volante.py` acierta a más de 108 km/h y no ve las entradas en curva cerrada | Reajustarlo con cada log nuevo; base del estudio del volante |
| Bordes de la pista | Pasillo comprobado por las ruedas (mediana 5,4 m); el usuario declara 10-12,5 m reales (V78, sin verificar). Terreno 48 = pintura sobre hormigón (probablemente legal) | D1b en pausa (V78) |
| Grabador manual de D1b (V77) | `circuito_virtual/src/sesion_manual.py`; 7 tests, sin ejecutar contra el juego | Sesiones del usuario (en pausa) y un extractor de bordes con ventana |
| Ajuste del límite lateral (`--lat-adapt`, V87-V88, V90) | **Validado en seco y en mojado.** Tope 12 (V87) y **tope 13 (V90): converge en la vuelta 3 con el mapa cargado, 1:51.5, lateral hasta 16,5 m/s²**; guardar y cargar el mapa con las condiciones (V88) funciona | Regla de subida de C3 y C11 (exige \|CTE\| ≤ 1,2 m), tope por encima de 13 (el usuario lo deja por ahora), pareja en mojado |
| Gas de salida (`--exit-circle 18`, `--exit-adapt`, V89-V91) | Exit 18 en la receta (−0,15 s sobre 16, −0,35 s sobre 14,6). `--exit-adapt` validado en seco: funciona y guarda el mapa, **sin ganancia medible** | Segunda versión o solo mojado |
| Frenos (`--brake-decel-straight 11`, `--brake-adapt`, V90-V91, V98-V99) | 11 m/s² en la receta (−0,19 s); `--brake-adapt` validado en seco (sube C5, C8, C10); **reparto 55/45: el coche frena 13,2 m/s² pero el perfil sigue en 11 (−0,01 s)** | Sesión B (mapa ×1,15), zonas saturadas, mojado |
| Second Monitor (V89) | `experimental/common/second_monitor.py` lee sus `.zLap` y empareja la sesión con nuestro log; trae las temperaturas izquierda / centro / derecha de las gomas | Cruzarlo por vuelta y distancia; delantero interior 2-4 °C más caliente |
| **Volante** | Contravolante 8 en la receta (V92); el coche sale por dentro tras el vértice de 13 de 14 curvas (0,8-1,9 m) por la cola que suelta el gas del vértice; el eje trasero es rígido (V97) | Zona muerta del contravolante a 2° (código), ajuste unificado; C3 (S de ±1,9 m) |
| Reglaje del coche (V98-V99) | Diferencial trasero por embragues con punto muerto a **60°** (−0,06 s) y frenos **55/45** (sin cambio de tiempo); presión de frenos 90 %, peso 45/55 y presiones 1,25 / 1,15 bar de fábrica; el log no guarda el reglaje | Presiones y peso; guardar el reglaje en el log (`log_schema` 5) |

## Comandos vigentes

Los lanza el usuario (en seco, delante del juego, Ctrl+C si el coche oscila o se sale). Siempre con
la ruta absoluta del Python del proyecto.

**RECETA VIGENTE, SESIÓN DE REFERENCIA (V90-V97): línea óptima `a1mu9c12`, banda 150, `--steer-slip-gain 8`, límite lateral 9,5 con el mapa de tope 13 y C12-C14 a 14 m/s² (congelado), exit 18 con su mapa (congelado), frenada 11 con su mapa (congelado), técnica de pedales, `--lat-gain-v0-kmh 70` y recorte de picos 60 m / 8 km/h; 8 vueltas, ≈ 1:49.0, con el coche en el garaje con el diferencial a 60° y los frenos a 55/45 (V98-V99).** Cada opción está explicada en la tabla de «Receta del teacher». Las sesiones se hacen cambiando **una** opción de este comando y un nombre de experimento nuevo (prefijo `a2_`, acabado en `_l8`…). Si las condiciones cambian, los mapas se recortan solos (V88); para aprender un mapa nuevo se quita el `-fixed` correspondiente y se añade `--…-save <ruta nueva>`:

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --teacher-only --speed-band 150 --max-gear 3 --lat-accel-limit 9.5 --steer-ff-gain 0.003 --steer-ff-v0-kmh 0 --steer-ff-cap-kmh 100 --steer-preview-s 0.3 --steer-slip-gain 8 --lat-gain-v0-kmh 70 --throttle-max 1.0 --brake-decel-straight 11 --brake-overspeed-straight-ms 2.5 --brake-slip-limit 0.25 --brake-slip-hold 0.85 --pedal-technique --brake-profile --brake-circle 10 --exit-circle 18 --profile-peak-min-m 60 --profile-peak-min-kmh 8 --exit-adapt --exit-adapt-fixed --exit-adapt-load C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\mapas_exit_adapt\seco_b140_exit18_t21.json --brake-adapt --brake-adapt-fixed --brake-adapt-load C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\mapas_freno_adapt\seco_b140_dec11_t21.json --lat-adapt --lat-adapt-fixed --lat-adapt-cap 14 --lat-adapt-max-scale 1.5 --lat-adapt-load C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\mapas_lat_adapt\seco_b140_lim95_cap14_c121314_t21.json --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_optima_a1mu9c12.json --experiment a2_optA1mu9c12_150_g3_lat95_slip8_v70_ff0_cap100_pv03_gas1_fr11_perfil_c10_slip_exit18_cap14_c121314_fijo_t21_dif60_frenos55_ref_l8 --laps 8
```

**Sesión B (más deceleración en el perfil; única variable: mapa de frenada `estres_x115_t21.json` = ×1,15 = 12,65 m/s² en todas las zonas, congelado; con el reparto 55/45).** Con el usuario atento y Ctrl+C a mano: puede llegar pasado a alguna curva:

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --teacher-only --speed-band 150 --max-gear 3 --lat-accel-limit 9.5 --steer-ff-gain 0.003 --steer-ff-v0-kmh 0 --steer-ff-cap-kmh 100 --steer-preview-s 0.3 --steer-slip-gain 8 --lat-gain-v0-kmh 70 --throttle-max 1.0 --brake-decel-straight 11 --brake-overspeed-straight-ms 2.5 --brake-slip-limit 0.25 --brake-slip-hold 0.85 --pedal-technique --brake-profile --brake-circle 10 --exit-circle 18 --profile-peak-min-m 60 --profile-peak-min-kmh 8 --exit-adapt --exit-adapt-fixed --exit-adapt-load C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\mapas_exit_adapt\seco_b140_exit18_t21.json --brake-adapt --brake-adapt-fixed --brake-adapt-load C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\mapas_freno_adapt\estres_x115_t21.json --lat-adapt --lat-adapt-fixed --lat-adapt-cap 14 --lat-adapt-max-scale 1.5 --lat-adapt-load C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\mapas_lat_adapt\seco_b140_lim95_cap14_c121314_t21.json --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_optima_a1mu9c12.json --experiment a2_optA1mu9c12_150_g3_lat95_slip8_v70_ff0_cap100_pv03_gas1_fr11_perfil_c10_slip_exit18_cap14_c121314_fijo_t21_dif60_frenos55_freno115_l8 --laps 8
```

**Banda 140 km/h (receta anterior a V95 con el mapa de tope 13; 1:51.2 de media)** (solo cambia `--speed-band` respecto de la receta; sirve de control si algo sale raro a 150, con el mismo `--lat-accel-limit` y los mismos mapas):

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --teacher-only --speed-band 140 --max-gear 3 --lat-accel-limit 9.5 --steer-ff-gain 0.003 --steer-ff-v0-kmh 0 --steer-ff-cap-kmh 100 --steer-preview-s 0.3 --steer-slip-gain 8 --lat-gain-v0-kmh 70 --throttle-max 1.0 --brake-decel-straight 11 --brake-overspeed-straight-ms 2.5 --brake-slip-limit 0.25 --brake-slip-hold 0.85 --pedal-technique --brake-profile --brake-circle 10 --exit-circle 18 --profile-peak-min-m 60 --profile-peak-min-kmh 8 --exit-adapt --exit-adapt-fixed --exit-adapt-load C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\mapas_exit_adapt\seco_b140_exit18_t21.json --brake-adapt --brake-adapt-fixed --brake-adapt-load C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\mapas_freno_adapt\seco_b140_dec11_t21.json --lat-adapt --lat-adapt-fixed --lat-adapt-cap 13 --lat-adapt-max-scale 1.4 --lat-adapt-load C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\mapas_lat_adapt\seco_b140_lim95_cap13_t21.json --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_optima_a1mu9c12.json --experiment a2_optA1mu9c12_140_g3_lat95_slip8_v70_ff0_cap100_pv03_gas1_fr11_perfil_c10_slip_exit18_cap13_fijo_t21_banda140_l8 --laps 8
```

**Sesión C = prueba de estrés de la frenada (después de la B)** (mapa de estrés ×1,15 cargado con `--brake-adapt` aprendiendo; sustituto de la lluvia, a banda 150 con el mapa de estrés hecho para 140; Ctrl+C a mano):

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --teacher-only --speed-band 150 --max-gear 3 --lat-accel-limit 9.5 --steer-ff-gain 0.003 --steer-ff-v0-kmh 0 --steer-ff-cap-kmh 100 --steer-preview-s 0.3 --steer-slip-gain 8 --lat-gain-v0-kmh 70 --throttle-max 1.0 --brake-decel-straight 11 --brake-overspeed-straight-ms 2.5 --brake-slip-limit 0.25 --brake-slip-hold 0.85 --pedal-technique --brake-profile --brake-circle 10 --exit-circle 18 --profile-peak-min-m 60 --profile-peak-min-kmh 8 --exit-adapt --exit-adapt-fixed --exit-adapt-load C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\mapas_exit_adapt\seco_b140_exit18_t21.json --brake-adapt --brake-adapt-load C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\mapas_freno_adapt\estres_x115_t21.json --brake-adapt-save C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\mapas_freno_adapt\estres_aprendido_t21.json --lat-adapt --lat-adapt-fixed --lat-adapt-cap 14 --lat-adapt-max-scale 1.5 --lat-adapt-load C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\mapas_lat_adapt\seco_b140_lim95_cap14_c121314_t21.json --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_optima_a1mu9c12.json --experiment a2_optA1mu9c12_150_g3_lat95_slip8_v70_ff0_cap100_pv03_gas1_fr11_perfil_c10_slip_exit18_cap14_c121314_fijo_t21_dif60_frenos55_estres_brakeadapt_l10 --laps 10
```

**Recetas anteriores:** la de 125 km/h con la línea suavizada y la óptima (V83-V86) y las históricas de A2.0 (V31-V32, V58, V65) están en el historial de git de este archivo (antes del commit de V90) y descritas en `DECISIONES.md`.

**A1, aceleración hasta el techo.** Por encima de 135 km/h hace falta `--lat-gain-v0-kmh 70`; sin
él el volante oscila (V42). Con el pedal 1,0 de la frenada final se bloquean las delanteras, por eso el
techo se queda en 140 km/h salvo con el limitador de frenada (V44):

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --ident acel --speed-band 60 --ident-cap-kmh 140 --max-gear 3 --lat-gain-v0-kmh 70 --ident-straights 1 --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_smooth.json --experiment a1_acel_g3_lg70_140_60 --laps 3
```

**Frenada con el limitador: serie cerrada (V43-V55).** Ajuste: `--brake-slip-limit 0.25 --brake-slip-hold 0.85`.
Con él, desde 150 km/h con banda 100 y la receta de A2.0 (`--lat-accel-limit 9 --steer-ff-gain 0.003
--steer-ff-v0-kmh 0 --steer-preview-s 0.3 --steer-slip-gain 5 --lat-gain-v0-kmh 70 --throttle-max 1.0
--brake-decel-straight 8 --brake-overspeed-straight-ms 2.5`): vueltas de ≈ 135 s que cumplen V19, frenada de
3437 a 3511 m, 0 ruedas paradas, CTE ≤ 0,40 m, 11,4-11,8 m/s² (V55). Solo cambia `--ident-caps` (140 o 150, la
aceleración arranca fija en 3132 m y la frenada cae en la recta del 3363 m con 140 y del 3437 m con 150; con
130 km/h la banda tiene que ser 60 para caer en la recta). El comando completo, con rutas absolutas:

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\experimental\common\aislado.py --ident frenar --ident-caps 150 --speed-band 100 --max-gear 3 --lat-accel-limit 9 --steer-ff-gain 0.003 --steer-ff-v0-kmh 0 --steer-preview-s 0.3 --steer-slip-gain 5 --lat-gain-v0-kmh 70 --throttle-max 1.0 --brake-decel-straight 8 --brake-overspeed-straight-ms 2.5 --brake-slip-limit 0.25 --brake-slip-hold 0.85 --ident-straights 1 --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_smooth.json --experiment a1_frenar_g3_slip025_hold085_150_100_a2 --laps 3
```

Tabla por tramos de velocidad de V55 (sin cuesta, m/s²; los de más de 120 km/h incluyen el arranque del pedal y
los de 100-80 y 40-30 km/h cambios de marcha): 150-130 11,03; 130-120 11,13; 120-100 11,56; 100-80 10,28;
80-60 11,49; 60-40 11,99; 40-30 9,82.

**Regenerar las líneas locales** (por orden; la segunda tarda ≈ 70 s y la tercera ≈ 50 s):

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\circuito_virtual\src\linea_suave.py
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\circuito_virtual\src\linea_optima.py --coche-a1-mu 9 --max-barridos 80
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\circuito_virtual\src\linea_optima.py --coche-a1-mu 9 --max-barridos 80 --pasillo-estricto --salto-max-rel 1.0 --margen 0.6 --nombre sugo_optima_a1mu9b
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\circuito_virtual\src\linea_optima.py --coche-a1-mu 9 --tope-kmh 125 --max-barridos 80 --pasillo-estricto --salto-max-rel 1.0 --margen 0.6 --curvatura-local-rel 1.2 --nombre sugo_optima_a1mu9c12
```

`a1mu9` y `a1mu9b` se hicieron con tope 125 km/h y la tabla de aceleración anterior a V56: regenerarlas hoy da líneas algo
distintas (las ya hechas no cambian). `a1mu9c12` es la línea con la cota local de curvatura (V62).

**Analizar una sesión:** el procedimiento paso a paso está arriba en «Cómo analizar una sesión». Otras herramientas:

- **Curvas numeradas (V70):** el informe HTML, `resumen_sesion.py` y `pedales_sesion.py` usan `circuito_virtual/pistas/<pista>/curvas.json` (C1-C14 en Sugo, tabla en `TECNICA_CONDUCCION.md` §9). Para que el usuario diga «la curva N», darle el número de ese catálogo; regenerar el informe de un log antiguo: `python experimental/common/informe_c0.py <log>`.
- Pedales y frenada (V65-V67): `experimental\common\pedales_sesion.py <log> --vueltas 2,3,4 [--eventos] [--consigna <linea.json>]` (inversiones y rebotes del gas, tiempo muerto antes de frenar, deceleración, % de la frenada con > 4 m/s² laterales, uso del círculo). Cifras de partida en `TECNICA_CONDUCCION.md` §7.1.
- **Aceleraciones de un log:** usar `session_log.tick_accels(tick["vehicle"])` (lateral, longitudinal positiva al acelerar) o `local_accel[0]` / `local_accel[2]`; **nunca `vehicle.lat_accel` en logs anteriores a V67** (era la longitudinal).
- A1: `experimental\common\analisis_a1.py <log>`.
- Modelo del volante: `experimental\common\modelo_volante.py --ajuste "LOG|REF" --prueba "LOG|REF"`.

### Receta del teacher (opciones de `aislado.py`)

| Opción | Valor | Qué hace | Decisión |
| --- | --- | --- | --- |
| `--teacher-only --max-gear 3` | 3 (2 hasta 115 km/h) | El teacher conduce y el cambio sube hasta 3.ª (techo permitido 150 km/h) | X24, V28-V30 |
| `--lat-accel-limit` | **9,5** (base de `--lat-adapt`, que lo sube por curva hasta `--lat-adapt-cap` 13: ×1,37) | Límite lateral base que el teacher supone en curva (máx. 14,6 por D21 con el ajuste apagado); el coche pide ≈ 1,45 veces ese valor; con `--lat-adapt` cada curva lleva su multiplicador | V27, V74-V76, V87, V90 |
| `--steer-ff-gain` + `--steer-ff-v0-kmh` | 0.003 y 0 | Anticipación de volante 1 + 0,003 · v². A más de 100 km/h se pasa de lo que pide el coche; bajar a 0.002 arregla las curvas rápidas y estropea las lentas | V21, V38-V41 |
| `--steer-ff-cap-kmh` | 0 (sin tope); **100 en la receta vigente** (V72: C14 de 2,0 a 0,95 m y C13 de 1,65 a 1,2 m) | Con `--steer-ff-gain`: por encima de esta velocidad el factor 1 + G · v² deja de crecer; sin cambio por debajo | V41, V57 |
| `--steer-preview-s` | 0.3 | La curvatura del volante se lee a v · 0,3 s y no a 30 m fijos | V22 |
| `--steer-slip-gain` | **8** (5 hasta el 2026-11-07) | Contravolante por deriva (zona muerta 3°, la ganancia de CTE baja a 0 a 8°); 5 → 8 dio −0,08 s de media y vueltas más regulares, confirmado con réplica | V17, V92 |
| `--lat-gain-v0-kmh` | 60 con la línea suavizada; 70 con la óptima y en A1 | Ganancia de CTE × (v0/v)² por encima de v0: estabilidad del lazo a alta velocidad; sin ella oscila a más de 135 km/h. No subir a 80 | V18, V35, V42 |
| `--throttle-max` | 1.0 | Gas a fondo (producción 0,85: acelera un 15-20 % menos) | V24, V25 |
| `--brake-decel-straight` + `--brake-overspeed-straight-ms` | 8 y 2.5 (**11 y 2.5 con el limitador en la receta, V90; 10 hasta la noche del 2026-11-06**) | En recta (\|κ\| < 0,004 y \|CTE\| < 1 m) frena a ≈ 8-11 m/s²; con `--brake-profile` es la `a_b` del perfil (con `--brake-adapt`, ×1 por frenada) | V31, V32, V71, V90 |
| `--reference` | `sugo_smooth.json` o `sugo_optima_a1mu9c12.json` | Línea que sigue el teacher | V14, V32, V36 |
| `--brake-slip-limit` | 0 (apagado); 0.25 en la receta vigente | Si 1 − rps delanteras / rps traseras pasa de este valor, el pedal baja y vuelve a subir al recuperar agarre; actúa sobre el pedal de cualquier origen, también `--ident frenar` | V43, V44 |
| `--brake-slip-hold` | 0 (sin memoria); 0.85 | Con `--brake-slip-limit`: tras pasar del objetivo el pedal sube deprisa solo hasta esta fracción del pedal que lo provocó y despacio desde ahí, en lugar de volver a 1,0 y oscilar | V49, V50 |
| `--pedal-technique` | apagado; en la receta vigente | Técnica de pedales (solo con el modelo físico): gas cortado del todo y enclavado antes de frenar, freno que se suelta en proporción al exceso hasta el vértice y gas que solo sube desde el vértice | V65 |
| `--pedal-exit-slew` | 1.5 | Con `--pedal-technique`: subida máxima del gas por segundo desde el vértice (1,5 = de 0 a fondo en ≈ 0,7 s; con 0,8 el coche de juguete perdía 1,2 s) | V65 |
| `--brake-profile` | apagado; en la receta vigente | Con `--pedal-technique` (V68): consigna de velocidad continua por barrido hacia atrás con el círculo de adherencia (sin el salto 8 → 4 m/s² al entrar en la curva) y freno por avance sin margen ni tiempo muerto | V68-V71 |
| `--profile-peak-min-kmh` | 0 (sin umbral); **8 en la receta vigente (V83)** | Con `--profile-peak-min-m`: un pico solo se aplana si el recorte lo baja al menos estos km/h (sobre el perfil lateral, antes del barrido hacia atrás). 8 deja intactos el pico de 1,4 km/h junto a C4 y el de su salida y mantiene los de C5-C6; depende de la línea y del límite lateral (medido con `sugo_smooth.json` y 9,5) | V82 |
| `--brake-circle` | 14.6; **10 en la receta vigente** | Con `--brake-profile`: radio del círculo en unidades de la línea. 14,6 = trail braking completo; ≈ 10 = casi terminar de frenar antes de girar (el coche hace ≈ 1,45 veces el lateral que cree la línea) | V69-V70 |
| `--exit-circle` | 0 (apagado); **18 en la receta (V89-V90)**; 16 y 14.6 antes | Con `--pedal-technique` (V72, F3): en la salida el gas no pasa de `gas_max · √(1 − (lateral medido / R)²)` (0,76 a 11,7 m/s² con R = 18); 14,6 → 16 → 18 dio −0,2 y −0,15 s: rendimientos decrecientes; con `--exit-adapt`, ×1 por curva | V72-V73, V89, V90 |
| `--profile-peak-min-m` | 0 (apagado); **60 con `--profile-peak-min-kmh 8` en la receta vigente (V83-V85)** | Con `--brake-profile`: aplana al valle más alto de alrededor los picos de la consigna más estrechos que estos metros; el coche no acelera en un tramo corto entre dos curvas para frenar enseguida (C5-C6, C9). Con el coche de juguete: 30 m −0,03 s, 60 m +0,08 s, 100 m +0,5-0,8 s, 150 m +3-3,8 s; en el juego (V80-V81) quita la frenada de C5-C6 y baja ≈ 0,15 s, pero cambia 32 tramos del perfil, entre ellos un pico de 1,4 km/h junto a C4 que sube su deriva | V79-V81 |
| `--lat-adapt` y sus opciones | apagado; en la receta con `--lat-adapt-cap 13 --lat-adapt-max-scale 1.4 --lat-adapt-load <mapa> --lat-adapt-fixed` | Límite lateral por curva (multiplicador 0,7-`max-scale`, sube un 4 % si la curva es limpia, baja un 8 % y se congela 2 vueltas si sale fuera de criterio); `-save` / `-load` / `-fixed` guardan, cargan y congelan el mapa con las condiciones | V87, V88, V90 |
| `--exit-adapt` y sus opciones | apagado; en la receta solo con `--exit-adapt-fixed --exit-adapt-load <mapa>` | Radio de `--exit-circle` por curva (0,7-1,3, `--exit-adapt-max-scale`): sube un 4 % si la salida es limpia y el tope recortaba el gas, baja un 8 % si las traseras patinan, hay deriva > 5° o \|CTE\| > 2 m. Necesita `--exit-circle` y `--pedal-technique` | V91 |
| `--brake-adapt` y sus opciones | apagado; en la receta solo con `--brake-adapt-fixed --brake-adapt-load <mapa>` | Deceleración de frenada por curva (0,6-1,15, `--brake-adapt-max-scale`): baja un 8 % si el freno se suelta a más de 1 m/s sobre el perfil, sube un 4 % si se suelta por debajo de −0,3 m/s sin forzar. Necesita `--brake-decel-straight`, `--brake-profile` y `--pedal-technique` | V91 |

`aislado.py` pasa siempre `--hold-stage` a `learn_driver.py` con `--teacher-only` (V64): sin él dos vueltas limpias cerraban la sesión aunque `--laps` fuese mayor.

Reglas de `aislado.py` para estas opciones: sin `--ident` exigen `--teacher-only` y un
`--experiment` con prefijo `a2_` (el nombre por defecto borraría el buffer `teacher_<banda>`); con
`--max-gear 2` la banda máxima es 115 km/h. Con `--ident` se aceptan y se pasan igual. `--profile-peak-min-m` exige `--brake-profile`.

### Escalera de bandas con la línea suavizada (vuelta lanzada)

| Banda | Límite lat. | Cambios | Vuelta medida / prevista | \|CTE\| máx. | Deriva máx. | Decisión |
| --- | --- | --- | --- | --- | --- | --- |
| 80 | 7,5 | 2.ª | 162,8 / 163,9 s | 0,71 m | 1,0° | V23 |
| 90 (gas 1,0) | 7,5 | 2.ª | 148,9 / 149,6 s | 0,85 m | 1,3° | V25 |
| 100 | 9 | 2.ª | 135,4 / 135,7 s | 1,42 m | 2,9° | V27 |
| 110 | 9 | 2.ª | 128,0 / 127,9 s | 1,42 m | 3,4° | V28 |
| 120 | 9 | 2.ª-3.ª | 123,4 / 122,6 s | 1,77 m | 1,6° | V30 |
| 125 | 9 | 2.ª-3.ª | 121,8 / 120,6 s | 1,59 m | 3,5° | V31 |
| 125 + frenada fuerte | 9 | 2.ª-3.ª | 120,4 / 120,6 s | 1,56 m | 2,5° | V32 |
| 125 + técnica de pedales completa | 9,5 | 2.ª-3.ª | 119,8 s | 1,77 m | 3,9° | V76 |

Con la línea óptima los resultados están en `DECISIONES.md` (V33-V41, V58-V64).

Criterio de volante para subir de banda (V19, provisional): 2 vueltas completas seguidas, sin
salirse, con rectas de volante rms ≤ 0,04, ≤ 1 inversión/100 m y |CTE| rms ≤ 0,25 m, y curvas con
tasa ≤ 0,2/s, |CTE| máx. ≤ 1,8 m y deriva máx. ≤ 4°; además, 0 ticks con ruedas fuera de la
superficie de carrera (hoy el terreno 48, pintura sobre hormigón, cuenta como fuera: ver V78). Referencia: la IA a ritmo real hace 97,9 s.

### Qué está probado y qué no

- **Probado:** teacher en 2.ª hasta 110 km/h y en 3.ª hasta 150 km/h con vuelta completa y los tres ajustes por curva (1:49.215; 10 vueltas seguidas a 1:49.38 de media, V95); aceleración en 3.ª hasta 151 km/h con el volante tranquilo; frenos delanteros estabilizados en ≈ 408 °C sin desvanecimiento en 10 vueltas; frenada fuerte con el limitador de deslizamiento sin bloqueo a 11 m/s²; la técnica de pedales completa; el ajuste del agarre en seco y en mojado; `--exit-adapt` y `--brake-adapt` en seco; guardar y cargar los mapas; lateral sostenido de 16,5 m/s² con tope 13.
- **Con aviso:** las frenadas a fondo de A1 desde 100, 110, 135, 140 y 150 km/h (pedal 1,0, 11,5-11,9 m/s²) bloquean las delanteras a los ≈ 0,3 s y hasta casi parar; el «sin bloqueo» anterior solo miraba las traseras (V42-V43). Con el limitador es otra historia (V44-V55).
- **Sin validar:** la vuelta completa a más de 150 km/h (pide la 4.ª marcha); `--exit-adapt` y `--brake-adapt` en mojado, con gomas nuevas o con otro reglaje; la prueba de estrés de la frenada; un tope del agarre por encima de 13; el grabador manual contra el juego (V77); 4.ª marcha; cualquier otra pista o coche; los bordes reales (D1b: semivía de 0,85 m y margen supuestos).

## Reglas de la sesión (no olvidar)

- **El usuario lanza el juego, yo nunca.** No ejecutar `aislado.py` ni `learn_driver.py` con
  argumentos válidos, ni para «probar» la CLI: lanza una sesión real y borra el buffer del
  experimento (incidente c0_log, memoria `feedback-no-ejecutar-aislado-para-probar`). Para
  comprobar una línea de comandos: `build_argv` y `a2_error` de `aislado.py` desde Python. Lo mismo con `sesion_manual.py` (abre el puerto UDP y escribe un log): solo `--help` y tests.
- **Seco y mojado van separados** (sección «Seco y mojado»): las sesiones con lluvia llevan `a2_mojado_` en el experimento y no se comparan con la base ni con V19.
- **Una sola variable por sesión.** El criterio es el tiempo y las temperaturas (V89), no V19; el orden de los ajustes es agarre → gas de salida → frenos → volante, y cada uno gana por separado antes de juntarlos.
- **Las sesiones anteriores son referencia, no vara de medir** (memoria `feedback-versiones-anteriores-solo-referencia`): cada sesión se juzga contra el criterio y su propio log; los modelos se reajustan con cada log nuevo. Con los ajustes por curva, la referencia es la sesión de referencia del día con los mapas congelados.
- Antes de cada sesión arriesgada (techo alto, frenadas desde más de 115 km/h, arcos, mapeo de
  bordes) confirmar que el usuario está delante del juego y en seco, y que corta con Ctrl+C si el
  coche oscila.
- **Bloqueo de ruedas:** medirlo en las delanteras y en las traseras (rps de cada eje frente al otro),
  no solo con la razón traseras/delanteras mínima.
- Dependencias en un solo sentido: `PCARS2-AI` ← `circuito_virtual` ← `experimental`.
  `circuito_virtual` no importa de `experimental`.
- Documentos de `circuito_virtual/` y `experimental/` en **LF**; en `PCARS2-AI/` los `.py` son
  CRLF salvo los tests nuevos (usar una utilidad que respete cada archivo). Para escribir archivos
  largos usar Write y no scripts de Python con `\n` dentro de cadenas en la línea de comandos.
- El usuario reformatea los docs con markdownlint: no comprobar texto con búsquedas literales
  frágiles (usar regex tolerante a espacios).
- **Ejes del log (V67):** `lat_accel` es la lateral solo desde `log_schema` 3; en los logs anteriores es la longitudinal. Un análisis suelto con el eje equivocado ya produjo cifras falsas en V64-V66.
- **Cambios del teacher que tocan los pedales:** los tests deben medir también la velocidad con la que se llega a cada curva (regresión de V65 7: la consigna «congelada» de la salida tapó la curva siguiente
  y el coche se pasó), no solo inversiones, rebotes y tiempo; el coche de juguete debe acelerar tanto o más que el real (probar ×1,0, ×1,3 y ×1,6).
- **Primera sesión tras un cambio de pedales:** el usuario atento y con Ctrl+C a mano; la primera vuelta es la que revela si el coche llega a una curva sin levantar.
- **Ruedas fuera:** separar siempre el terreno 48 (pintura sobre hormigón, probablemente legal) de la hierba (7) antes de dar una cifra (V78).
- **Datos de fuera del proyecto** (ancho de pista, mapas de la web): comprobación de cordura, no entrada; la página consultada es de otra variante (con chicane), no la `SUGO_GP` del juego.
- **Documentar solo cuando el usuario lo diga** («apunta»); al apuntar, V nueva en `DECISIONES.md`, entrada en `DIARIO.md` y este archivo al día, y commit. Tiempos de vuelta en minutos y segundos (1:51.164).
- **Una sesión con `--…-adapt` guarda su mapa solo si las dos últimas vueltas quedan limpias**; si no se guarda, se reconstruye del log (como el de tope 13) y se etiqueta.
- Camino sólido a largo plazo, sin prisa. Si hay que elegir, recomendar y no listar todo.

## Siguiente (en este orden)

La historia de cada sesión de la noche está en `DECISIONES.md` V69-V99; aquí solo lo que toca.

0. **Al empezar:** `git status` (debería estar limpio; pueden quedar sueltos el `1.tzip` y el `Sportsland Sugo International track map.svg` de la raíz, que no son del proyecto); leer «Al retomar» (arriba) y `docs/TECNICA_CONDUCCION.md` §8-§9. Cuando el usuario diga «la curva N», es el catálogo C1-C14.
1. ~~Pruebas de banda 135 y 140, tope 13 del agarre, gas de salida 18 y frenada 11~~ **hechas (V87, V90).** Lo que toca ahora está en «Al retomar».
2. **D1b por conducción manual — EN PAUSA a petición del usuario (V78: «deja las pruebas pendientes»).** El ancho real declarado (10-12,5 m) duplica los 5,4 m comprobados, así que la línea óptima está limitada por lo recorrido y no por la pista. El usuario conduce (teclado) con las dos ruedas de un lado sobre la hierba y el limitador a 60 km/h, una sesión por lado y 3 vueltas; nada del teacher en marcha a la vez (comparten el puerto UDP). Después: `bordes_logs.py actualizar`, mirar la cobertura y, si hay metros con una sola cota, hacer el extractor con ventana (V77, punto 2); calibrar la semivía con los dos lados; mirar qué ids de terreno hay al cruzar la línea blanca (46, 47, 49) y decidir el 48. Éxito (`PLAN.md`): los dos bordes medidos en ≥ 90 % de la vuelta con incertidumbre ≤ 0,3 m. Diseño original con el teacher (6-10 rondas por lado) en `PLAN.md`, solo si esto no alcanza.

```text
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\circuito_virtual\src\sesion_manual.py --lado izq --laps 3
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\circuito_virtual\src\sesion_manual.py --lado dcha --laps 3
C:\Users\doski\projectIA\.venv\Scripts\python.exe C:\Users\doski\projectIA\circuito_virtual\src\bordes_logs.py actualizar
```

3. ~~**Prueba de banda 145-150 km/h**~~ **hecha (V93-V95: banda 150 es la receta). Texto de entonces:** (va en «Al retomar», punto 3): el techo con 3.ª es 150 km/h (`ident_max_cap_kmh(3)`); el solver (μ 9) tiene tablas de aceleración hasta 140 y el techo de 3.ª está limpio hasta 140; por encima de 135 hace falta `--lat-gain-v0-kmh 70` (V42, ya en la receta). Antes de cada sesión, calcular lo que prevé el solver para esa banda. La recta final (3113-3567 m) y la de 2555-2655 m van hoy a 126-131 km/h con el gas a medias: ahí está el tiempo.
4. ~~C11~~ **Resuelto con la línea óptima y `--lat-gain-v0-kmh 70` (V85):** 1,57-1,63 m.

5. **Pendientes menores del circuito** (observaciones del usuario curva a curva, V76, y de la noche, V90): el coche sale por dentro tras el vértice de casi todas las curvas (V92: volante y gas del vértice); C4 toca el piano (terreno 48) y su deriva de salida llega a 5°; deriva de C5 ≈ 4,3-5,7° con |CTE| ≈ 0; deriva de C9 ≈ 4,4°; hierba en 1400-1450 m tras C8 (desapareció con la frenada a 11); ajuste de pedales en C9-C11.
6. **Más técnica** (`TECNICA_CONDUCCION.md` §5): F10 gas con espera en la salida de curvas cerradas, F11 clasificar las curvas (C12-C14 son un solo viraje largo), F12 eses, F13 horizonte de mirada (el recorte de picos de V79 es un primer paso), F5 puntos de frenada adaptativos, F6 cambios de marcha respecto a la frenada, F7 neumáticos (se enfrían de 80 a 46 °C en 4 vueltas).
7. **Decidir la tabla de frenada del solver** (V55, punto 4; enlaza con F4, perfil del solver como archivo): la de `parametros_a1.json` (45-105 km/h, 11,87-13,05 m/s²) y las medias por ventanas de V55 (10,3-12,0 m/s²) no coinciden. Las tablas de A1 ya descuentan la pendiente. Datos de partida (radio efectivo 0,274 m): sin bloqueo el deslizamiento delantero va al 10-15 % con pedal 0,6-0,95; con bloqueo (80-110 %) la deceleración baja a 11,9 m/s² frente a 12,5-12,7 con el 20-50 %.

   **Estado de `coches/formula_rookie/parametros_a1.json` (revisado 2026-11-03, V86):** la aceleración (15-135 km/h) es de V56 y regenerarla con `analisis_a2.py` desde sus 6 logs da el mismo archivo; la frenada (45-105 km/h, 11,87-13,05 m/s²) es la de A1 con pedal 1,0 y no tiene datos por encima de 105 km/h (usa 13,05 hasta el tope). `mu` 14,6 no pesa: `coche_a1()` lo sustituye por el que se pide. Solo lo leen el solver y la generación de líneas (`coche_a1()`, `linea_optima.py`, los informes de líneas); el teacher y el juego no. **Efecto medido con la línea `a1mu9c12`** (solo cambia la tabla de frenada; segundos de vuelta prevista a 125 / 135 / 140 km/h): la actual 118,4 / 115,3 / 114,1; las medias de V55 con el limitador (150-130 11,03; 130-120 11,13; 120-100 11,56; 100-80 10,28; 80-60 11,49; 60-40 11,99) 118,6 / 115,5 / 114,3; plana a 10,0 m/s² (la `a_b` de la receta) 118,7 / 115,6 / 114,5. Es decir, +0,2 a +0,3 s (0,2 %), y con las medias de V55 la previsión a 125 km/h (118,6 s) coincide con lo medido en las sesiones de V85-V86 (118,6-118,7 s). **No urgente y no tocarlo antes de la sesión de 135:** esa sesión se juzga contra 115,3 s con la tabla actual, y cambiar la frenada del solver cambiaría la línea óptima si se regenera (una variable nueva sobre la receta confirmada). **Cuando se decida:** regenerar el archivo con las medias del limitador (`analisis_a2.py --guardar …/parametros_a1.json` tras ajustar `BRAKE_LOGS` o la tabla), regenerar `a1mu9c12` y comparar la línea nueva con la actual, y probarla en una sesión aparte (una variable: `--reference`).

8. **Ajuste unificado de las curvas (diseño del 2026-11-08, sin escribir código todavía; proponerlo al usuario antes).** Idea del usuario: que todos los parámetros por curva se adapten juntos, con un solo conjunto de opciones. Hoy son tres adaptadores que heredan de `LatAdapter` (`lat_adapt.py`, `exit_adapt.py`, `brake_adapt.py`) con tres mapas, nueve opciones (`-adapt`, `-load`, `-save`, `-fixed`, `-cap` / `-max-scale`) y criterios distintos. Propuesta:
   - **Un solo adaptador `CurveAdapter`** con, por curva (C1-C14, `curvas.json`), tres magnitudes en **valores absolutos**: límite lateral (m/s², 9,5-14,6; D21), radio del círculo de gas de salida (12,6-23,4) y deceleración de frenada (6,6-13); cada una con su tope propio (hoy el efectivo es el menor entre `max-scale` y `cap` / base: redundante) y `--brake-decel-straight` deja de limitarse a 11 en `aislado.py` (el coche hace 13,2 m/s²). Opciones: `--curve-adapt`, `--curve-adapt-load / -save / -fixed` y `--curve-adapt-only lat,exit,brake` para activar solo algunas; las antiguas siguen como alias.
   - **Un criterio común de «curva mala» con los umbrales de V89** (|CTE| ≈ 2,3 m, deriva ≈ 5,5°, ruedas fuera que no sean franja 10 ni pintura 48 de sitios conocidos), más las señales propias de cada magnitud (razón RPS trasera en la salida; velocidad sobre el perfil al soltar el freno). La regla de subida no puede exigir < 3° de deriva en las curvas rápidas (C12-C14: 3,2-3,8°) ni |CTE| ≤ 1,2 m en las que salen por dentro (C3, C10, C11). Registrar en cada vuelta por qué sube, baja o se congela cada magnitud.
   - **Mapa de formato 2** que lleva también el **reglaje** (diferencial, reparto de frenada, presiones) y las condiciones; carga los de formato 1.
   - **Protocolo «aprender – congelar – medir»:** 10 vueltas aprendiendo desde el mapa anterior, guardar (dos últimas limpias) y 8 vueltas congeladas de medida. Cada cambio de reglaje se evalúa después de reaprender. La primera vez, congelación escalonada (agarre → gas → freno) y, si oscila, una magnitud por vuelta.
   - **Antes de jugar:** tests de los tres adaptadores portados, tests nuevos (topes absolutos, criterio común, mapas de formato 1) y **pasar los logs `222926Z` (que no debe bajar C2-C7), `225939Z` y `000717Z` por el código nuevo**, como se hizo en V91.

## Después (en este orden)

- **BC v2 y PPO (opinión del 2026-11-08; el usuario quiere probar BC antes que PPO y no hay fecha):** el BC (copia del teacher) va **antes** del PPO, como en `PLAN_C_RAMPA_BC.md` (C4: «re-destilar a PPO»). Hoy el BC llega a 60 km/h (`bc60_ft_model.pt`) y el teacher da 1:49.0 a 150 km/h, así que un BC v2 se entrenaría **sin juego** con los logs del teacher de ahora (cientos de vueltas a 117 km/h de media), tal como prevé D16 (reentreno desde cero tras A1). Condiciones, para no copiar algo que cambia: (1) el reglaje del coche, la receta y los mapas, **fijos** (por eso conviene tener antes el ajuste unificado y el reglaje decidido); (2) logs con el reglaje y los mapas aplicados en la cabecera (`log_schema` 5); (3) el BC aprende la política ya convergida (mapas congelados) y no el aprendizaje vuelta a vuelta, que se queda en el teacher; (4) criterio de éxito: igualar al teacher en tiempo (1:49.0) en Sugo, en seco y con el teacher de red de seguridad, subiendo por bandas como D20; el valor del BC no es batir al teacher en esta pista sino **generalizar** (otras pistas y coches) y servir de arranque al PPO; (5) el PPO empieza desde el BC y se compara con el teacher (1:49.0 es la vara de medir). Orden: ajuste unificado → reglaje cerrado → trazada (línea y mapas reaprendidos) → conjunto de datos «oro» (≥ 30 vueltas limpias) → BC v2 offline → prueba en el juego con el usuario delante → PPO.

1. **Medir el límite lateral del coche (A1.3b)**: el teacher ya pide 13-15 m/s² sostenidos con
   `--lat-accel-limit 9`, en la cota validada de D21 (≥ 14,6). Subir más exige arcos en 3.ª y 4.ª
   (D23). Riesgo de daño de motor (P26): tres de tres sesiones de arcos lo dieron hacia los 607 s;
   `aislado.py` ya pasa `--stop-on-damage`; sesiones cortas.
2. **A/B de la ayuda de bloqueo opuesto (D12, P20):** el log no muestra intervención
   (`game_steer` ≈ `raw_steer`, diferencia media 0,017) pero no se sabe si actúa sin reflejarse.
   Misma sesión con la ayuda desactivada (ajuste del juego, se aplica al empezar una sesión
   nueva; anotarlo en el nombre del experimento).
3. **Completar el reglaje del diferencial:** del trasero solo se ve «DDL por embragues: Sí» y rampa
   en deceleración de 30°; faltan precarga, embragues, potencia de rampa y todo el delantero
   (pedir captura). El freno de motor está en 8. No tocar el reglaje: A1 y A2 están medidos así.
4. **Datos de agarre: temperaturas izquierda / centro / derecha.** `log_schema` 4 ya lee la capa, la carcasa, el aire interior y el compuesto (offsets 224-248 y 378 del paquete de física de 556 bytes, `SMS_UDP_Definitions.hpp`), pero `sTyreTempLeft` 256, `sTyreTempCenter` 264 y `sTyreTempRight` 272 (`ushort` en °C) salen siempre 0 en nuestro UDP. **Second Monitor (V89) las lee bien** (de los mismos campos de la shared memory / UDP de PC2, en °C con resolución de 1 °C), así que el foro que decía que solo estaban en el UDP estaba equivocado o nuestra lectura falla. Pendiente: comparar nuestro paquete con el suyo (otro tipo de paquete u otro offset) y, si no, leerlas de la shared memory `$pcars2$`; guardarlas compactas en el log (enteros en °C). Mientras tanto basta `second_monitor.py`. No cambia la conducción, así que no cuenta como variable de una sesión.
5. **Peralte de la pista:** el mapa tiene altura (−46 a +25 m) y pendiente, pero no inclinación lateral; se puede sacar de los logs (alabeo menos la parte de la aceleración lateral; a 30-60 km/h en recta el alabeo es casi el de la pista).
6. **Visión por pantalla para las líneas blancas** (idea del usuario, V78): sería el mejor objetivo de una visión (HUD oculto, cámara de capó, campo de visión fijo, captura sincronizada con la posición y la orientación del UDP); solo si los ids de terreno no ven la línea blanca y D1b no basta; D1b serviría de verdad de referencia. **2026-11-08, el usuario propone grabar un vídeo de una vuelta y analizarlo:** el entorno del proyecto no tiene ffmpeg ni OpenCV (solo PIL y numpy; haría falta `pip install opencv-python-headless imageio-ffmpeg`, con permiso). Primer paso, cualitativo y casi gratis: una vuelta del teacher grabada con cámara de capó, HUD oculto y 60 fps, empezando desde parado (sirve para sincronizar con el log), y mirar fotogramas en C1, C4 y C11 para ver si hay ≈ 1 m más de pista (V100). Medir los bordes a lo largo de toda la vuelta exige calibrar la cámara (los fotogramas con una rueda en la franja o en la hierba dan puntos de verdad por el id de terreno) y vale la pena sobre todo para otras pistas y coches (BC / PPO), donde D1b a mano no escala. **D1c, diseño (2026-11-08; el debate general, para todas las pistas y coches, sigue en la carpeta nueva `video_vuelta/`, ver `video_vuelta/docs/DEBATE.md`):** análisis fuera de línea del vídeo, sin tocar el juego. (1) Sincronizar con el log por el arranque desde parado y comprobar con el cruce de la meta; (2) corregir cada fotograma con la orientación del UDP (cabeceo, alabeo) y la altura de suspensión; (3) calibrar la cámara (altura, inclinación, campo de visión) con puntos de verdad: fotogramas donde una rueda pisa franja o hierba según el id de terreno; (4) detectar por color y en vista de pájaro la línea blanca, la franja roja y blanca, la hierba y el asfalto; (5) pasar los puntos al sistema del mundo con la posición y el rumbo del UDP y proyectarlos sobre el eje del mapa (`n` izquierdo y derecho por metro), promediando las vueltas; (6) escribir un log propio (`bordes_video.json` y un CSV por fotograma) que `bordes_logs` / `linea_optima.py` puedan leer; (7) validar contra los cruces de terreno del log (éxito: error mediano ≤ 0,3 m en ≥ 90 % de la vuelta, como D1b). Es una herramienta que sirve para cualquier pista y coche; para Sugo, el ensanchado progresivo del teacher (V100) da el dato duro más barato. **Idea del usuario (2026-11-08) que lo hace fiable, D1c en dos fases:** (A) el vídeo de la sesión A da una estimación del borde por metro; (B) con esa estimación se generan líneas de referencia a baja velocidad (30-40 km/h) con el centro del coche a la estimación menos 0,3 m, en la estimación y más 0,3 m, una vuelta por lado y escalón (≈ 6 vueltas, ≈ 35 min en total) grabadas también en vídeo; con la posición, el rumbo y el CTE del log y los **cambios de terreno por rueda** (asfalto → franja o hierba) se mide en cada punto cuánto se equivoca la estimación y se calibra la cámara con muchos puntos de verdad. Así se necesitan 2-3 rondas por lado en vez de las 6-10 de D1b (`PLAN.md`) y ninguna conducción a mano. Código pendiente: generador de las referencias desplazadas a partir de `bordes_video.json` (como el `sesion_mapeo.py` de `PLAN.md`: escribe las referencias en `pistas/sugo_gp/desplazadas/` e imprime los comandos de `aislado.py`, sin arrancar el juego) y el comparador de cruces de terreno.
7. **A3, segunda pista:** repetir A2 con otra pista y otra IA para saber si el factor de ritmo y
   las envolventes se generalizan. Requiere `circuito_virtual/pistas/<pista>/` con mapa y
   referencia suavizada.
8. **Rivales:** ver si el paquete de tiempos trae la posición de los rivales (hoy solo se lee al
   participante propio; el relay de memoria compartida del Telemetry Tool dice dar «posición y
   velocidad de otros coches»), antes de D5.
9. **PPO residual sobre el teacher:** la técnica de curva del manual (frenar fuerte y soltar con el giro, mínimo en el ápice, gas progresivo con tope por el círculo) ya está en el teacher (paso 4 de V17; V65-V79, `TECNICA_CONDUCCION.md`), así que el PPO va después como corrección acotada sobre ese teacher (V17); antes, revisar el estado de `ppo_guard`, `ppo_anchor` y `ppo_bootstrap`, y decidir si el BC aprende la receta vigente (los logs ya traen `long_accel`, el catálogo de curvas y las razones `lift_lock`/`accel_exit` normalizadas al vocabulario del BC).

## Ideas y referencias

- **Técnica de conducción** (V66): `docs/TECNICA_CONDUCCION.md` recoge lo que dicen PCA «The Art of Braking» y 8000vueltas (frenar y acelerar), lo que hace el teacher con datos y las fases F1-F13.
- **Manual de Racelogic** (*Advanced Circuit Driving Techniques*, aportado por el usuario): volante
  mínimo («enderezar cada curva» valió 0,9 de 1 s en Eau Rouge); la velocidad en curva no es
  constante (frenada modulada, mínimo en el ápice); gas solo cuando no haya que soltarlo; una línea
  que usa todo el ancho pide menos volante (apoya la línea óptima).
- **Ancho y geometría de la pista (V78):** ni el UDP ni la shared memory de PC2 traen el ancho ni los bordes (solo `mTrackLength`); yourdatadriven.com da 10 m, ≈ 75 m de desnivel (nuestro mapa 70,9 m) y 3704 m, pero es otra variante (con chicane; el juego mide 3567 m) y su mapa viene de OpenStreetMap. Shared memory = los mismos datos en `float`, con número de secuencia; seguir con UDP.
- **Terrenos (V78):** 46 `RunoffRoad`, 47 `IllegalStrip`, 48 `PaintConcrete`, 49 `PaintConcreteIllegal`; solo el 10 (franjas) está en la lista de carrera.
- **Second Monitor** (Matus Celko, `gitlab.com/winzarten/SecondMonitor`, MIT; el espejo de GitHub está desfasado): graba cada vuelta cerrada en `Documents\SecondMonitor\Telemetry\Recent\<sesión>\` (un `.zLap` por vuelta: gzip + protobuf-net con las clases `ProtoContract` de `Foundation/DataModel`). Aporta lo que nuestro UDP no da: las temperaturas izquierda / centro / derecha de las gomas; slip y carga por rueda salen a 0 (PC2 no los da). Sin ancho ni bordes de la pista. Lector propio en `experimental/common/second_monitor.py`.
- **Telemetry Tool for PC2 (Iko Rein) v15.09**, revisado en solo lectura: lee el mismo UDP; no trae
  canales de agarre para PC2 (carga por rueda y nivel de agarre son de F1 y rF2); sus indicadores
  útiles (deriva frente a guiñada, razón traseras/delanteras, índice de subviraje) se calculan con
  lo que ya registramos. El índice de subviraje sería un buen estado para el gas de salida.
- **Dato:** `air_pressure` del log son centésimas de bar y en caliente (155/142 con el garaje en
  1,51/1,39 bar); `CONFIGURACION_JUEGO.md` da el reglaje en frío (1,25/1,15).
- **Más puntos de control en la línea:** `--paso-nudos 15` da −5,3 % frente a −3,5 % con 20 m con
  las envolventes de la IA, pero una línea con más movimiento lateral; solo cuando la de 20 m esté
  rodada (hoy exige más seguimiento).

## Más adelante (tras D2, D3 y el mapa)

- **D3-D5:** planificador (dónde y a qué velocidad), política aprendida por selección y
  adelantar/defender, según el plan D de `docs/PLAN.md`.
- **PPO / C4:** después de mapa, modelo y BC v2, con noche protegida.
- **Reentreno v2 del BC y controles de seco:** en `experimental/docs/PENDIENTE.md`.
- **Informe del mapa:** añadir la línea óptima (D2) a `src/informe_mapa.py`.
- **Informes HTML (no versionados, `pistas/sugo_gp/informes/`)**: `informe_mapa.html`, `informe_linea_optima.html` e
  `informe_lineas_teacher.html` (V63). Se regeneran con los comandos de «Uso» del `README.md`; el último, tras cada
  sesión nueva de A2.0, añade la sesión a su tabla.

## Hecho (no repetir)

- ~~G1b~~ **Hecho (V14):** 134,9 km/h en 3.ª, 3 vueltas, sin cortes, sin daño.
- ~~A2 con la IA a ritmo real~~ **Hecho (V12, V13).**
- ~~D0~~ **Hecho (V7):** coordenadas (s, n), `src/mapa.py`, `pistas/sugo_gp/mapa.json`.
- ~~D1a~~ **Hecho (V9, V10, V33):** bordes de 124 logs (hoy se añadieron 18).
- ~~Línea suavizada~~ **Hecho (H61 en `experimental/docs/DECISIONES.md`).**
- ~~D2~~ **Hecho (V15, V32, V33):** línea óptima por ritmo de la IA y por coche del teacher.
- ~~A2.0, escalera 80 → 125 km/h~~ **Hecho (V16-V32).**
- ~~G3, frenadas desde la 3.ª hasta 115 km/h~~ **Hecho (V29).**
- ~~Frenada fuerte en recta~~ **Hecho (V31, V32).**
- ~~Techo en 3.ª~~ **Hecho hasta 140 km/h (V43):** volante tranquilo; el motor llega a 149,9 km/h (V42).
- ~~Modelo del volante~~ **Hecho (V39-V41):** `experimental/common/modelo_volante.py`.
- ~~Línea `a1mu9b`~~ **Hecha (V36):** quita las ruedas fuera de 759-771 y 1444-1454 m; no cumple todavía el criterio.
- ~~Corregir el campo `lat_accel` del log~~ **Hecho (V67):** `log_schema` 3, `long_accel` y `tick_accels`.
- ~~Leer las tres partes de 8000vueltas y el PDF de Porsche (PCA)~~ **Hecho (V66, V67):** `docs/TECNICA_CONDUCCION.md`.
- ~~Técnica de pedales implementada~~ **Hecho (V65-V73):** frenada con perfil, tope del gas por el círculo y volante con tope de anticipación; cumple V19 en una pareja de vueltas (V73, V76).
- ~~Actualizar la tabla de aceleración de A1 y el tope del solver~~ **Hecho (V56).** Queda, si se quiere, una sesión de aceleración con techo 150 km/h (`--ident acel --ident-cap-kmh 150 --lat-gain-v0-kmh 70`).
- ~~Subir el límite lateral del teacher a 10~~ **Probado (V74-V75):** gana 1,9 s pero no cumple V19; la receta vigente usa 9,5 (V76).
- ~~Grabador pasivo para D1b manual~~ **Hecho (V77):** `circuito_virtual/src/sesion_manual.py`.
- ~~Recorte de picos de la consigna~~ **Implementado (V79) y probado dos veces en el juego (V80-V81):** sin freno en C5-C6, 119,5-119,7 s, pero sin pareja V19 por la deriva de C4; el umbral de prominencia lo arregló (V82-V83) y es parte de la receta vigente.
- ~~La línea óptima con la receta vigente~~ **Hecho (V84-V85):** `a1mu9c12` con `--lat-gain-v0-kmh 70` da 118,6 s con las tres parejas de vueltas cumpliendo V19; confirmado con 6 vueltas (V86).
- ~~Ajuste del límite lateral por curva (`--lat-adapt`)~~ **Hecho (V87-V88, V90):** validado en mojado y en seco; tope 12 → 1:52.1 en 10 vueltas, tope 13 → 1:51.5 convergiendo en la vuelta 3 con el mapa cargado; guardar y cargar el mapa con las condiciones de pista y gomas.
- ~~Gas de salida 16 y 18, y frenada 11~~ **Hecho (V89-V90):** −0,2, −0,15 y −0,19 s; sin hierba tras C8.
- ~~`--exit-adapt` y `--brake-adapt`~~ **Hechos y validados en seco (V91):** seguros y casi neutros; mapas guardados con cola limpia.
- ~~Lector de Second Monitor y emparejamiento con el log~~ **Hecho (V89):** `experimental/common/second_monitor.py`.
- ~~Criterio V19 con los ajustes~~ **Sustituido (V89):** tiempo y temperaturas de la pista y de las gomas.
