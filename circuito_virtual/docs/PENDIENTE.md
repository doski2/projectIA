# Pendiente de circuito_virtual

Orden de trabajo y estado al cierre de la sesión del **2026-11-01**. Lo que no es del circuito
(rampa del BC, PPO, daño de motor P26, controles de seco, reentreno v2) sigue en
`experimental/docs/PENDIENTE.md`. Las decisiones están en `docs/DECISIONES.md` (V1-V14), el plan
en `docs/PLAN.md` y la historia en `docs/DIARIO.md`.

## Dónde estamos (para retomar sin releer nada)

- **Último commit:** `04208ac` (docs). D2 (V15) está hecho pero **sin commit** al cierre de esta sesión: `src/linea_optima.py`, `src/informe_linea_optima.py`, `tests/test_linea_optima.py`, los tres `_n.npy`, cambios en `perfil_velocidad.py` (solver 5 veces más rápido, `kappa_half_m`) y en `.gitignore`.
- **Tests en verde:** `circuito_virtual` 51, `experimental` 61, `PCARS2-AI` 471. Se lanzan con
  `pytest` dentro de cada carpeta.
- **Sin commit y no son míos:** 6 archivos de `experimental/` (`README.md`, `docs/DECISIONES.md`,
  `DIARIO.md`, `ESTUDIO_SIMULADOR_Y_LIMITES.md`, `PENDIENTE.md`, `PLAN_A_LIMITES_COCHE.md`)
  reformateados por el usuario con markdownlint. Los commitea él. No tocarlos ni mezclarlos en mis
  commits.
- **Qué está probado:**
  - Mapa (s, n) de Sugo: `pistas/sugo_gp/mapa.json` (D0, V7).
  - Asfalto comprobado en toda la vuelta (mediana 5,24 m entre ruedas), bordes medidos solo en el
    15,4 % (izquierdo) y el 6,8 % (derecho) de la vuelta (D1a, V9-V10).
  - Solver de perfil de velocidad calibrado con la IA a ritmo real: 97,90 s previstos frente a
    98,06 s reales (−0,2 %) con un factor de ritmo f = 0,697 (A2, V13).
  - Línea suavizada `pistas/sugo_gp/sugo_smooth.json` válida en el juego: 3ª hasta 134,9 km/h
    sin cortes, CTE ≤ 0,2 m y volante ±0,025 en la recta 1 (G1b, V14).
- **Línea óptima (D2, V15):** prevista, no probada en el juego.
- **Qué NO está probado:** nada por encima de 135 km/h ni en 4ª; ninguna vuelta completa del agente
  a más de 60 km/h sobre la línea suavizada; ningún borde de pista medido a propósito (D1b); una
  sola pista y una sola IA.

## Reglas de la sesión (no olvidar)

- **El usuario lanza el juego, yo nunca.** No ejecutar `aislado.py` ni `learn_driver.py` con
  argumentos válidos, ni para «probar» la CLI: lanza una sesión real y borra el buffer del
  experimento (incidente c0_log, memoria `feedback-no-ejecutar-aislado-para-probar`).
- Antes de cada sesión arriesgada (techo alto, arcos, mapeo de bordes) confirmar que el usuario
  está delante del juego y en seco.
- Dependencias en un solo sentido: `PCARS2-AI` ← `circuito_virtual` ← `experimental`.
  `circuito_virtual` no importa de `experimental`.
- Documentos de `circuito_virtual/` y `experimental/` en **LF**. Para escribir archivos largos usar
  Write, no scripts de Python con rutas Windows en cadenas normales (usar `r"..."`).
- El usuario reformatea los docs con markdownlint: no comprobar texto con búsquedas literales
  frágiles (usar regex tolerante a espacios).
- Camino sólido a largo plazo, sin prisa. Si hay que elegir, recomendar y no listar todo.
- Comando de Python del usuario:
  `C:\Users\doski\projectIA\.venv\Scripts\python.exe` y **rutas absolutas** (su terminal puede
  estar en `circuito_virtual`, no en la raíz).

## Orden de trabajo propuesto

### 1. D2 hecho (V15): queda probar la línea en el juego

Las tres líneas están en `pistas/sugo_gp/sugo_optima_f{697,850,1000}.json` (regenerables con
`src/linea_optima.py`; el informe, con `src/informe_linea_optima.py`). La de f = 0,697 prevé −3,5 %
(98,96 → 95,46 s) con el mismo modelo; con |κ| casi sin suavizar, −2 %. Es la cifra prudente.

- **No probada en el juego.** La línea se separa hasta 1,3 m de la suavizada, también en la recta 1
  (validada a 135 km/h en V14). Primer uso: A2.0 (punto 4) con la de f = 0,697 y `--reference` a
  esa línea, a poca velocidad, para ver que el teacher la sigue (CTE, volante, rumbo).
- **Ampliar el pasillo vale más que afinar el optimizador:** con ±3 m hipotéticos sale −6,5 %. D1b
  (punto 3) es lo que lo mide.
- **Más puntos de control:** `--paso-nudos 15` da −5,3 % frente a −3,5 % con 20 m (κ ±7 m), pero es
  una línea con más movimiento lateral (hasta 0,12 m por metro) y más ajustada al modelo. Probar
  solo cuando la de 20 m esté rodada.
- **Óptimo local:** el descenso por coordenadas parte del eje. Si hiciera falta, probar otros
  puntos de partida o movimientos de varios puntos a la vez.

### 2. Sesión en el juego: subir el techo y frenadas (la lanza el usuario)

Objetivo: medir lo que D2 necesita y hoy se extrapola (aceleración en la parte alta y frenada).

- **Antes de lanzar:** revisar cómo se comporta `--max-gear 4` con el corte de encendido del
  cambio (H50: la UDP da `gear` 1 durante el corte; `auto_shift.py` ya lo filtra con
  `GEAR1_GLITCH_MIN_SPEED_MS` y `GEAR1_GLITCH_MIN_RPM_RATIO`). En G1b la 3ª llegó a 134,9 km/h
  con 6323 rpm y el par ya bajaba (127,6 → 119,8); la subida automática está en rpm/max_rpm > 0,87.
  `MAX_CAP_BY_MAX_GEAR` permite 150 km/h con 3ª y 170 con 4ª.
- **Comando del techo** (empezar con 3ª para ver dónde se acaba y después 4ª; ajustar el techo
  según lo que acabe el pase):

  ```text
  C:\Users\doski\projectIA\.venv\Scripts\python.exe
  C:\Users\doski\projectIA\experimental\common\aislado.py --ident acel --speed-band 60
  --ident-cap-kmh 150 --max-gear 3 --ident-straights 1
  --reference C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_smooth.json
  --experiment a1_acel_g3_150_60 --laps 3
  ```

  Éxito: llega a 150 km/h sin cortes por CTE (>2,5 m), rumbo (>0,30) ni fuera de asfalto; volante
  ±0,05; sin daño. Si el techo de la recta 1 (3132-3393 m, 260 m) se queda corto para frenar a
  tiempo, comprobar el margen final antes de subir (`--ident-end-margin-m`).
- **G3, frenadas en 3ª** desde 100, 110 y 115 km/h:
  `aislado.py --ident frenar --ident-caps 100,110,115 --max-gear 3 --ident-straights 1
  --reference <sugo_smooth.json> --experiment a1_frenar_g3_60 --laps 3`. Mide la distancia de
  frenada y la bajada de marcha; cruzar con los 12-15 m/s² de la IA.
- Tras cada sesión: analizar el informe (`experimental/logs/informe_<ts>_sugo_gp_l1_linea.html` y
  el log `PCARS2-AI/logs/learning/<ts>_sugo_gp_l1_linea.jsonl`) con
  `experimental/common/analisis_a1.py` y documentarlo (nueva decisión V15 en adelante).

### 3. D1b: mapeo de bordes con sesiones (necesita visto bueno del usuario)

Diseño completo en `docs/PLAN.md`, sección «D1b». Resumen: `src/sesion_mapeo.py` (sin escribir
todavía) no arranca el juego; escribe referencias desplazadas en `pistas/sugo_gp/desplazadas/` e
imprime los comandos de `aislado.py` (`--teacher-only --speed-band 30 --reference <archivo>
--experiment mapa_<lado>_<k>`), una ronda por lado y avance de 0,4 m (0,2 m cerca de muros).
**Antes de la primera ronda:** comprobar la guardia de superficie que `aislado.py` pasa a
`learn_driver.py` (no tiene opción propia; mirar `teacher_controller.py`): una o dos ruedas en hierba son `edge_surface` (sigue) y tres son
`off_surface` (frena y aborta); la recuperación debe ir hacia la línea desplazada, no hacia la
original. Calibrar de paso la semivía de 0,85 m. Éxito: los dos bordes medidos en ≥ 90 % de la
vuelta con incertidumbre ≤ 0,3 m.

### 4. A2.0: el agente rueda vueltas completas rápidas

Teacher en modo físico (límite lateral ≈ 12,5 m/s², techo 125 km/h, luego el que se mida en el
punto 2) sobre la línea suavizada y después sobre la de D2 (`sugo_optima_f697.json`), para comparar el tiempo previsto con el medido
(criterio < 3 %). Es la primera prueba del solver con el propio coche y no con la IA. Con la
línea óptima de D2 sirve también para ver si de verdad se gana tiempo.

### 5. A1.3b: arcos en 3ª y 4ª (riesgo de daño de motor, P26)

Para ver cuánto cambia el límite lateral con la marcha (D23: a 90 km/h en 4ª no es lo mismo que en
2ª o 3ª) y fijar `k`. Tres de tres sesiones de arcos dieron daño de motor hacia los 607 s; una de
aceleración llegó a 629 s sin daño. `aislado.py` ya pasa `--stop-on-damage`; usar sesiones cortas. Es la que menos
bloquea: dejarla para el final.

### 6. A3, segunda pista

Repetir A2 con otra pista y otra IA para saber si el factor de ritmo y las envolventes se
generalizan (hoy una pista y una IA). Requiere `circuito_virtual/pistas/<pista>/` con mapa y
referencia suavizada.

### 7. Comprobar los rivales

Ver si el paquete de tiempos del juego trae la posición de los rivales (hoy solo se lee al
participante propio), antes de D5 (adelantar y defender).

## Más adelante (tras D2, D3 y el mapa)

- **D3-D5:** planificador (dónde y a qué velocidad), política aprendida por selección y
  adelantar/defender, según el plan D de `docs/PLAN.md`.
- **PPO / C4:** después de mapa, modelo y BC v2, con noche protegida.
- **Reentreno v2 del BC y controles de seco:** en `experimental/docs/PENDIENTE.md`.
- **Informe del mapa:** añadir la línea óptima (D2) a `src/informe_mapa.py`.

## Hecho (no repetir)

- ~~G1b~~ **Hecho (V14):** 134,9 km/h en 3ª, 3 vueltas, sin cortes, sin daño.
- ~~A2 con la IA a ritmo real~~ **Hecho (V12, V13).**
- ~~D2~~ **Hecho (V15), sin juego:** línea óptima por ritmo, informe y 8 tests.
- ~~D0~~ **Hecho (V7):** coordenadas (s, n), `src/mapa.py`, `pistas/sugo_gp/mapa.json`; ida y vuelta
  con error < 0,3 cm.
- ~~D1a~~ **Hecho (V9, V10):** bordes de 106 logs, izquierdo 15,4 % y derecho 6,8 %.
- ~~Línea suavizada~~ **Hecho (H61 en `experimental/docs/DECISIONES.md`):** `src/linea_suave.py`, `pistas/sugo_gp/sugo_smooth.json`.
