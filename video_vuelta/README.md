# video_vuelta/

Grabar la vuelta en vídeo y sacar de ella lo que el UDP no da: los bordes reales de la pista, la línea
blanca y la franja, y más adelante una observación visual para BC / PPO. Nace de la idea D1c de
`circuito_virtual/docs/PENDIENTE.md` (2026-11-08) pero se plantea desde el principio para **cualquier
pista y cualquier coche**, no solo para Sugo con el coche actual.

**Estado (2026-11-08, tarde):** hecho de extremo a extremo para Sugo con el Formula R: gráficos fijados, vídeo automático a 30 km/h, cámara calibrada,
línea blanca y límite de carrera medidos (10,87 m de ancho frente a 5,4 m comprobados), estudio de trazada (−0,62 s previstos), etiquetas automáticas y
primer segmentador (IoU 0,94); 55 tests. **Pendiente y orden de la próxima sesión:** «Al retomar» 1b de `circuito_virtual/docs/PENDIENTE.md`; decisiones D2-D10
en `docs/DECISIONES.md`. **Aviso:** el piano es superficie legal (D10) y el vídeo subestima el límite donde lo hay; la generalización a otro circuito no está probada.

## Reglas

1. **Dependencia en un solo sentido:** `PCARS2-AI` ← `circuito_virtual` ← `experimental` y
   `video_vuelta`. Esta carpeta puede importar de `PCARS2-AI/src` y de `circuito_virtual/src` (el mapa
   `(s, n)`, los cruces de terreno de `bordes_logs`). Ninguna de ellas importa de aquí: el resultado
   (`bordes_video.json` de cada pista) se escribe en `circuito_virtual/pistas/<pista>/` como un dato
   más, con el mismo formato que ya leen `bordes_logs` y `linea_optima.py`.
2. **Análisis fuera de línea.** No se toca el juego ni el bucle de producción: se graba, se guarda el
   vídeo junto con el nombre del log y se analiza después.
3. **Nada propio de Sugo en el código.** Pista, coche y cámara son parámetros; lo que cambie entre
   pistas o coches vive en un manifiesto, no en constantes.
4. **Los vídeos no se versionan** (pesan GB); sí se versionan los manifiestos, los parámetros de
   cámara calibrados y los resultados pequeños.
5. **Tests propios** en `video_vuelta/tests/`, con fotogramas sintéticos, fuera de las otras suites.
6. **Cada paso termina en una decisión** anotada en `docs/DECISIONES.md` (se crea con la primera).

## Estructura

| Ruta | Contenido |
| --- | --- |
| `docs/DEBATE.md` | Qué queremos del vídeo, qué es general y qué no, preguntas abiertas y orden propuesto |
| `src/comprobar_video.py` | Comprueba un vídeo: resolución, fotogramas perdidos y si el codificador lo ha roto |
| `src/sincronia.py` | Desfase vídeo-log por el arranque desde parado; saca el fotograma de cualquier distancia de vuelta |
| `src/comprobar_graficos.py` | Compara el XML gráfico del juego con `perfiles/graficos.json` y la resolución de la captura |
| `src/camara.py` | Cámara de capó: píxel ↔ suelo y calibración (altura, cabeceo) con la línea de meta |
| `src/lineas.py` | Detecta la línea blanca de cada lado en un fotograma (por su ancho en metros) |
| `src/bordes_video.py` | Vídeo + log + mapa → `n` de la línea blanca por metro (`linea_blanca.json`) y validación con los logs antiguos |
| `src/calibrar_camara.py` | Calibra altura, cabeceo y posición de la cámara con la línea de meta en los cruces del vídeo (repetir si cambia el campo de visión) |
| `src/verificar_limite.py` | Con un log que mete las ruedas en la hierba, compara los cruces asfalto → fuera con el límite medido por vídeo |
| `src/etiquetas.py` | Proyecta el pasillo medido sobre cada fotograma (con cuestas): máscara automática |
| `src/crear_dataset.py` | Vídeo + log + mapa de bordes → fotogramas y máscaras para entrenar (`data/`, no se versiona) |
| `src/segmentador.py` | U-Net pequeña de PyTorch puro, entrenable en CPU; valida por tramos de pista |
| `modelos/` | Modelos entrenados (pequeños, se versionan) |
| `tests/` | Tests (`cd video_vuelta; python -m pytest`) |
| `capturas/<pista>/<coche>/<fecha>/` | Vídeos y su manifiesto (no se versionan los vídeos) |
| `data/` | Fotogramas extraídos y salidas intermedias (no se versionan) |
