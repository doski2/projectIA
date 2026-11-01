# circuito_virtual/

Mapa virtual de cada pista y su línea óptima: el eje, los bordes del asfalto, la línea suavizada, la línea que minimiza el tiempo de vuelta y su gráfico.
Nace de las conclusiones de A1-A2 (`experimental/docs/DECISIONES.md`, H56, H59, H61, D24, D25) y sirve para cualquier circuito.

## Reglas

1. **Dependencia en un solo sentido:** `PCARS2-AI` ← `circuito_virtual` ← `experimental`.
   `circuito_virtual/` solo importa de `PCARS2-AI/src` (la línea de referencia, los terrenos, el CTE firmado, el teacher como seguidor).
   `experimental/` puede importar de aquí. `PCARS2-AI/` no importa nada de aquí hasta que algo se promueva, con tests y anotado.
2. **Un mapa por pista y un modelo por coche.** `pistas/<pista>/` lleva el eje, los bordes, la línea suavizada, la línea óptima y los gráficos.
   `coches/<coche>/` lleva los parámetros que se miden en A1 (aceleración, frenada, límite lateral `μ + k·v²`).
3. **Los datos pequeños y de resultado se versionan** (mapa, parámetros del coche); los archivos grandes derivados (`sugo_smooth.json`, 4,5 MB, copia de la
   referencia) se regeneran con el script y no se versionan.
4. **Logs y sesiones:** los logs de sesión se quedan en `PCARS2-AI/logs/` (los escribe producción). Las sesiones de identificación del coche (A1) se lanzan con `experimental/common/aislado.py`; el lanzador del mapeo de bordes (D1), con copias desplazadas de la línea y `--reference`, irá en `src/` (V6). Aquí se guardan las salidas por pista.
5. **Tests propios** en `circuito_virtual/tests/`, fuera de las suites de `PCARS2-AI` y `experimental`.

## Estructura

| Carpeta | Contenido |
| --- | --- |
| `docs/PLAN.md` | Plan D0-D5: coordenadas (s, n), mapeo de bordes, línea óptima, exploración y selección aprendida |
| `docs/DECISIONES.md`, `DIARIO.md`, `PENDIENTE.md` | Decisiones (V1...), diario y orden de trabajo de esta carpeta; la historia anterior está en `experimental/docs/` |
| `src/perfil_velocidad.py` | Modelo del coche y de la pista: solver de perfil de velocidad de adelante y atrás (A2) |
| `src/linea_suave.py` | Suavizado de la referencia en las rectas (H61) |
| `src/bordes_logs.py` | D1a: cotas de borde por metro a partir de los logs ya grabados (terreno de las ruedas y posición) |
| `src/informe_mapa.py` | Informe HTML del mapa: cobertura, planta, anchura comprobada (distinto del de `experimental`) |
| `src/mapa.py` | Mapa en coordenadas (s, n): eje, curvatura, pendiente, bordes, `sn_a_xz` / `xz_a_sn` (D0) |
| `tests/` | Pruebas con pistas sintéticas y con Sugo |
| `pistas/sugo_gp/` | `mapa.json` (versionado), referencia suavizada (no versionada) y, cuando existan, línea óptima y gráficos |
| `coches/formula_rookie/` | `parametros_a1.json`: tablas de aceleración y frenada, retraso del freno |

## Uso

```text
python circuito_virtual/src/linea_suave.py          # escribe pistas/sugo_gp/sugo_smooth.json
python circuito_virtual/src/mapa.py construir        # escribe pistas/sugo_gp/mapa.json
python circuito_virtual/src/bordes_logs.py escanear  # recorre los logs y escribe pistas/sugo_gp/observaciones_logs.json
python circuito_virtual/src/informe_mapa.py          # escribe pistas/sugo_gp/informes/informe_mapa.html
python experimental/identificacion/analisis_a2.py --guardar circuito_virtual/coches/formula_rookie/parametros_a1.json
python -m pytest circuito_virtual/tests
```

`experimental/identificacion/analisis_a2.py` ajusta los parámetros del coche leyendo los logs de A1 con `experimental/common/analisis_a1.py`, por eso se queda en `experimental/`.
