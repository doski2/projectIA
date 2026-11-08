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

## 6. Orden y estado (2026-11-08)

1. **V0, formato:** hecho. Manifiesto y convención de carpetas (D1 de `DECISIONES.md`); primer manifiesto en
   `capturas/sugo_gp/formula_r/2026-11-08_1/`.
2. **V1, cualitativo:** hecho con una vuelta de teclado (D3): se ve más asfalto y piano que lo comprobado en
   C1, C4 y C11; a ojo no se puede decir si es 1 m.
3. **V2, sincronía:** hecha por el arranque desde parado (`sincronia.py`, `t_log = t_vídeo + 8,901 s`).
   **Falta medir su error** con el cruce de meta.
4. **V3, cámara:** pendiente. Necesita fotogramas con una rueda sobre piano o hierba (los cruces de terreno
   por rueda del log); la vuelta del 08-11 tiene todos los terrenos a 0 (asfalto).
5. **V4-V5, detección y proyección** sobre `(s, n)`: pendiente.
6. **V6, validación** y escritura de `bordes_video.json`; solo entonces la fase B (vueltas lentas): pendiente.
7. **Segunda pista o coche** como prueba de que de verdad es general: pendiente.

## Pendiente para la próxima sesión (el mismo texto, con comandos, está en `circuito_virtual/docs/PENDIENTE.md`, «Al retomar» 1b)

1. Filtro de texturas anisotrópico y texturas más altas en el menú; reiniciar y leer el XML para saber qué
   número es cada opción. Comprobar 1920×1080 y anotar la tasa de bits exacta de Radeon.
2. Dos vueltas manuales con vídeo, una por lado, a ≈ 40 km/h o con el limitador, con
   `sesion_manual.py --lado izq|dcha --laps 1`; una tercera zigzagueando, opcional.
3. `comprobar_graficos.py` (XML + captura frente al perfil de D2).
4. Error de la sincronía con la meta; después V3-V6.
5. Preguntar si se añaden esas vueltas a las cotas con `bordes_logs.py actualizar`.

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
