# Procedimiento: del juego al pasillo de una pista (y qué cambia con otra pista o coche)

Qué se obtiene al final, para una pista y un coche: un **pasillo** (el límite de carrera de cada lado, por metro, con su incertidumbre) en el formato de
`circuito_virtual` y la línea óptima que lo usa. Hecho de extremo a extremo con **Sugo GP y el Formula R** (2026-11-08/09); es la plantilla. Las decisiones y
cifras de cada paso están en `DECISIONES.md` (D1-D12); aquí solo lo necesario para repetirlo. Tiempo aproximado: una tarde, casi todo vídeos y revisar fotogramas.

Convenciones: `PY` = `C:\Users\doski\projectIA\.venv\Scripts\python.exe`; `<pista>` = `sugo_gp`; `<coche>` = `formula_r`; el juego en seco y sin sombras largas
(el detector de color falla con atardecer, lluvia y sombras: D7). Todos los scripts de `video_vuelta/src` tienen `--help`.

## 0. Antes de tocar el juego

1. **Mapa de la pista** `circuito_virtual/pistas/<pista>/mapa.json` (eje `(s, n)` a 1 m) y su línea suavizada; curvas numeradas `curvas.json`
   (`circuito_virtual/src/curvas.py`). Para una pista nueva: línea de referencia con `PCARS2-AI/src/reference_recorder.py --source ai --laps 3 --output refs/<pista>_ai.json`
   (la IA del juego, sin conducir) y `mapa.construir` (ver el docstring de `circuito_virtual/src/mapa.py`). Algunos scripts de `circuito_virtual` llevan `sugo_gp` por defecto
   (`PISTA` en `linea_optima.py`; `--salida-dir`, `--mapa`): revisar el `--help` de cada uno.
2. **Gráficos fijados** (D2): 1920×1080 a 60 Hz en pantalla completa, texturas y detalle de pista al máximo, HUD y línea de carrera apagados, cámara de capó con 70° horizontales y sin
   movimientos de cámara (ver D2). `PY video_vuelta/src/comprobar_graficos.py` compara el XML del juego con `perfiles/graficos.json`; el XML solo se reescribe al
   **cerrar** el juego (leerlo después). Si cambias el antialiasing, el campo de visión u otro ajuste, repetir la calibración (paso 3) y anotarlo en el manifiesto.
3. **Grabación con Radeon ReLive** «Dentro del juego», 60 fps, AVC, tasa de ≈ 65 Mb/s (con el tope en 100 Mb/s el codificador se hundió una vez a los 8,7 s y el vídeo quedó roto: `comprobar_video.py` lo detecta; con ≈ 65 Mb/s no ha fallado en ≈ 25 min de vídeo; plan B,
   OBS con el codificador de AMD y fotograma completo cada 1 s). Una vuelta por grabación; coche parado ≥ 5 s al empezar.

## 1. Vídeo automático a 30 km/h (calibrar y medir la línea blanca)

```text
PY experimental\common\aislado.py --teacher-only --speed-band 30 --reference <línea de la pista> --experiment <nombre> --laps 2
```

Con la grabación puesta antes de que acabe la espera inicial (`Start-Sleep -Seconds 60;` delante del comando). Después:

1. `PY video_vuelta/src/comprobar_video.py <video.mp4>`: debe salir «utilizable» (resolución, 100 % a periodo exacto, sin fotogramas rotos; un hueco en el último fotograma no importa).
2. Manifiesto en `video_vuelta/capturas/<pista>/<coche>/<fecha>_<n>/manifiesto.json` (plantilla en `DECISIONES.md`, «Convención de carpetas»; los vídeos no se versionan).
3. **Sincronía** (`t_log = t_vídeo + desfase`): `PY video_vuelta/src/sincronia.py <video> <log> --manifiesto <manifiesto.json>` (arranque desde parado). **Si el log no empieza con el coche parado**
   (p. ej. empieza a mitad de vuelta) sale un desfase falso: usar `PY video_vuelta/src/sincronia_giro.py <video> <log> --desde 40 --hasta 200 --manifiesto <manifiesto.json>` (correlación del giro; fiable
   con correlación > 0,9). Comprobar a ojo con `sincronia.py --fotograma <s_m>`: el cartel de la curva o la línea de meta en el fotograma de esa distancia.
4. **Cámara:** `PY video_vuelta/src/calibrar_camara.py <manifiesto> --escribir` (altura, cabeceo y distancia al punto del log con la línea de meta; rms < 1 px).
5. **Línea blanca y límite:** `PY video_vuelta/src/bordes_video.py <manifiesto> --cada 6 --fila-min 440 --z-max 22` → `linea_blanca.json` y `mapa_bordes_video.json` (límite = línea blanca + `SESGO_CAMARA_M` ∓ `LIMITE_FUERA_M`).
   Esas dos constantes y `ANCHO_PLAUSIBLE_M` (7-14,5 m) son de Sugo con el Formula R: **verificar en el paso 2 y ajustar**.

## 2. Vueltas manuales con zigzag (verificar y corregir lo que el vídeo no ve)

Una por lado, a 30 km/h, **solo log** (sin vídeo, salvo que quieras revisar fotogramas: entonces grabar). El programa lleva gas y freno; el usuario solo gira y cruza la línea hacia la hierba cada ≈ 3,6 s (30 m):

```text
PY circuito_virtual\src\sesion_manual.py --lado izq --laps 1 --velocidad-auto 30
PY circuito_virtual\src\sesion_manual.py --lado dcha --laps 1 --velocidad-auto 30
```

- El usuario **no toca los pedales del volante** (sale un aviso si pisa el gas). Probar antes 20 s en recta: debe llegar a 30 km/h y quedarse.  Si el juego no recibe el gas, desactivar Steam Input para PCARS2 (ver `PCARS2-AI/src/controller.py`).
- Cruzar hacia **hierba o grava**, no hacia un piano (pasar a un piano no da cruce: es superficie legal).
- El log queda en `PCARS2-AI/logs/manual/`. Si el vídeo también se graba, es la misma sincronía del paso 1.3.

**Verificar D6:** `PY video_vuelta/src/verificar_limite.py <log> --lado izq|dcha`: error mediano ≈ 0 (± 0,15 m) = las constantes valen de media. En Sugo salieron +0,11 y −0,06 m, pero con un 35-40 % de cruces a más de 0,3 m:
el mapa del vídeo falla justo donde hay piano, pasillos de asfalto fuera de la línea y curvas.

## 3. Revisar los tramos dudosos con el usuario (la parte que no se automatiza)

```text
PY video_vuelta\src\tramos_dudosos.py <log> --lado izq --desfase <s> --video <video.mp4> --fotogramas <carpeta>
```

Da la lista de tramos con cruces a más de 0,5 m del límite, con su curva, su instante en el vídeo y la **secuencia de terrenos** de las dos ruedas, y un fotograma por tramo. Se enseñan **uno por uno**
al usuario (nunca varios a la vez) y se anota qué es cada cosa y si el coche puede usarla. Ids de terreno que han salido en Sugo: 0 asfalto, 7 hierba, 10 piano rugoso, 46 asfalto fuera de la línea
(`RUNOFF_ROAD`, ilegal), 47 franja ilegal, 48 pintura plana de los pianos (no está en `pcars2_surface.py`; se toma como legal), 49 pintura ilegal. **En otra pista el id de la pintura plana puede ser otro:**
mirar las secuencias y los fotogramas.

Las reglas acordadas en Sugo (D11) son el punto de partida, no una verdad para otra pista:
1. Límite = línea blanca continua; el asfalto fuera de ella no cuenta.
2. Piano = su borde exterior (se usa en la salida de la curva con el volante casi recto); en los de dos partes (plana + rugosa) solo la plana; si el log no las distingue, el piano entero.
3. Lo de detrás del piano (parches de asfalto, moqueta verde, isletas) no cuenta; tampoco el asfalto que se vuelve a pisar tras salir (entrada a boxes).
4. Donde no hay línea ni piano, el borde del asfalto que enlaza con la línea de antes y de después.

Las excepciones de cada pista van en `circuito_virtual/pistas/<pista>/reglas_limite.json`: `sin_48` (tramos donde el 48 no es piano) y `linea_manda` (tramos donde el límite es la línea aunque detrás haya asfalto
pisable que el juego no marca como fuera).

## 4. Mapa de bordes corregido y pasillo

```text
PY video_vuelta\src\mapa_corregido.py <log izq> <log dcha> [más logs] [--video <mapa_bordes_video.json>] [--reglas <reglas_limite.json>]
PY video_vuelta\src\pasillo_a_observaciones.py <mapa_bordes_corregido.json> --salida circuito_virtual\pistas\<pista>\observaciones_pasillo_d11.json [--prudente 0.3]
```

- `mapa_corregido.py` imprime la **validación cruzada**: error mediano y p90 del vídeo solo frente al corregido sobre metros con horquilla. Si no mejora, hay un error en las reglas o en la sincronía.
  Un contacto ilegal a menos de 0,3 m «hacia fuera» se ignora (el coche en la hierba del otro lado).
- `pasillo_a_observaciones.py` escribe un archivo **nuevo**; no toca `observaciones_logs.json` (versionado: **preguntar** antes de sustituirlo).
- Con 4 logs (dos por lado) la verificación es independiente: `verificar_limite.py --bordes <mapa_bordes_corregido.json> <log que no se usó>`.

## 5. Estudio de trazada, línea y sesión

1. **Estudio sin juego** (carpeta temporal, `pistas/` sin tocar): `linea_optima.py` con los parámetros de la línea vigente y `--margen 0.6`, para el control (observaciones de siempre), el pasillo corregido y el
   corregido con `--prudente 0.3`. En Sugo (V103): control 118,447 s, corregido 117,773 s (−0,67 s), prudente 118,370 s (−0,08 s), margen 1,0 +0,15 s: **manda el margen y lo no verificado**.
2. **Línea nueva** (los archivos `*_optima_*.json` no se versionan; los `_n.npy` sí):

```text
PY circuito_virtual\src\linea_optima.py --coche-a1-mu 9 --tope-kmh 125 --max-barridos 80 --pasillo-estricto --salto-max-rel 1.0 --margen 0.6 --curvatura-local-rel 1.2 --observaciones observaciones_pasillo_d11.json --nombre sugo_optima_a1mu9c12d11
```

3. **Sesión de una variable** (solo cambia `--reference`), con el usuario atento y Ctrl+C a mano: comando en «Comandos vigentes» de `circuito_virtual/docs/PENDIENTE.md` (Sesión D). Qué mirar: ticks con rueda fuera (terreno 7) por tramo, el
   tiempo frente al control del día, y la holgura de la rueda. **Los mapas de agarre, gas y frenada se aprendieron con la línea anterior**: si la línea cambia mucho, reaprenderlos.
4. Si en la sesión salen metros con ruedas fuera que no esperabas: vuelta extra de zigzag por lado (paso 2) con el mapa corregido como `--bordes` y rehacer el paso 4 con los cuatro logs.

## Qué es de Sugo / Formula R y qué no

| Elemento | Dónde | Depende de |
| --- | --- | --- |
| 70° horizontales, altura 1,009 m, cabeceo 5,88°, 2,88 m tras el punto del log | `camara.py`, `calibrar_camara.py` | coche y cámara del juego: recalibrar siempre (cambia con el campo de visión) |
| `SESGO_CAMARA_M` 0,06 y `LIMITE_FUERA_M` 0,18 | `bordes_video.py` | coche (semivía supuesta 0,85 m) y juego: verificar con el paso 2 |
| `ANCHO_PLAUSIBLE_M` (7-14,5 m) | `bordes_video.py` | la pista: quitar pit lane y líneas vistas dos veces |
| `reglas_limite.json` | `circuito_virtual/pistas/<pista>/` | la pista (una por circuito) |
| Id 48 = pintura plana legal; 46 = asfalto fuera de la línea; 10 = rugoso | `mapa_corregido.py` | el juego; en otra pista puede haber otros ids |
| Detector de color de la línea blanca (ancho 4-35 cm) | `lineas.py` | pista con línea blanca y buen contraste; sin ella, la red (`segmentador.py`, no probada fuera de Sugo) |
| Perfil gráfico de referencia | `perfiles/graficos.json` | el equipo del usuario y sus ajustes |

## Trampas que ya han salido

- El juego **ignora `adapter`** y reescribe `graphicsconfigdx11.xml` al cerrarse; la captura debe medir exactamente 1920×1080.
- `sincronia.py` por el arranque da un desfase falso si el log empieza a mitad de vuelta (−10,18 s frente a +8,55 s reales): usar `sincronia_giro.py` y comprobar con un fotograma.
- Terreno 10 y 25 (pianos) están en `RACING_TERRAIN_IDS`: son legales; «fuera» es hierba, grava y los ids de ilegal (46, 47, 49). El 48 no está en esa lista pero se trata como legal.
- El rumbo del log es `orientation[1] − π` (con `− π/2` las líneas salían giradas 90°).
- Vídeos de otras fuentes (YouTube) no sirven para calibrar ni validar: sin el log no hay posición, rumbo ni velocidad.
- Una sola sesión en seco y nublado no cubre mojado ni otra hora del día: etiquetar cada pasillo con sus condiciones.
