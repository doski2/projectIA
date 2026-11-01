# Plan de circuito_virtual: mapa virtual de la pista y línea óptima (antes Plan D)

Contexto: H56 (el seguimiento de la línea limita a 90 km/h), H59 (el eje delantero satura a ≈ 88
km/h), H61 (la referencia grabada lleva micro-quiebros) y
las observaciones del usuario del 2026-11-01. Depende de: A1 (modelo del coche) y del solver de A2
(`perfil_velocidad.py`).
Estado: **aprobado como carpeta propia (D25, 2026-11-01); diseño D0-D5 pendiente de visto bueno del
usuario**. Código existente: `src/perfil_velocidad.py` y `src/linea_suave.py`.

## Por qué

Hoy el teacher sigue **una línea fija** grabada a 60 km/h, con mando y limitador de pit: lleva
micro-correcciones que a 125 km/h se vuelven oscilación,
y el BC aprende a imitar ese seguimiento estricto. No hay concepto de «dónde puedo estar»: ni para
buscar la vuelta rápida, ni para adelantar o defender.
Decisión del usuario (2026-11-01): el plan ideal para los problemas actuales es **optimizar la
línea**y que el comportamiento aprendido sea una**selección** del agente dentro de la pista,
no un seguimiento estricto.

## La idea en cuatro piezas

1. **Mapa** (geometría + pasillo): para cada metro de vuelta `s`, el eje (x, y, z, rumbo, κ,

   pendiente) y los bordes del asfalto `n_izq(s)`, `n_dcha(s)` (en metros
   respecto al eje) con el tipo de superficie del borde (bordillo, césped, franja ilegal).

2. **Planificador** (decide *dónde*): da la posición lateral `n(s)` y la velocidad objetivo. Primero

   es un optimizador sin juego; después, una política aprendida.

3. **Seguidor** (ejecuta): el teacher que ya tenemos (volante con anticipación por curvatura, X23, y

   PI de velocidad), que sigue cualquier trayectoria suave.

4. **Modelo del coche**: el solver de A2 (aceleración, frenada, límite lateral `μ + k·v²`), que hace

   de simulador rápido.

## Pasos

| #   | Paso                                                                                                                                                                                                                                          | Éxito si…                                                                                  | Estado                                                                                     |     |                                            |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ | --- | ------------------------------------------ |
| D0  | Sistema de coordenadas (s, n) sobre el eje de la pista, a partir de la referencia suavizada; formato del mapa en `circuito_virtual/pistas/sugo_gp/mapa.json` (versionado)                                                                     | Ida y vuelta (x, z) ↔ (s, n) con error < 5 cm                                              | **Hecho (2026-11-01):** `src/mapa.py`; ida y vuelta con error de s ≤ 0,3 cm y de n ≈ 0 con | n   | ≤ 6 m; `pistas/sugo_gp/mapa.json` (164 KB) |
| D1  | **Mapeo de bordes:** sesión lenta (30 km/h) en la que el teacher recorre desplazamientos laterales crecientes por vueltas hasta que una rueda toca césped o franja ilegal; se anota `n` del borde por metro y lado                            | Bordes de las 3567 m con una incertidumbre ≤ 0,25 m                                        | **D1a hecho** (logs, V9, V10: borde izq. 15,4 %, dcha. 6,8 %); D1b diseño en la sección siguiente, pendiente de visto bueno     |     |                                            |
| D2  | **Línea óptima sin juego:** con el mapa y el solver, minimizar el tiempo de vuelta variando `n(s)` dentro del pasillo, con margen a los bordes y penalización de curvatura                                                                    | Tiempo predicho menor que el de la línea suavizada; curvatura continua                     | Pendiente                                                                                  |     |                                            |
| D3  | Convertir la línea óptima en un `ReferenceLine` (mismo formato JSON) y rodarla con el teacher a velocidades crecientes                                                                                                                        | Vuelta limpia a ritmo > actual; tiempo medido dentro del 3 % del predicho (criterio de A2) | Pendiente                                                                                  |     |                                            |
| D4  | **Exploración en bucle cerrado:** margen a los bordes menor por escalones, μ y k reajustados con cada vuelta real                                                                                                                             | La línea mejora o se queda; ninguna salida de pista                                        | Pendiente                                                                                  |     |                                            |
| D5  | **Selección aprendida:** el planificador pasa a ser una política (PPO u otra) entrenada en el simulador (solver + mapa), con estado (`n`, `v`, márgenes, κ por delante) y acción (`Δn`, velocidad); rivales como obstáculos móviles en (s, n) | Iguala o mejora la línea óptima de D2; adelanta sin salirse del pasillo                    | Pendiente                                                                                  |     |                                            |

## Notas de diseño

- **Datos que ya hay:** el terreno de cada rueda (asfalto, bordillo, césped, grava, franja ilegal),

  la posición exacta y el CTE firmado. Los logs de A1 tocan el borde en
solo 3 sitios (bordillo y césped a la izquierda hacia 1350-1450 m con CTE −1,16 a +0,23 m; terreno
48 a la derecha hacia 800 m con CTE +0,57 a +0,87 m): **el mapa no sale gratis, hace falta D1**.

- **Seguridad de D1:** a 30 km/h un toque a la hierba no hace daño; la guardia de superficie del

  teacher ya trata una rueda en césped como `edge_surface` y frena con tres. Los muros
(terreno 12-14) **no se exploran**: el borde se da por encontrado al tocar césped, grava o franja
ilegal, nunca al llegar a un muro. Siempre `--stop-on-damage`.

- **Qué es el borde:** la rueda exterior toca el límite; el pasillo para el centro del coche es el

  borde menos la mitad del ancho del coche y un margen. El ancho del coche se mide del propio D1
  (diferencia de CTE entre contacto izquierdo y derecho en una recta).

- **Superficies de carrera:** el bordillo cuenta como superficie de carrera para el juego

  (`RACING_TERRAIN_IDS`), pero las franjas ilegales (47, 49) llevan penalización: son límite duro.

- **El seguidor:** si el teacher no sigue bien una línea optimizada, se arregla el seguidor (volante

  con anticipación, X23), no la línea.

- **El simulador de D5:** el solver de A2 no simula la dinámica (volante, deslizamiento), solo el

  perfil de velocidad; antes de entrenar una política hay que decidir si basta con eso o se pasa a B
  (simulador aprendido).

- **Adelantar y defender:** necesita la posición de los rivales. El paquete de tiempos de PCARS2

  debería traerla, pero hoy solo se lee al participante propio (`TimingsFrame`): hay que comprobarlo
  con una sesión con rivales antes de D5.

- **Observaciones de `universal_v2`:** los márgenes a cada borde y la κ por delante entran como

  observaciones; el CTE a una línea fija deja de ser el objetivo y pasa a ser el error de
  seguimiento.

## Riesgos

1. El mapa depende de la pista y de la superficie: otra pista, otro D1 (A3). La lluvia no mueve los

   bordes, pero sí el agarre.

2. Una línea óptima puede pedir más agarre del que el coche tiene en las curvas: se evita subiendo μ

   y k solo con datos reales y con márgenes por escalones.

3. El BC actual aprendió a seguir una línea; con una selección propia hará falta reentrenar (v2), no

   ajustar.

4. D1 puede encontrar bordes irregulares (bordillos altos, zonas de salida de pit): se anotan, no se

   promedian.

## Orden con el resto del trabajo

1. Validar G1b (línea suavizada, `--reference`) y cerrar A2.0 con la línea suavizada: el solver de

   A2 sirve para cualquier línea, así que no se pierde nada.

2. D0 y D1 (mapa), D2 (óptimo sin juego), D3 (rodarlo): cierran A2 con una línea mejor.
3. D4, y A1.3b (arcos en 3ª) para fijar `k`.
4. D5 y el PPO (C4) con el mapa, el modelo y un BC v2.

## D1b: mapeo de bordes con sesiones (diseño propuesto, pendiente de visto bueno del usuario, 2026-11-01)

D1a (V9) dejó el asfalto comprobado en toda la vuelta pero los bordes medidos en < 2 %. D1b los mide
con el teacher a 30 km/h, sin tocar `PCARS2-AI`.

- **Lanzador:** `src/sesion_mapeo.py` **no arranca el juego**: lee las observaciones y el mapa,

  escribe las referencias desplazadas en `pistas/sugo_gp/desplazadas/` (no versionadas) y **imprime
  los comandos de `aislado.py`** (`--teacher-only --speed-band 30 --reference <archivo> --experiment
  mapa_<lado>_<k>`). El usuario los lanza. Así se respeta la regla de dependencias
  (`circuito_virtual` no importa de `experimental`) y el aislamiento de modelo, buffer y progreso de
  `aislado.py`.

- **Qué línea se rueda:** una por lado y ronda. Para el lado izquierdo, la posición objetivo de la

  rueda es la cota «asfalto hasta» ya comprobada menos 0,4 m, suavizada (mínimo móvil de ±15 m y
  gaussiana de σ = 10 m) para que el teacher la pueda seguir; el centro del coche va a esa posición
  más la semivía. Igual a la derecha. Cada ronda empuja el límite comprobado 0,4 m más allá; cuando
  aparece la cota «ya fuera», el borde queda acotado.

- **Rondas:** una vuelta lanzada por lado y ronda (≈ 7 min a 30 km/h), con el extractor

  (`bordes_logs.py escanear`) entre una ronda y la siguiente para recalcular el objetivo. Se para en
  cada tramo al llegar a |n| = 6 m o al medir el borde. Estimación: 6-10 rondas por lado.

- **Seguridad:** a 30 km/h un toque a la hierba no hace daño; `--stop-on-damage` cierra la sesión

  ante un golpe; los muros no se buscan (el avance es de 0,4 m por ronda y solo hacia donde no se ha
  medido); el usuario delante del juego y en seco, con Ctrl+C si el coche no recupera la línea.
  **Riesgo conocido:** si el borde está pegado a un muro (en 1350-1450 m la línea ya pasa a ≈ 1 m
  del borde izquierdo), los 0,4 m de avance podrían acercar el coche a él; en esos tramos el avance
  baja a 0,2 m.

- **Guardia de superficie:** el teacher trata una o dos ruedas en hierba como `edge_surface` (sigue)

  y frena con tres (`off_surface`): antes de la primera ronda hay que comprobar qué perfil de
  seguridad usa `aislado.py` (`--safety-profile`) y que la recuperación va hacia la línea
  desplazada, no hacia la original.

- **Calibración de la semivía:** con una ronda en recta donde el coche sale por los dos lados, la

  diferencia entre las cotas «fuera» izquierda y derecha menos la anchura medida del asfalto da la
  vía; hasta entonces 0,85 m.

- **Éxito:** los dos bordes medidos en ≥ 90 % de la vuelta con una incertidumbre ≤ 0,3 m.

## A2 con las vueltas de la IA a ritmo real (propuesto, 2026-11-01)

Con `pistas/sugo_gp/ia_ritmo_real.json` (V11) se puede cerrar lo que A2 no podía: **predecir el tiempo de una vuelta a ritmo real** (97,7 s) y el perfil de velocidad (criterio: error < 3 % y perfil correlado). Pasos: (1) extender `a_acel(v)` hasta 184 km/h con la envolvente de la aceleración longitudinal de las 14 vueltas (el gas de la IA no sirve para saber cuándo iba a fondo, así que se toma el percentil alto por tramo de velocidad y marcha, con la pendiente corregida); (2) el límite lateral `μ + k·v²` con la envolvente de `a_lat` frente a v² de la IA (a 120-150 km/h llega a 11,9 m/s²: ajusta `k` si resulta positiva, y `μ` queda en la cota de D21 mientras no haya datos por encima); (3) la frenada con la envolvente del freno de la IA (0-172) y la deceleración medida; (4) predecir la vuelta con `solve()` sobre la línea de la propia IA (mediana de las 14 vueltas) y comparar con 97,7 s y con el perfil v(s), separando algunas vueltas para validar. Todo sin juego.
