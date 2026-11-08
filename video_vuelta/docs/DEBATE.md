# Debate: grabar la vuelta (para todas las pistas y coches)

Documento vivo. Aquí se discute y se decide; lo decidido pasa a `DECISIONES.md` (D1, D2...) con la
fecha. Punto de partida: D1c en `circuito_virtual/docs/PENDIENTE.md` («Al retomar», tareas 1 y 9, y
«Siguiente», punto 6).

## 1. Qué queremos del vídeo

| Uso | Qué da | Estado |
| --- | --- | --- |
| **A. Bordes de la pista** (D1c) | `n` izquierdo y derecho por metro: el pasillo real para la línea óptima | Diseñado en PENDIENTE, sin código |
| **B. Línea blanca, franja y hierba** | Lo que los ids de terreno no ven | Idea del usuario (V78) |
| **C. Mirar** | Comprobar a ojo dónde pierde el coche, qué ve el piloto en cada curva | Casi gratis: fotogramas en C1, C4 y C11 |
| **D. Observación visual para BC / PPO** | Una entrada de imagen además de la telemetría | Lejano; condiciona la captura (ver 3) |

Pregunta 1: ¿el alcance de la carpeta es solo A + B (medir la pista), o desde ya también D? Si es D,
la captura tiene que ser en directo y sincronizada por tick, no un archivo grabado aparte.

## 2. Lo que sabemos (de PENDIENTE)

- El entorno **no tiene ffmpeg ni OpenCV** (solo PIL y numpy). Haría falta
  `pip install opencv-python-headless imageio-ffmpeg`, con permiso del usuario.
- Condiciones de grabación acordadas: cámara de capó o parachoques, **HUD oculto**, campo de visión
  fijo, 1080p y 60 fps con bitrate alto, **empezando desde parado** para sincronizar con el log.
- Diseño D1c en 7 pasos: sincronizar → corregir por cabeceo y alabeo del UDP → calibrar la cámara con
  puntos de verdad → detectar por color en vista de pájaro → pasar al mundo y proyectar sobre el eje
  `(s, n)` → escribir `bordes_video.json` → validar con los cruces de terreno (éxito: error mediano
  ≤ 0,3 m en ≥ 90 % de la vuelta).
- Idea del usuario que lo hace fiable, **en dos fases**: (A) el vídeo de la sesión A da una estimación
  del borde; (B) vueltas lentas (30-40 km/h) con el centro del coche a estimación −0,3 / 0 / +0,3 m,
  y los cambios de terreno por rueda dan los puntos de verdad. ≈ 6 vueltas, ≈ 35 min.

## 3. Cómo capturar (decidido en D1 y D2: grabadora externa, Radeon ReLive; plan B, OBS)

| Opción | A favor | En contra |
| --- | --- | --- |
| **1. Grabadora externa** (OBS, ShadowPlay, Game Bar) | Cero código, calidad alta, ya disponible | Sincronizar con el log a mano (arranque desde parado); sin marca de tiempo común |
| **2. Captura desde Python** (dxcam / mss) a la vez que el bucle lee el UDP | Un fotograma por tick con su posición, rumbo y cabeceo; sirve para D | Gasta CPU y GPU en el mismo PC que el juego; riesgo de perder ticks |
| **3. Grabadora externa + marca de tiempo propia** (p. ej. un destello o reloj en una esquina, o un evento en el log que se vea en el vídeo) | Sincronía exacta sin tocar el rendimiento | Hay que inventar la marca |

Preguntas:

- ¿Qué usa el usuario hoy para grabar y qué cámara del juego deja el capó sin estorbo?
- ¿Aceptamos sincronizar por el arranque desde parado (error de unos pocos fotogramas) o queremos
  sincronía exacta?
- ¿Cuántos GB por vuelta aceptamos y dónde se guardan (hay que sacarlos de `projectIA/`)?

## 4. Qué es general y qué es de cada pista o coche

| General (código único) | Por coche / cámara (manifiesto) | Por pista (dato) |
| --- | --- | --- |
| Sincronización, proyección al mundo, detección por color, escritura de `bordes_video.json`, validación | Altura y cabeceo de la cámara, campo de visión, recorte del capó, ancho de vía | Colores de línea blanca, franja y hierba (distintos por pista y clima), ids de terreno |

Un **manifiesto** por grabación (`capturas/<pista>/<coche>/<fecha>/manifiesto.json`) con: archivo de
vídeo, log asociado, cámara, resolución, fps, instante de sincronización, reglaje, clima y condiciones.
Pregunta: ¿qué más tiene que guardar para que una grabación de dentro de un año siga siendo usable?

## 5. Riesgos y puntos débiles

- **Calibración:** una cámara de capó con pitch y roll variables mueve el suelo proyectado metros; sin
  puntos de verdad el error no se acota. De ahí las dos fases.
- **Colores:** sombras, lluvia y atardecer cambian la detección; probablemente hay que calibrar por
  grabación, no con constantes.
- **Pista que se pierde de vista:** las curvas ciegas y las cuestas ocultan el borde; hay que marcar la
  confianza por metro y no inventar.
- **Piano y franja** en el exterior: es justo lo que más interesa (V100) y lo más difícil de ver
  desde el capó.
- **Rendimiento del PC** si se captura a la vez que se conduce (opción 2).

## 6. Orden y estado (2026-11-08, al cierre de la tarde)

1. **V0, formato:** hecho (D1-D2): manifiesto, convención de carpetas y condiciones de grabación.
2. **V1, cualitativo:** hecho (D3): se ve más asfalto y piano que lo comprobado.
3. **V2, sincronía:** hecha (`sincronia.py`). Comprobada con un cruce de terreno independiente (1425 m, D5); sin medir el error con la meta porque la fórmula es la misma.
4. **V3, cámara:** hecha (`camara.py`, `calibrar_camara.py`, D5 y D9): altura 1,009 m, cabeceo 5,88°, 70° horizontales, rms 0,39 px. Se calibra con la línea de meta, no con cruces de terreno (la
   salida desde parado no vale; el instante del cruce en el log tiene ±1 tick y por eso cada cruce lleva su `atras_m`).
5. **V4-V5, detección y proyección:** hechas para la línea blanca (`lineas.py`, `bordes_video.py`, D5-D6) y para el pasillo con un segmentador (`etiquetas.py`,
   `crear_dataset.py`, `segmentador.py`, D7). Lo de color funciona donde hay línea blanca; la red es la vía para pistas sin ella (sin probar en otra pista).
6. **V6, validación:** hecha en parte: línea contra cotas por ruedas de los logs antiguos (D6), contra un segundo vídeo (D8, vuelta a mano a alta velocidad) y la red con un tramo no visto (D7).
   **Falta la verificación independiente de los 0,18 m** con una vuelta que meta las ruedas en la hierba (`verificar_limite.py`, D10).
7. **Corrección importante (D10):** el piano es superficie legal; el vídeo da la línea blanca y la constante vale donde hay hierba tras la línea; donde hay piano el límite legal es el exterior del piano.
8. **Estudio de trazada (V102):** pasillo unión (lo pisado ∪ vídeo), margen 0,6: **−0,62 s** previstos; con margen 1,0 no gana (+0,24 s). Manda el margen.
9. **Segunda pista o coche** como prueba de que de verdad es general: pendiente (D7 explica el procedimiento).

Mejoras abiertas, con su efecto esperado (D8-D9): campo de visión de 90° (ver el borde derecho desde ≈ 7 m en vez de ≈ 11 m), cabeceo del chasis con `ride_height` (sesgo −0,25 m del borde
derecho a más de 110 km/h), antialiasing (líneas lejanas rotas), red a 512×288. Más fps no ayuda; más resolución solo en lo lejano.

## Pendiente para la próxima sesión (el mismo texto, con comandos, está en `circuito_virtual/docs/PENDIENTE.md`, «Al retomar» 1b)

1. Vuelta manual metiendo las ruedas en la hierba (solo log, `sesion_manual.py`; el juego puede ir en ventana) y `verificar_limite.py`.
2. Grabar 2 vueltas con 90° de campo de visión; manifiesto, sincronía, `calibrar_camara.py --escribir`, comprobar la focal y recalcular la máscara de carrocería.
3. Cabeceo con `ride_height`; repetir D6 con la cámara de D9.
4. Antialiasing; borde exterior del piano; segundo circuito; versión manual a 30 km/h; red a 512×288.
5. Decidir el margen al borde y, solo entonces y preguntando, escribir el pasillo en `observaciones_logs.json`.

## 7. Herramientas de lectura de vídeo

ffmpeg es el decodificador que convierte el `.mp4` en fotogramas numpy; no hace falta instalarlo aparte:

| Opción | Cuándo |
| --- | --- |
| `opencv-python-headless` (~50 MB) | **Por defecto:** lee el vídeo y además hace vista de pájaro, color y corrección de lente |
| `av` (PyAV) | Solo si la sincronía necesita la marca de tiempo exacta de cada fotograma |
| `imageio-ffmpeg` | Descartada: solo lee y escribe, OpenCV ya lo cubre |
| Capturas con `mss` / `dxcam` | Solo si hace falta imagen en directo (uso D) |

## 8. Propuesta por defecto (aceptada el 2026-11-08; ver D1 y D2 en `DECISIONES.md`)

1. Carpeta `video_vuelta`; alcance A + B (medir la pista); D más adelante.
2. Grabadora externa (OBS o la que ya uses) y sincronía por el arranque desde parado; la marca de tiempo
   propia solo si el error resulta grande.
3. Instalar `opencv-python-headless` (con permiso).
4. Grabar ya la sesión A (V1, cualitativo) y mirar los fotogramas de C1, C4 y C11 antes de seguir.
