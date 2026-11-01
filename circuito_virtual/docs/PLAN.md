# Plan de circuito_virtual: mapa virtual de la pista y línea óptima (antes Plan D)

Contexto: H56 (el seguimiento de la línea limita a 90 km/h), H59 (el eje delantero satura a ≈ 88 km/h), H61 (la referencia grabada lleva micro-quiebros) y
las observaciones del usuario del 2026-11-01. Depende de: A1 (modelo del coche) y del solver de A2 (`perfil_velocidad.py`).
Estado: **aprobado como carpeta propia (D25, 2026-11-01); diseño D0-D5 pendiente de visto bueno del usuario**. Código existente: `src/perfil_velocidad.py` y `src/linea_suave.py`.

## Por qué

Hoy el teacher sigue **una línea fija** grabada a 60 km/h, con mando y limitador de pit: lleva micro-correcciones que a 125 km/h se vuelven oscilación,
y el BC aprende a imitar ese seguimiento estricto. No hay concepto de «dónde puedo estar»: ni para buscar la vuelta rápida, ni para adelantar o defender.
Decisión del usuario (2026-11-01): el plan ideal para los problemas actuales es **optimizar la línea** y que el comportamiento aprendido sea una **selección** del agente dentro de la pista,
no un seguimiento estricto.

## La idea en cuatro piezas

1. **Mapa** (geometría + pasillo): para cada metro de vuelta `s`, el eje (x, y, z, rumbo, κ, pendiente) y los bordes del asfalto `n_izq(s)`, `n_dcha(s)` (en metros
   respecto al eje) con el tipo de superficie del borde (bordillo, césped, franja ilegal).
2. **Planificador** (decide *dónde*): da la posición lateral `n(s)` y la velocidad objetivo. Primero es un optimizador sin juego; después, una política aprendida.
3. **Seguidor** (ejecuta): el teacher que ya tenemos (volante con anticipación por curvatura, X23, y PI de velocidad), que sigue cualquier trayectoria suave.
4. **Modelo del coche**: el solver de A2 (aceleración, frenada, límite lateral `μ + k·v²`), que hace de simulador rápido.

## Pasos

| # | Paso | Éxito si… | Estado |
| --- | --- | --- | --- |
| D0 | Sistema de coordenadas (s, n) sobre el eje de la pista, a partir de la referencia suavizada; formato del mapa en `circuito_virtual/pistas/sugo_gp/mapa.json` (versionado) | Ida y vuelta (x, z) ↔ (s, n) con error < 5 cm | Pendiente |
| D1 | **Mapeo de bordes:** sesión lenta (30 km/h) en la que el teacher recorre desplazamientos laterales crecientes por vueltas hasta que una rueda toca césped o franja ilegal; se anota `n` del borde por metro y lado | Bordes de las 3567 m con una incertidumbre ≤ 0,25 m | Pendiente |
| D2 | **Línea óptima sin juego:** con el mapa y el solver, minimizar el tiempo de vuelta variando `n(s)` dentro del pasillo, con margen a los bordes y penalización de curvatura | Tiempo predicho menor que el de la línea suavizada; curvatura continua | Pendiente |
| D3 | Convertir la línea óptima en un `ReferenceLine` (mismo formato JSON) y rodarla con el teacher a velocidades crecientes | Vuelta limpia a ritmo > actual; tiempo medido dentro del 3 % del predicho (criterio de A2) | Pendiente |
| D4 | **Exploración en bucle cerrado:** margen a los bordes menor por escalones, μ y k reajustados con cada vuelta real | La línea mejora o se queda; ninguna salida de pista | Pendiente |
| D5 | **Selección aprendida:** el planificador pasa a ser una política (PPO u otra) entrenada en el simulador (solver + mapa), con estado (`n`, `v`, márgenes, κ por delante) y acción (`Δn`, velocidad); rivales como obstáculos móviles en (s, n) | Iguala o mejora la línea óptima de D2; adelanta sin salirse del pasillo | Pendiente |

## Notas de diseño

- **Datos que ya hay:** el terreno de cada rueda (asfalto, bordillo, césped, grava, franja ilegal), la posición exacta y el CTE firmado. Los logs de A1 tocan el borde en
  solo 3 sitios (bordillo y césped a la izquierda hacia 1350-1450 m con CTE −1,16 a +0,23 m; terreno 48 a la derecha hacia 800 m con CTE +0,57 a +0,87 m): **el mapa no sale gratis, hace falta D1**.
- **Seguridad de D1:** a 30 km/h un toque a la hierba no hace daño; la guardia de superficie del teacher ya trata una rueda en césped como `edge_surface` y frena con tres. Los muros
  (terreno 12-14) **no se exploran**: el borde se da por encontrado al tocar césped, grava o franja ilegal, nunca al llegar a un muro. Siempre `--stop-on-damage`.
- **Qué es el borde:** la rueda exterior toca el límite; el pasillo para el centro del coche es el borde menos la mitad del ancho del coche y un margen. El ancho del coche se mide del propio D1 (diferencia de CTE entre contacto izquierdo y derecho en una recta).
- **Superficies de carrera:** el bordillo cuenta como superficie de carrera para el juego (`RACING_TERRAIN_IDS`), pero las franjas ilegales (47, 49) llevan penalización: son límite duro.
- **El seguidor:** si el teacher no sigue bien una línea optimizada, se arregla el seguidor (volante con anticipación, X23), no la línea.
- **El simulador de D5:** el solver de A2 no simula la dinámica (volante, deslizamiento), solo el perfil de velocidad; antes de entrenar una política hay que decidir si basta con eso o se pasa a B (simulador aprendido).
- **Adelantar y defender:** necesita la posición de los rivales. El paquete de tiempos de PCARS2 debería traerla, pero hoy solo se lee al participante propio (`TimingsFrame`): hay que comprobarlo con una sesión con rivales antes de D5.
- **Observaciones de `universal_v2`:** los márgenes a cada borde y la κ por delante entran como observaciones; el CTE a una línea fija deja de ser el objetivo y pasa a ser el error de seguimiento.

## Riesgos

1. El mapa depende de la pista y de la superficie: otra pista, otro D1 (A3). La lluvia no mueve los bordes, pero sí el agarre.
2. Una línea óptima puede pedir más agarre del que el coche tiene en las curvas: se evita subiendo μ y k solo con datos reales y con márgenes por escalones.
3. El BC actual aprendió a seguir una línea; con una selección propia hará falta reentrenar (v2), no ajustar.
4. D1 puede encontrar bordes irregulares (bordillos altos, zonas de salida de pit): se anotan, no se promedian.

## Orden con el resto del trabajo

1. Validar G1b (línea suavizada, `--reference`) y cerrar A2.0 con la línea suavizada: el solver de A2 sirve para cualquier línea, así que no se pierde nada.
2. D0 y D1 (mapa), D2 (óptimo sin juego), D3 (rodarlo): cierran A2 con una línea mejor.
3. D4, y A1.3b (arcos en 3ª) para fijar `k`.
4. D5 y el PPO (C4) con el mapa, el modelo y un BC v2.
