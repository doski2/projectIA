# video_vuelta/

Grabar la vuelta en vídeo y sacar de ella lo que el UDP no da: los **bordes reales de la pista** (el límite de carrera de cada lado, por metro), y más adelante una observación visual para
BC / PPO. Nace de la idea D1c de `circuito_virtual/docs/PENDIENTE.md` (2026-11-08) y está pensada para **cualquier pista y cualquier coche**; hecha de extremo a extremo con Sugo GP y el Formula R.

**Para una pista nueva, empezar por [`docs/PROCEDIMIENTO.md`](docs/PROCEDIMIENTO.md)** (pasos, comandos, qué es de Sugo y qué no, trampas). Decisiones y cifras de cada paso: `docs/DECISIONES.md`.

## Estado (2026-11-09)

- **Terminado para Sugo con el Formula R:** gráficos fijados, vídeo automático a 30 km/h, cámara calibrada, línea blanca y límite de carrera medidos (10,87 m de ancho frente a 5,4 m comprobados por ruedas),
  verificación con dos vueltas manuales (error mediano +0,11 m izq y −0,06 m dcha, con mucha dispersión), reglas del límite acordadas con el usuario viendo los fotogramas (D11), mapa corregido
  (`mapa_corregido.py`, validación cruzada: error mediano 0,18 → 0,12 m y 0,36 → 0,21 m), pasillo y línea nueva (`sugo_optima_a1mu9c12d11`, D12).
- **Previsto con el pasillo corregido:** 117,773 s frente a 118,447 s (−0,67 s, margen 0,6; solo −0,08 s si lo propagado se acerca 0,3 m). Es un cálculo del solver (μ 9, tope 125 km/h): **falta la sesión
  que lo pruebe** (Sesión D en «Comandos vigentes» de `circuito_virtual/docs/PENDIENTE.md`).
- **Sin probar:** otro circuito (la red de D7 no está validada fuera de Sugo), mojado, otro coche u otra cámara.
- **Opcional, por si no cuadra algo:** una vuelta extra de zigzag por lado para verificar los metros propagados; 90° de campo de visión; cabeceo con `ride_height`; clase «piano» en la red.

## Reglas

1. **Dependencia en un solo sentido:** `PCARS2-AI` ← `circuito_virtual` ← `experimental` y `video_vuelta`. Esta carpeta puede importar de `PCARS2-AI/src` y de `circuito_virtual/src`
   (el mapa `(s, n)`, los cruces de terreno de `bordes_logs`). Ninguna de ellas importa de aquí. Lo que sale de aquí y usa `circuito_virtual` se escribe en `circuito_virtual/pistas/<pista>/`
   como un dato más (`observaciones_pasillo_d11.json`, `reglas_limite.json`) y `linea_optima.py` lo lee con `--observaciones`.
2. **Análisis fuera de línea.** No se toca el juego ni el bucle de producción: se graba, se guarda el vídeo junto con el nombre del log y se analiza después.
3. **Nada propio de una pista en el código.** Pista, coche y cámara son parámetros: lo que cambia entre pistas vive en un manifiesto o en `pistas/<pista>/reglas_limite.json`. Las constantes de coche y juego
   (`SESGO_CAMARA_M`, `LIMITE_FUERA_M`, `ANCHO_PLAUSIBLE_M`) están en `bordes_video.py` y se verifican con `verificar_limite.py` en cada coche o pista.
4. **Los vídeos no se versionan** (pesan GB); sí se versionan los manifiestos, la cámara calibrada y los resultados pequeños.
5. **Tests propios** en `video_vuelta/tests/`, con fotogramas y logs sintéticos.
6. **Cada paso termina en una decisión** anotada en `docs/DECISIONES.md`. Las reglas del límite de cada pista las decide el usuario viendo los fotogramas, uno por uno.

## Estructura

| Ruta | Contenido |
| --- | --- |
| `docs/PROCEDIMIENTO.md` | Guía paso a paso para una pista nueva, con comandos, lo que es de Sugo y las trampas |
| `docs/DECISIONES.md` | Registro de decisiones D1-D12 (con índice) |
| `docs/DEBATE.md` | Histórico: qué queríamos del vídeo, qué es general y qué no (2026-11-08) |
| `src/comprobar_graficos.py` | Compara el XML gráfico del juego con `perfiles/graficos.json` y la resolución de la captura |
| `src/comprobar_video.py` | Comprueba un vídeo: resolución, fotogramas perdidos y si el codificador lo ha roto |
| `src/sincronia.py` | Desfase vídeo-log por el arranque desde parado; saca el fotograma de cualquier distancia de vuelta |
| `src/sincronia_giro.py` | Desfase por correlación del giro, para logs que no empiezan con el coche parado |
| `src/camara.py` | Cámara de capó: píxel ↔ suelo y calibración (altura, cabeceo) con la línea de meta |
| `src/calibrar_camara.py` | Calibra altura, cabeceo y posición de la cámara con la línea de meta (repetir si cambia el campo de visión) |
| `src/lineas.py` | Detecta la línea blanca de cada lado en un fotograma (por su ancho en metros) |
| `src/bordes_video.py` | Vídeo + log + mapa → `n` de la línea blanca por metro, límite de carrera (`mapa_bordes_video.json`) y validación con los logs antiguos |
| `src/verificar_limite.py` | Con un log que mete las ruedas en la hierba, compara los cruces asfalto → fuera con un mapa de bordes |
| `src/tramos_dudosos.py` | Tramos con cruces a más de 0,5 m del límite, su instante en el vídeo y un fotograma de cada uno para revisarlos con el usuario |
| `src/mapa_corregido.py` | Mapa de bordes del vídeo corregido con las ruedas de las vueltas manuales y las reglas de la pista (`mapa_bordes_corregido.json`, con σ y fuente por metro) |
| `src/pasillo_a_observaciones.py` | Mapa corregido → archivo de observaciones para `linea_optima.py --observaciones` |
| `src/etiquetas.py` | Proyecta el pasillo medido sobre cada fotograma (con cuestas): máscara automática |
| `src/crear_dataset.py` | Vídeo + log + mapa de bordes → fotogramas y máscaras para entrenar (`data/`, no se versiona) |
| `src/segmentador.py` | U-Net pequeña de PyTorch puro, entrenable en CPU; valida por tramos de pista |
| `perfiles/` | Perfil gráfico de referencia (`graficos.json`) |
| `modelos/` | Modelos entrenados (pequeños, se versionan) |
| `capturas/<pista>/<coche>/<fecha>_<n>/` | Manifiesto, cámara calibrada y resultados; los vídeos no se versionan |
| `data/` | Fotogramas extraídos y salidas intermedias (no se versionan) |
| `tests/` | `python -m pytest video_vuelta/tests` |

Fuera de esta carpeta, y que forma parte del flujo: `circuito_virtual/src/sesion_manual.py` (graba el log de las vueltas manuales; con `--velocidad-auto 30` el programa lleva gas y freno y el usuario solo gira),
`circuito_virtual/src/linea_optima.py` y `circuito_virtual/pistas/<pista>/{mapa.json, curvas.json, reglas_limite.json, observaciones_pasillo_d11.json}`.
