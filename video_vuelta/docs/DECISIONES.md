# Decisiones de video_vuelta

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
- **Pendiente:** filtro de texturas anisotrópico y resolución de texturas más alta (hoy
  `texturefilter="5"`, `textureresolution="2"`); `comprobar_graficos.py` antes de cada sesión.

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

