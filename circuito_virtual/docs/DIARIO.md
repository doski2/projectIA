# Diario de circuito_virtual

Lo más reciente arriba. Historia anterior en `experimental/docs/DIARIO.md`.

- **2026-11-01 — D0 hecho (V7).** `src/mapa.py`: eje a 1 punto por metro desde la referencia suavizada, `sn_a_xz` / `xz_a_sn` (ida y vuelta con error de s ≤ 0,3 cm y de n ≈ 0 con |n| ≤ 6 m), curvatura, pendiente, bordes en NaN (D1) y guardado/carga. n positivo a la derecha y κ positiva a la izquierda, iguales que en producción (comprobado con `signed_lateral_error` y `ReferenceLine.curvature`). `pistas/sugo_gp/mapa.json` de 164 KB. 26 tests en `circuito_virtual` (9 nuevos).

- **2026-11-01 — Nace la carpeta (V1-V6).** El usuario decide un mapa virtual de la pista y una línea óptima que sirva para cualquier circuito, con los márgenes y la línea ideal en un gráfico, y que el comportamiento aprendido
  sea una selección del agente dentro del pasillo. Se mueven aquí el solver de perfil de velocidad, el suavizado de la referencia, sus tests y el plan. Los logs de sesión se quedan en `PCARS2-AI/logs/`. Suites: 17 aquí, 61 en `experimental`, 471 en `PCARS2-AI`.
