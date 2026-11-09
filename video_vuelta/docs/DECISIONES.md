# Decisiones de video_vuelta

Registro cronológico. Una decisión posterior puede corregir una anterior (se indica en las dos). Para repetirlo en otra pista: `PROCEDIMIENTO.md`.

| Decisión | Fecha | Tema | Vigente |
| --- | --- | --- | --- |
| D1 | 2026-11-08 | Alcance, captura y herramienta (OpenCV, grabadora externa) | Sí |
| D2 | 2026-11-08 | Condiciones de grabación: formato, cámara de capó, gráficos | Sí |
| D3 | 2026-11-08 | Primera vuelta utilizable; sincronía por el arranque | Sí, con D12 si el log no empieza parado |
| D4 | 2026-11-08 | Plan de vueltas con ruedas fuera del asfalto (40 km/h) | **Sustituido por D11** (30 km/h con gas automático) |
| D5 | 2026-11-08 | Cámara calibrada y línea blanca (vídeo automático a 30 km/h) | Sí; el 10 es legal (D10) |
| D6 | 2026-11-08 | Borde derecho y límite de carrera; constantes 0,06 y 0,18 m | Sí, verificadas en D11 |
| D7 | 2026-11-08 | Etiquetas automáticas y primer segmentador; cómo añadir un circuito | Red sin probar fuera de Sugo |
| D8 | 2026-11-08 | Segundo vídeo (12.41) y sesgo a alta velocidad | Sí |
| D9 | 2026-11-08 | Calibración reproducible; plan de 90° | 90° sin hacer |
| D10 | 2026-11-08 | El piano es legal; `verificar_limite.py` | Sí |
| D11 | 2026-11-09 | Reglas del límite, verificación con dos vueltas manuales y mapa corregido | Sí |
| D12 | 2026-11-09 | Pasillo y línea nueva para la sesión; herramientas de sincronía y revisión; cierre para Sugo | Sí |

## D1 (2026-11-08): alcance, captura y herramienta

- **Alcance:** medir la pista (bordes, línea blanca y franja, usos A + B del debate). La observación
  visual para BC / PPO (uso D) queda para más adelante.
- **Captura:** grabadora externa y sincronía por el arranque desde parado; la marca de tiempo propia
  solo si el error resulta grande.
- **Herramienta:** `opencv-python-headless` 5.0.0 instalado en `.venv` (el 2026-11-08, sin conflictos
  según `pip check`). **No** se añade a `PCARS2-AI/requirements.txt`: solo lo usa esta carpeta, y
  `PCARS2-AI` no debe depender de ella. `av` (PyAV) solo si la sincronía necesita la marca de tiempo
  exacta de cada fotograma.
- **Siguiente (V1, cualitativo):** grabar la sesión A en vídeo y mirar fotogramas en C1, C4 y C11.

## Convención de carpetas

`capturas/<pista>/<coche>/<AAAA-MM-DD>_<n>/` con el vídeo y un `manifiesto.json`:

```json
{
  "video": "sesion_a.mp4",
  "log": "PCARS2-AI/logs/<nombre del log>",
  "pista": "sugo_gp",
  "coche": "<coche>",
  "camara": "capo",
  "resolucion": [1920, 1080],
  "fps": 60,
  "hud": "oculto",
  "sincronia": {"metodo": "arranque_desde_parado", "t_video_s": null, "t_log_s": null},
  "reglaje": "diferencial 60°, frenos 55/45",
  "condiciones": "seco, pista 21 °C, ambiente 14 °C",
  "notas": ""
}
```

Los vídeos pesan GB: si no caben en el disco del proyecto, se guardan fuera y el manifiesto apunta a
la ruta absoluta en `video`.

## D2 (2026-11-08): condiciones de grabación

- **Formato:** 1920×1080 a 60 Hz, pantalla completa (`windowed="0"`), grabación de Radeon ReLive «Dentro
  del juego», 60 fps, AVC, 100 Mb/s. La comprobación es la propia captura: debe medir 1920×1080 (una
  prueba salió a 1920×1200 y otra a 2560×1440). El juego reescribe `graphicsconfigdx11.xml` al cerrarse
  y **ignora `adapter`** (se probó `adapter="1"`: volvió a 0), así que no sirve para elegir monitor.
- **Cámara:** la de capó / morro (las dos ruedas delanteras y la punta del morro en pantalla, borde
  izquierdo y derecho visibles, rígida al chasis). Descartadas: persecución, ras de suelo, cockpit y
  la de superficie negra.
- **Ajustes de cámara a fijar y no tocar más:** sensibilidad de la velocidad del campo de visión = No,
  vibración a alta velocidad = Desactivada, efecto de fuerza G = 0, movimiento del entorno = 0,
  cámara ladeada = 0 (si se puede); campo de visión del capó = 70° **horizontal** (lo dice la ayuda del juego; en 16:9 son ≈ 43,6° vertical; anotarlo
  en cada manifiesto). Comprobado con capturas el 2026-11-08 (12:26): todo puesto, `Cámara ladeada` incluida.
- **Ayuda de línea de carrera apagada** (las flechas verdes tapan el asfalto) y overlay de rendimiento
  apagado.
- **Gráficos (cerrado el 2026-11-08, 16:11):** el filtro de texturas (`texturefilter="5"`) y la resolución de
  texturas (`textureresolution="2"`) ya estaban en el máximo del menú; solo cambió el detalle de pista
  (`trackdetaillevel` de 0 a 3, el máximo). Perfil de referencia en `perfiles/graficos.json` (28 ajustes, sin
  `adapter`); `src/comprobar_graficos.py` lo compara con el XML del juego antes de cada sesión (`--captura`
  mide además el vídeo, `--copiar-a` deja una copia del XML en el manifiesto; con tests). El XML solo se
  reescribe al cerrar el juego. Vídeo de prueba `Project CARS 2_2026.11.08-16.11.mp4` (54,8 s, 3292
  fotogramas, 100 % a periodo exacto, 0 huecos, 0 rotos, ≈ 80 Mb/s de media con el detalle de pista 3):
  utilizable; línea blanca, piano y marcas de goma nítidos.

## D3 (2026-11-08): primera vuelta utilizable y sincronía por el arranque

- **Grabación:** `Project CARS 2_2026.11.08-12.41.mp4` (143,7 s, 1920×1080, 60 fps, 66 Mb/s de media, 1,5 GB), con el
  log pasivo `20261108T114128Z_sugo_gp_mapeo_izq.jsonl` (`sesion_manual.py`, 8641 ticks). Manifiesto en
  `capturas/sugo_gp/formula_r/2026-11-08_1/`. `comprobar_video.py`: utilizable. HUD ya oculto.
- **Antes (12:28, 100 Mb/s):** el codificador de Radeon se hundió a los 8,7 s (de 71 a 11 Mb/s; los fotogramas
  completos pasaron de 480 KB a 40 KB) y el vídeo quedó roto. Con la tasa más baja no se repitió.
- **Sincronía por el arranque:** el coche se mueve en el log a t = 17,434 s y en el vídeo a 8,533 s
  (energía de movimiento de la franja de carretera) → **t_log = t_video + 8,901 s**. A ojo cuadra (el apice de C11
  sale con su cartel «11»); falta medir el error con el cruce de meta.
- **Para la fase B (30-40 km/h):** el coche no «detecta» las líneas; las detecta el análisis fuera de línea del
  vídeo y los ids de terreno por rueda del log dan la verdad. Falta escribir el generador de referencias
  desplazadas y el comparador de cruces de terreno (ver PENDIENTE, D1c).

## D4 (2026-11-08): plan de las vueltas con ruedas fuera del asfalto

> **Sustituido por D11:** al final se hicieron a 30 km/h con gas automático (`sesion_manual.py --velocidad-auto 30`), con zigzag en lugar de ruedas todo el rato fuera, y sin vídeo obligatorio.

- **Qué:** dos vueltas manuales, una con las ruedas del lado izquierdo sobre hierba y piano y otra con las del
  derecho, a unos 40 km/h (o con el limitador a 60), cada una con su vídeo y su log
  (`circuito_virtual/src/sesion_manual.py --lado izq|dcha --laps 1`, rutas absolutas en el PENDIENTE). Una
  tercera vuelta zigzagueando, opcional, da cruces repartidos.
- **Por qué:** la vuelta del 08-11 tiene todos los terrenos a 0 (asfalto), así que no hay puntos de verdad para
  calibrar la cámara. Cada cruce de terreno de una rueda marca un punto del suelo cuya posición se conoce
  por el log, y la línea o el piano que se veían en el vídeo unos metros antes se pueden emparejar con él.
  Esas mismas vueltas dan los bordes por ruedas (D1b) sin ningún coste extra.
- **Una vuelta por grabación** (≈ 5 min a 40 km/h, ≈ 3 GB): los vídeos largos arriesgan el codificador de
  Radeon, que ya se hundió una vez a los 8,7 s con el tope en 100 Mb/s. Se comprueba cada vídeo con
  `comprobar_video.py` antes de seguir. Si vuelve a romperse con una tasa baja, OBS con el codificador de AMD y
  fotograma completo cada 1 s.
- **Procedimiento:** coche parado 5 s en la parrilla, lanzar el grabador y la grabación, dar la vuelta, parar unos
  segundos después de la meta; después `sincronia.py --manifiesto` de cada vuelta.
- **Pendiente de la sesión:** texturas (filtro anisotrópico y resolución), `comprobar_graficos.py`, error de la
  sincronía con la meta y preguntar si se añaden las vueltas a las cotas (`bordes_logs.py actualizar`).

## D5 (2026-11-08): cámara calibrada y línea blanca medida desde el vídeo automático a 30 km/h

- **Grabación:** `Project CARS 2_2026.11.08-16.20.mp4` (861,7 s, 6,4 GB, ≈ 64 Mb/s, 0 rotos) con el piloto
  automático (`aislado.py --teacher-only --speed-band 30`, línea `sugo_ai.json`, 2 vueltas, 429,2 y 427,2 s,
  29-32 km/h, |CTE| medio 0,22 m). Manifiesto y resultado en `capturas/sugo_gp/formula_r/2026-11-08_2/`.
  Sincronía `t_log = t_vídeo − 1,662 s`; a 1425 m el log dice «ruedas izquierdas sobre la franja» y el fotograma
  muestra el piano bajo ellas (comprobación independiente). En el log, las ruedas izquierdas pisan el terreno 10 (piano) en 1400-1447 m y el 7
  (hierba) en 1445-1451 m. **Ojo: el 10 (`TERRAIN_RUMBLE_STRIPS`) está en `RACING_TERRAIN_IDS`, es superficie legal; solo el paso a hierba, grava, etc. es
  «fuera»** (corregido en D10; antes lo traté como fuera).
- **Cámara (`src/camara.py`):** estenopeica, 70° horizontales, sin alabeo. Ajustada con la fila de la línea de
  meta que se acerca frente a los metros que el log dice que quedan (cruces de las vueltas 1 y 2, velocidad
  constante): **altura ≈ 1,02 m, cabeceo ≈ 5,98°, la cámara va ≈ 3,0 m por detrás del punto «posición» del log**
  (rms 0,6-2,4 px). Comprobación independiente: ese cabeceo pone el horizonte en la fila 396 y en los fotogramas
  está en la 396-403. La salida desde parado **no vale** para calibrar (el coche se «sienta» al acelerar: sale
  h = 0,77 m y 4,3°, rms 4 px).
- **Rumbo del log:** `orientation[1] − π` = dirección del avance (`atan2(dx, dz)`), error medio 0,005 rad,
  desviación 0,03 rad (1,7°). Con `− π/2` las líneas salían giradas 90° (error mío, ya corregido y con test).
- **Detector (`src/lineas.py`):** blanco poco saturado cuyo ancho en metros a esa distancia es de línea (4-35 cm);
  las franjas del piano, el cielo y los muros se descartan por ancho. Recta sobre el suelo con más apoyos a cada
  lado. Útil entre ≈ 3,6 y 9,6 m por delante de la cámara.
- **Resultado (`src/bordes_video.py`, `linea_blanca.json`):** mediana de `n` por metro y lado. **Ancho línea a
  línea 10,18 m (p10-p90 9,8-10,8) en 541 m con las dos líneas; el asfalto comprobado por ruedas era 5,4 m.** Es
  lo que el usuario declaraba (10-12,5 m, V78): el pasillo de la línea óptima se queda corto en ≈ 4-5 m.
  Cobertura: izquierda 70 % de la vuelta, derecha 40 %, ambas 15 % (a la derecha hay piano rojo y blanco, no línea).
- **Frente a las cotas por ruedas de los logs antiguos** (horquillas estrechas, < 0,3 m): la línea cae 0,26-0,30 m
  hacia dentro del punto medio de la izquierda (independiente de la distancia: no es de escala) y 0,16-0,57 m en
  la derecha; la dispersión p10-p90 es de ≈ ±0,5 m. Lectura (corregida en D10): donde junto a la línea hay hierba, la superficie legal
  termina ≈ 0,2-0,3 m más allá de la línea blanca (el asfalto sigue un poco tras la pintura) y la semivía de 0,85 m de los logs
  antiguos no está medida. **No es todavía el borde de carrera**: es la línea blanca.
- **Pendiente:** (1) el borde derecho: piano rojo y blanco y hierba (color), y la franja entre línea y piano;
  (2) pasar de «línea blanca» a «límite legal» con una constante por lado medida con los cruces de terreno
  (el paso de asfalto a hierba en 1445-1451 m y una vuelta manual que meta las ruedas en la hierba); (3) la dispersión: corregir el cabeceo del coche con la
  orientación del log y promediar más vueltas; (4) escribir `bordes_video.json` con el formato de `bordes_logs`
  solo cuando (2) esté medido; (5) preguntar antes de tocar `observaciones_logs.json`.

## D6 (2026-11-08): borde derecho y límite de carrera sin vuelta manual

- **Por qué el derecho salía mal:** la pista mide ≈ 10 m, el coche va pegado a la izquierda (línea a −3,3 m) y el borde derecho queda
  en X ≈ +6,9 m; a 6 m por delante la cámara (70°) solo ve ±4,2 m, así que ese borde solo entra en el encuadre más lejos. No era
  un fallo del detector sino de mi rango (3,6-9,6 m). Con `--fila-min 440 --z-max 22` (hasta ≈ 22 m) la línea derecha se ve en el 97 %
  de la vuelta y la izquierda en el 99 %.
- **Dos arreglos del detector:** (1) de las rectas bien apoyadas se elige la **más cercana al coche** (el borde), no la de más puntos:
  el pit lane (−8 a −11 m en 229-419 m) es blanco y fino pero está por fuera; (2) por metro se pondera 1/Z² (lo cercano pesa más).
- **Acuerdo lejos / cerca:** donde las dos medidas existen, diferencia mediana 0,01-0,02 m y el 93-97 % a menos de 0,3 m.
- **Frente a las cotas por ruedas de los logs antiguos** (solo horquillas válidas y estrechas, −0,3 < ancho < 0,3 m; **corregido: antes
  entraban horquillas cruzadas por decenas de metros**): izquierda 516 m, error mediano +0,24 m (rango intercuartil 0,13-0,33);
  derecha 228 m, −0,12 m (−0,21 a −0,03); el 96-98 % a menos de 1 m de la mediana. Lectura: desplazamiento común de la cámara de
  +0,06 m y límite de carrera 0,18 m más allá de la línea a cada lado (incluye el error de la semivía de 0,85 m supuesta).
- **Resultado (`mapa_bordes_video.json`, un `Mapa` con `borde_izq` / `borde_dcha`):** límite de carrera en el 97 % (izq) y el 96 % (dcha)
  de la vuelta; **ancho mediana 10,87 m (p10-p90 9,99-13,07)** frente a los 5,4 m comprobados. Se descartaron 145 m con un ancho imposible
  (< 7 o > 14,5 m: pit lane, línea vista dos veces) y se rellenaron huecos de hasta 15 m. Constantes en `bordes_video.py`
  (`SESGO_CAMARA_M`, `LIMITE_FUERA_M`, `ANCHO_PLAUSIBLE_M`).
- **Qué NO está comprobado:** (1) el límite 0,18 m sale de las cotas de los logs antiguos, que dependen de la semivía supuesta; el
  paso de asfalto a hierba en 1445-1451 m y una vuelta manual que meta las ruedas en la hierba lo verificarían de forma independiente; (2) **donde hay
  piano o franja legal (terrenos 10, 25, 48...) el límite de carrera es el borde exterior del piano, no la línea: el vídeo lo subestima** (la unión de V102 lo
  cubre solo donde ya se pisó); (3) curvas ciegas y cuestas: la línea no se ve y la
  mediana móvil puede tapar un tramo corto; (4) una sola sesión, 2 vueltas, seco y nublado.
- **Siguiente:** estudio sin juego del tiempo previsto con este pasillo (como V100, `linea_optima.py`); si compensa, ensanchado
  progresivo con el teacher (V100) usando este mapa como techo y no el ensayo y error.

## D7 (2026-11-08): etiquetas automáticas y primer segmentador del pasillo (pensado para otras pistas)

- **Por qué:** el detector de color de D5-D6 usa que la pista tiene línea blanca y buen contraste. Falla donde no hay línea (circuitos
  urbanos), con lluvia, atardecer o sombras. Un segmentador entrenado con etiquetas **automáticas** no necesita dibujar nada a mano y se
  puede reentrenar con cada pista nueva que tenga mapa y límites.
- **Etiquetas (`src/etiquetas.py`):** el pasillo entre `borde_izq` y `borde_dcha` del mapa se proyecta sobre cada fotograma con la cámara
  de D5, el rumbo y la posición del log y la **altura del mapa** (cuestas: un punto de la calzada está por debajo de la cámara
  `altura − (y_punto − y_coche − pendiente · Z)`). Comprobado sobre 12 fotogramas repartidos por la vuelta (curvas, cuestas y piano):
  la línea blanca implícita cae sobre la línea real, y en 1425 m el límite de carrera cae dentro del piano (que el juego da como legal: ahí el límite
  está más afuera, ver D10). Valida toda la cadena (cámara, rumbo, mapa, constantes). La carrocería del coche (morro y ruedas) va marcada 255 y no se entrena.
- **Conjunto (`src/crear_dataset.py`):** 1563 fotogramas de las dos vueltas de `2026-11-08_2` (1 de cada 30), 256×144, 104 MB en
  `video_vuelta/data/` (no se versiona).
- **Red (`src/segmentador.py`):** U-Net pequeña de PyTorch puro (16-32-64-96 canales), sin `ultralytics`, `torchvision` ni `scipy`; CPU
  (torch 2.11+cpu: la RX 6600 XT no entrena con PyTorch en Windows). 53 s por época con el Ryzen 7 5800X; 20 épocas ≈ 19 min.
  Entrena con s < 2400 m y **valida con s ≥ 2400 m** (un tramo que no ha visto, en las dos vueltas).
- **Resultado (`modelos/pasillo_v1.pt`):** IoU de validación **0,94** (0,928 a la primera época; se estanca en 0,94: el techo parece el ruido de
  las propias etiquetas). Error lateral del borde frente a la etiqueta, mediana en metros: 0,00-0,25 hasta 8 m por delante; 0,3-0,8 a 12-20 m
  (con 256×144 una fila equivale a ≈ 1,4 m de profundidad a 16 m); **percentil 90 ≈ 1,1-1,2 m a 6-8 m: hay fotogramas que fallan** (p. ej. los
  cuadros de la línea de salida, que se comen un trozo de pasillo). A ojo, en muchos fotogramas la predicción sigue el borde real mejor que la
  etiqueta. Es una prueba de concepto, **no** mejora al detector de color en Sugo (rango intercuartil ±0,1-0,2 m).
- **Qué NO está probado:** la generalización a otro circuito (no hay vídeo de otro; todas las grabaciones son de Sugo en seco y nublado), a
  mojado ni a otro coche o cámara. Eso es lo que justifica la red, y solo se puede comprobar con un segundo circuito.
- **Cómo añadir un circuito (sin código nuevo):** (1) línea de referencia: `PCARS2-AI/src/reference_recorder.py --source ai --laps 3 --output
  refs/<pista>_ai.json` (la IA del juego, sin conducir); (2) mapa: `mapa.construir` y guardarlo en `circuito_virtual/pistas/<pista>/mapa.json`;
  (3) una vuelta del piloto automático a 30 km/h con `aislado.py --teacher-only --speed-band 30 --reference <esa línea>` grabada con las
  condiciones de D2 y `comprobar_graficos.py` antes; (4) manifiesto y `sincronia.py`; (5) `bordes_video.py` (límites; si no hay línea blanca el detector
  de color no vale y ahí entra la red); (6) `crear_dataset.py` y reentrenar con las pistas juntas, validando con una pista que no se ha usado.
  La cámara y las constantes de límite dependen del coche y del juego, no de la pista.
- **Siguiente:** la prueba de verdad es un segundo circuito; mientras tanto, la red es útil donde el detector de color falla en Sugo y sirve de
  base si algún día el coche ve el borde (BC / PPO).

## D8 (2026-11-08): segundo vídeo, el de las 12.41 (vuelta a mano con teclado, hasta 184 km/h, detalle de pista 0)

- **Para qué:** comprobar con un vídeo independiente (otra conducción, otra velocidad, otros gráficos) lo medido con el de las 16.20.
  Se procesó sin escribir nada junto a su manifiesto (`bordes_video.procesar`, ahora con `v_min_kmh` / `v_max_kmh`).
- **Línea blanca frente a la de las 16.20** (mismos metros): izquierda mediana **+0,05 m**, rango intercuartil −0,24..+0,21 (59 % a menos de
  0,3 m); derecha mediana **−0,19 m**, −0,45..+0,11 (45 %). Límite de carrera igual (+0,05 y −0,19 m): las constantes de D6 valen entre
  vídeos en la izquierda y la derecha queda 0,19 m más adentro en este.
- **Por velocidad:** a más de 110 km/h (rectas) la izquierda coincide mejor, IQR −0,07..+0,19 m (71 % a menos de 0,3 m), y la derecha tiene
  un sesgo de **−0,25 m** (IQR −0,45..−0,02); a 5-60 km/h (118 fotogramas, horquillas y curvas lentas con el coche cruzado) la dispersión
  es la peor (IQR −1,1..+0,4). Lectura: lo que estropea la medida no es ir rápido sino (a) las curvas cerradas, donde la línea no es una
  recta sobre ≈ 20 m, y (b) a alta velocidad el cabeceo del chasis (el borde derecho está a ≈ 7 m y es más sensible: el error crece con X).
  Aún no corregido: el log trae `ride_height` por rueda, de donde sale el cabeceo del chasis frente a la calzada; es la mejora siguiente.
- **Red de D7 aplicada a ese vídeo** (nunca visto; 224 fotogramas con etiqueta, etiquetas = límites del de las 16.20 proyectados): IoU **0,936**
  (0,939 en validación), con otra conducción, otra velocidad y otros gráficos.

## D9 (2026-11-08): calibración de la cámara reproducible y plan del campo de visión de 90°

- **`src/calibrar_camara.py <manifiesto> [--escribir]`:** repite la calibración de D5 en un comando para cualquier vídeo con al menos una vuelta
  a velocidad constante: para cada cruce de meta del log mide la fila de la línea de meta en los 3 s anteriores y 0,8 s posteriores (la línea sigue a
  la vista ≈ 3 m tras el cruce del log porque la cámara va detrás: son las filas más cercanas, las que más pesan) y ajusta altura, cabeceo y distancia al
  punto del log. **Cada cruce lleva su propio `atras_m`**: el instante del cruce solo se conoce a ±1 tick del log (±0,14 m a 30 km/h, ≈ 20 px cerca de la
  cámara); con uno compartido el ajuste daba 5,3 px de rms y con uno por cruce **0,39 px**. Recorta fotogramas atípicos.
- **Resultado con `2026-11-08_2`:** altura **1,009 m**, cabeceo **5,88°**, cámara a 2,88 m del punto del log (2,97 y 2,80 por cruce), horizonte en la
  fila 399 (medido en las imágenes: 396-403). Coincide con el ajuste manual de D5 (1,02 m, 5,98°, 3,01 m) dentro del 1 %. **Las constantes de D6 (0,06 y
  0,18 m) se midieron con la cámara de D5, así que no se cambian los valores por defecto de `Camara` hasta repetir D6 con el cabeceo corregido.**
- **Vídeos de otras fuentes (p. ej. YouTube):** sin el log (posición, rumbo y velocidad) no se puede colocar nada sobre el mapa ni calibrar la cámara, así que
  no sirven para validar las constantes ni el cabeceo. Solo valen para mirar a ojo si la red de D7 segmenta otros circuitos, y solo si son de cámara de capó
  con el HUD apagado; con otra cámara el desajuste de dominio engaña. Los datos buenos de otros circuitos salen del propio juego (procedimiento de D7).
- **Campo de visión de 90° (a probar):** a 70° el borde derecho (a ≈ 7 m) solo entra en la imagen desde ≈ 11 m; a 90° entraría desde ≈ 7 m, donde la
  medida es mejor (menos error de profundidad y de rumbo). Cuesta densidad de píxeles en el centro (focal 960 px frente a 1371). Procedimiento: cambiar solo
  el campo de visión de la cámara de capó (que siga siendo horizontal), grabar 2 vueltas del piloto a 30 km/h con el mismo comando, manifiesto con
  `campo_de_vision_horizontal_deg: 90`, `calibrar_camara.py` y comprobar la focal con la proyección de límites sobre los fotogramas (`etiquetas.py`): si la
  focal fuera otra, las líneas proyectadas se separarían de las reales hacia los bordes de la imagen. La máscara de carrocería de `etiquetas.carroceria` está
  medida para 70° y habrá que recalcularla para otro campo de visión.
- **Siguiente:** (1) cabeceo del chasis con `ride_height` (D8); (2) 90°; (3) antialiasing.

## D10 (2026-11-08): corrección sobre el piano y herramienta para verificar el límite

- **Corrección:** `TERRAIN_RUMBLE_STRIPS` (10), `EXIT_RUMBLE_STRIPS` (25) y los demás pianos están en `RACING_TERRAIN_IDS`: son **superficie legal**. En D5-D7
  los traté como «fuera» (el 10 de 1400-1447 m, «el juego marcó fuera» en 1425 m); no es así: lo que el juego marca fuera en ese tramo es la hierba (7),
  en 1445-1451 m. Frases corregidas en su sitio.
- **Qué cambia:** (1) las constantes de D6 (cámara +0,06 m, límite 0,18 m más allá de la línea) salen de las horquillas estrechas de los logs antiguos, que están
  donde el asfalto pasa **directo a hierba** (ahí el asfalto sigue ≈ 0,2 m tras la pintura); valen para ese caso. (2) **Donde hay piano, el límite legal es el
  borde exterior del piano y el vídeo lo subestima** (la línea blanca queda dentro): el pasillo de V102 es la unión de lo comprobado con las ruedas y del vídeo, y
  solo cubre los pianos donde ya se pisó. (3) La clase «pasillo» de la red de D7 es «asfalto hasta la línea (+ ≈ 0,2 m)», no «superficie legal».
  (4) Hay más recorrido legal del que el vídeo dice, sobre todo en curvas con piano largo (C4, C1, C11...).
- **`src/verificar_limite.py <log> [--bordes mapa_bordes_video.json]`:** de un log con posición y terreno (de `sesion_manual.py`, sin vídeo) saca los cruces
  asfalto → fuera (y fuera → asfalto) de cada lado y compara la posición de la rueda (`n ∓ 0,85`, la misma semivía de `bordes_logs.py`, así se cancela) con el límite del
  vídeo en ese metro; da el error mediano, el rango intercuartil y los cruces a más de 0,5 m. **Solo hay cruce donde la rueda llega a hierba, grava...; cruzar
  la línea hacia un piano no cuenta.** Con 55 tests en total. Es la verificación independiente de las constantes de D6: si el error mediano sale ≈ 0, valen; si no,
  se ajustan `SESGO_CAMARA_M` y `LIMITE_FUERA_M` y se repite D6 y V102.
- **Qué falta medir:** el borde exterior del piano (la hierba tras él): detectarlo por color (verde) o con una clase «legal» de la red, y verificarlo con cruces
  de piano a hierba; sin eso el potencial de la trazada en curvas con piano está por debajo de lo real.

## D11 (2026-11-08/09): reglas del límite acordadas con el usuario, verificación con dos vueltas manuales y mapa de bordes corregido

- **Vueltas (solo log, `sesion_manual.py --lado izq|dcha --laps 1 --velocidad-auto 30`):** el programa lleva gas y freno por un mando virtual y el usuario solo gira,
  haciendo zigzag hacia el lado cuyo borde se mide cada ≈ 3,6 s (30 m a 30 km/h). Lado izquierdo `20261108T215747Z_sugo_gp_mapeo_izq.jsonl` (vídeo `22.57`) y lado
  derecho `20261108T230117Z_sugo_gp_mapeo_dcha.jsonl` (vídeo `2026.11.09-00.01`); los dos vídeos son utilizables (1920×1080, 100 % a periodo exacto, sin fotogramas rotos,
  un hueco en el último fotograma). La primera mitad de la vuelta izquierda fue a 44-46 km/h (el control estaba más suave que el pedal del usuario) y el resto a
  30,0 km/h; la derecha fue a 30 km/h toda la vuelta. **Sincronía:** el arranque desde parado no vale con un log que empieza a mitad de vuelta (la derecha); se calcula por
  correlación del giro del log con el desplazamiento horizontal de la imagen: **t_log = t_vídeo + 7,40 s (izq) y + 8,55 s (dcha)**, correlación 0,97.
- **Verificación de D6 (`verificar_limite.py`):** izquierda, 123 cruces, error mediano **+0,11 m** (IQR −0,04…+0,28; 57 % a menos de 0,3 m); derecha, 150 cruces, mediano
  **−0,06 m** (IQR −0,43…+0,31; 45 % a menos de 0,3 m). Las constantes (0,06 y 0,18 m) valen de media, pero **la dispersión es grande: 43 cruces a la izquierda y 53 a la
  derecha caen a más de 0,5 m** y el mapa del vídeo falla entre 0,6 y 1,8 m en los dos sentidos (curvas, pasillos de asfalto fuera de la línea, pianos).
- **Reglas del límite (acordadas viendo ≈ 35 fotogramas, uno por uno, con el usuario):**
  1. El límite es la **línea blanca continua**. Pasar la línea no se penaliza legalmente, pero se pierde agarre y velocidad, así que no gana nada. Donde fuera de la línea hay
     un pasillo de asfalto (recta final izquierda, C1 entrada derecha, C2 entrada izquierda) **no cuenta** (el terreno 46, `TERRAIN_RUNOFF_ROAD`, es ese asfalto: ilegal).
  2. **Donde hay piano, el límite es su borde exterior.** Se puede usar en la salida de la curva con el volante casi recto. Los pianos de C4, C9, C10, C12 y C13 tienen dos
     partes: una interior plana y lisa (terreno 48, pintado; no está en `pcars2_surface.py` pero se toma como legal) y una banda exterior rugosa (10); **cuenta solo la plana**.
     Si el log no distingue las dos, el piano vale entero («ya ajustaremos en pruebas»).
  3. **Lo que hay detrás del piano no cuenta:** el parche de asfalto de C4 y C9, la moqueta verde de C11 (frena; en el log sale como 7) y la isleta de cemento de C3. En C3
     el límite es el piano.
  4. En C13 salida, donde no hay línea ni piano (bloques de hormigón de otro trazado separados por línea discontinua), el límite es el **borde del asfalto**, que enlaza con
     la línea de antes y de después. El 48 de ahí es la base de los bloques y no cuenta.
  5. El asfalto que se pisa de nuevo tras salir (entrada a boxes en 3219 m, patches tras el piano) no cuenta.
- **`src/mapa_corregido.py <log izq> <log dcha> [...]`:** por metro y lado, cota inferior (rueda más exterior legal hasta la primera superficie ilegal) y cota superior (rueda
  ilegal más interior que esté a más de 0,3 m del eje), y se combinan con el vídeo: con las dos a menos de 0,6 m, punto medio (σ 0,1-0,15 m); si no, el vídeo recortado a las
  cotas que lo cambian (> 0,1 m; σ 0,4 m); y la corrección se propaga a los vecinos (interpolada entre dos anclas a menos de 50 m, o mantenida 8 m y atenuada hasta 25 m;
  σ 0,6 m). Salida: `capturas/sugo_gp/formula_r/2026-11-08_2/mapa_bordes_corregido.json` (mismo formato que `mapa_bordes_video.json` más `sigma_*`, `fuente_*`, `delta_*`).
  Con las dos vueltas: horquilla en 378 m (izq) y 337 m (dcha), propagado en 2309 y 2063 m, solo vídeo en 184 y 302 m; ancho mediano del límite 10,79 m (vídeo 10,88 m).
  Un contacto ilegal con menos de 0,3 m «hacia fuera» (el coche en la hierba del otro lado) se ignora: sin eso el pasillo salía invertido en 1250-1410 m.
- **Validación cruzada** (se quita la horquilla de cada metro con sus vecinos ±4 m y se predice su corrección): error mediano 0,18 → 0,12 m (izq) y 0,36 → 0,21 m (dcha); p90
  1,04 → 0,56 m y 1,11 → 0,56 m; la corrección mejora al vídeo solo en el 58 % y el 70 % de los metros. Comparar con los mismos cruces (57 → 95 % y 45 → 94 % a menos de 0,3 m) es
  circular: el mapa se ajustó con ellos.
- **Límites:** el borde exterior del piano solo se conoce donde una rueda lo alcanzó (C9 salida 2088 m queda con el límite del vídeo, que lo subestima); unos 200 m por lado
  quedan más estrechos que lo que ya pisaron las ruedas en los logs antiguos (recta tras C8 en 1355-1444 m, C4 derecha en 799-835 m...), sobre todo parches, franjas y la
  pintura 49 dentro del piano de la recta tras C8; **solo el 20 % de la vuelta tiene horquilla de las ruedas y cerca del 60 % es corrección propagada**.
- **Estudio de trazada con este mapa (V103 de `circuito_virtual/docs/DECISIONES.md`):** −0,67 s previstos con margen 0,6, pero solo −0,08 s si los metros propagados o del
  vídeo se acercan 0,3 m a la pista. Antes de escribir nada en `observaciones_logs.json`, verificar esos metros con una vuelta extra de zigzag por lado.

## D12 (2026-11-09): pasillo y línea para la sesión, herramientas de sincronía y revisión, y cierre para Sugo

- **Pasillo preparado:** `circuito_virtual/pistas/sugo_gp/observaciones_pasillo_d11.json` (`pasillo_a_observaciones.py` sobre `mapa_bordes_corregido.json`; ancho mediano de la rueda 10,79 m, mínimo
  8,22 m). **`observaciones_logs.json` no se ha tocado**: `linea_optima.py` gana `--observaciones <archivo>` (por defecto el de siempre) para elegir el pasillo. Las excepciones de Sugo salen del código
  a `circuito_virtual/pistas/sugo_gp/reglas_limite.json` (`mapa_corregido.py --reglas`; sin ese archivo no hay excepciones); el mapa corregido sale idéntico.
- **Línea nueva `sugo_optima_a1mu9c12d11`** (mismos parámetros que `a1mu9c12` y margen 0,6; solo cambia el pasillo): **117,773 s previstos frente a 118,447 s**, holgura mínima de la rueda al borde 0,52 m
  (en 772-773 m y 816-822 m, salida de C4; 9 m con menos de 0,6 m). El ápice de cada curva queda 0,3-0,8 m más por dentro que en `a1mu9c12` (C1 +0,75 m, C2 +0,82 m, C4 −0,49 m, C5 −0,50 m, C10 −0,42 m...); la
  diferencia media |Δn| es de 0,48 m y la máxima de 3,91 m, en 1917 m (recta antes de C9, donde el pasillo viejo era muy estrecho). Los `.json` de las líneas no se versionan; el `_n.npy` sí. Comando en `PROCEDIMIENTO.md`.
- **`src/sincronia_giro.py`:** desfase por correlación del giro del log con el desplazamiento horizontal de la imagen. Reproduce los +8,55 s (correlación 0,965) donde `sincronia.py` dio −10,18 s por un log que empezaba
  a mitad de vuelta. **`src/tramos_dudosos.py`:** lista los tramos con cruces a más de 0,5 m del límite con su instante de vídeo, su curva y la secuencia de terrenos de las dos ruedas, y guarda un fotograma por tramo
  para revisarlos con el usuario uno por uno (así se hizo D11). Con tests.
- **Qué falta para dar el pasillo por bueno:** la sesión (Sesión D, `--reference` con la línea nueva) y, si salen ruedas fuera donde no se esperaban, una vuelta extra de zigzag por lado con el mapa corregido como
  `--bordes`. El 60 % de la vuelta es corrección propagada, no medida.
- **Cierre:** `video_vuelta` queda **terminado para Sugo con el Formula R** como herramienta de medición. Quedan opcionales (no necesarios para Sugo): 90° de campo de visión, cabeceo con `ride_height`, antialiasing, clase «piano»
  en la red, segundo circuito y la vuelta extra de zigzag. Documentación reordenada: `README.md` (estado e índice de scripts), `PROCEDIMIENTO.md` (guía para otra pista), este registro con índice, `DEBATE.md` como histórico.
