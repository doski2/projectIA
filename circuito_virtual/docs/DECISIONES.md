# Decisiones de circuito_virtual

Numeración propia con prefijo **V**. La historia anterior (hallazgos H, excepciones X, decisiones D y preguntas P de A1-A2 y de la rampa del BC)
sigue en `experimental/docs/DECISIONES.md`; aquí solo se anota lo que se decide a partir del 2026-11-01. Las filas citan allí lo que las originó.

| # | Tema | Decisión | Estado |
| --- | --- | --- | --- |
| V1 | Carpeta | El mapa virtual de la pista y la línea óptima viven en `circuito_virtual/` (D25). Dependencia: `PCARS2-AI` ← `circuito_virtual` ← `experimental` | Decidido (2026-11-01) |
| V2 | Plan | El plan es `docs/PLAN.md` (D0-D5): mapa de bordes, línea óptima con el solver de A2, rodarla, exploración en bucle y selección aprendida (D24) | Diseño pendiente de visto bueno |
| V3 | Logs | Los logs de sesión siguen en `PCARS2-AI/logs/` (los escribe el código de producción y los leen muchas herramientas). Aquí se guardan las **salidas por pista**: mapa, línea, gráficos, informes de mapeo | Decidido (2026-11-01) |
| V4 | Documentos | Desde el 2026-11-01 el trabajo de mapa, línea y modelo del coche se anota en estos tres documentos (`DECISIONES.md`, `DIARIO.md`, `PENDIENTE.md`). `experimental/docs/` conserva la historia y lo que no es del circuito (rampa del BC, PPO, daño de motor) | Decidido (2026-11-01) |
| V5 | Archivos derivados | Se versionan el mapa y los parámetros del coche (pequeños); la referencia suavizada (4,5 MB) se regenera con `src/linea_suave.py` | Decidido (2026-11-01) |
| V6 | Sesiones en el juego | Las de identificación del coche (A1) se lanzan con `experimental/common/aislado.py`; las de mapeo de bordes (D1) tendrán su lanzador aquí, en `src/`, que llama a `learn_driver.py` de producción sin cambiarlo | Pendiente (D1) |
