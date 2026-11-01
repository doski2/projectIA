# circuito_virtual/

Mapa virtual de cada pista y su línea óptima: el eje, los bordes del asfalto, la línea suavizada, la
línea que minimiza el tiempo de vuelta y su gráfico. Nace de las conclusiones de A1-A2
(`experimental/docs/DECISIONES.md`, H56, H59, H61, D24, D25) y sirve para cualquier circuito.

**Estado (2026-11-01):** mapa (D0), cotas de borde de los logs (D1a) y línea óptima sin juego (D2)
hechos; la línea óptima ya se ha rodado en el juego (D3, en curso: gana tiempo pero el seguidor aún no
cumple el criterio de volante). Lo que falta y los comandos vigentes están en `docs/PENDIENTE.md`.

## Reglas

1. **Dependencia en un solo sentido:** `PCARS2-AI` ← `circuito_virtual` ← `experimental`.
   `circuito_virtual/` solo importa de `PCARS2-AI/src` (la línea de referencia, los terrenos, el CTE
   firmado, el teacher como seguidor). `experimental/` puede importar de aquí. `PCARS2-AI/` no importa
   nada de aquí hasta que algo se promueva, con tests y anotado.
2. **Un mapa por pista y un modelo por coche.** `pistas/<pista>/` lleva el eje, los bordes, la línea
   suavizada, la línea óptima y los gráficos. `coches/<coche>/` lleva los parámetros que se miden en A1
   (aceleración, frenada, límite lateral `μ + k·v²`).
3. **Los datos pequeños y de resultado se versionan** (mapa, observaciones de borde, parámetros del
   coche, `n(s)` de cada línea óptima en `*_n.npy`); los archivos grandes derivados (`sugo_smooth.json` y
   `sugo_optima_*.json`, 4,5 MB cada uno) se regeneran con el script y no se versionan.
4. **Logs y sesiones:** los logs de sesión se quedan en `PCARS2-AI/logs/` (los escribe producción).
   Las sesiones de identificación del coche (A1) y las del teacher (A2.0) se lanzan con
   `experimental/common/aislado.py`, que las ejecuta en un entorno aislado; el lanzador del mapeo de
   bordes (D1b) irá en `src/` y solo imprimirá los comandos (V6). El usuario lanza el juego.
5. **Tests propios** en `circuito_virtual/tests/`, fuera de las suites de `PCARS2-AI` y `experimental`
   (59 hoy).
6. **Los números de versión «V»** de los documentos son entradas del registro de decisiones, no
   versiones del software; la versión del software es el commit de git, que cada sesión guarda en la
   cabecera de su log.

## Estructura

| Ruta | Contenido |
| --- | --- |
| `docs/PLAN.md` | Plan D0-D5: coordenadas (s, n), mapeo de bordes, línea óptima, exploración y selección aprendida |
| `docs/DECISIONES.md`, `DIARIO.md` | Registro de decisiones (V1...) y diario de esta carpeta; la historia anterior está en `experimental/docs/` |
| `docs/PENDIENTE.md` | Estado actual, comandos vigentes y orden de trabajo |
| `src/perfil_velocidad.py` | Modelo del coche y de la pista: solver de perfil de velocidad de adelante y atrás (A2) |
| `src/mapa.py` | Mapa en coordenadas (s, n): eje, curvatura, pendiente, bordes, `sn_a_xz` / `xz_a_sn` (D0) |
| `src/linea_suave.py` | Suavizado de la referencia en las rectas (H61) |
| `src/bordes_logs.py` | D1a: cotas de borde por metro a partir de los logs ya grabados (terreno de las ruedas y posición); `actualizar` añade los logs nuevos a las observaciones |
| `src/linea_optima.py` | D2: línea de menor tiempo previsto dentro del pasillo comprobado (B-spline, descenso por coordenadas) y su escritura en el formato de `sugo_smooth.json`. Opciones de V36: `--pasillo-estricto` (respeta el margen donde el pasillo es estrecho), `--salto-max-rel`, `--pendiente-max`, `--margen`, `--nombre`; `holgura_rueda` da la distancia de la rueda al borde |
| `src/extraer_ia.py` | Extrae del historial de git las 14 vueltas de la IA a ritmo real (97,7 s) a `pistas/sugo_gp/ia_ritmo_real.json` |
| `src/ajuste_ia.py` | Ajusta el solver a las vueltas de la IA (envolventes de aceleración, frenada y lateral) y predice las vueltas apartadas (A2, V13) |
| `src/informe_mapa.py` | Informe HTML del mapa: cobertura, planta, anchura comprobada (distinto del de `experimental`) |
| `src/informe_linea_optima.py` | Informe HTML de D2: tiempos, planta con el pasillo, `n(s)` y velocidad por nivel de ritmo |
| `tests/` | Pruebas con pistas sintéticas y con Sugo |
| `pistas/sugo_gp/` | `mapa.json`, `observaciones_logs.json`, `ia_ritmo_real.json` y los `*_n.npy` (versionados); `sugo_smooth.json` y `sugo_optima_*.json` (no versionados); `informes/` |
| `coches/formula_rookie/` | `parametros_a1.json`: tablas de aceleración y frenada, retraso del freno |

### Herramientas de otras carpetas que trabajan con esta

| Ruta | Para qué |
| --- | --- |
| `experimental/common/aislado.py` | Lanzador aislado de las sesiones de A1 (`--ident`) y de A2.0 (`--teacher-only`); valida la combinación de opciones y las pasa a `learn_driver.py` |
| `experimental/common/resumen_sesion.py` | Resume un log de A2.0: criterio de volante (V19), tramos fuera de criterio, frenos, cambios de marcha, ruedas fuera |
| `experimental/common/analisis_a1.py` | Análisis de las sesiones de identificación A1 (aceleración, rodar, frenadas, arcos) |
| `experimental/common/analisis_volante.py` | Métricas de volante por rectas y curvas |
| `experimental/common/modelo_volante.py` | Ajusta volante → guiñada a los logs y simula en lazo cerrado la ley de volante del teacher para comprobar ganancias sin juego (V39-V41) |
| `experimental/identificacion/analisis_a2.py` | Ajusta los parámetros del coche leyendo los logs de A1 con `analisis_a1.py` |
| `PCARS2-AI/src/teacher_controller.py`, `brake_slip.py` | El seguidor y el limitador de frenada por deslizamiento (V44); todas sus opciones son opt-in |

## Uso

Desde la raíz del repositorio, con el Python del proyecto. Los archivos locales se regeneran por este
orden:

```text
python circuito_virtual/src/mapa.py construir
python circuito_virtual/src/linea_suave.py
python circuito_virtual/src/bordes_logs.py actualizar
python circuito_virtual/src/linea_optima.py --coche-a1-mu 9 --max-barridos 80
python circuito_virtual/src/linea_optima.py --coche-a1-mu 9 --max-barridos 80 --pasillo-estricto --salto-max-rel 1.0 --margen 0.6 --nombre sugo_optima_a1mu9b
```

Informes HTML (`--help` en cada uno para las opciones):

```text
python circuito_virtual/src/informe_mapa.py
python circuito_virtual/src/informe_linea_optima.py
```

Las sesiones se lanzan con `experimental/common/aislado.py` y se analizan con las herramientas de
arriba (`resumen_sesion.py <log> --previsto <s>`, `analisis_a1.py <log>`). Los comandos completos y
vigentes de cada tipo de sesión, con sus rutas absolutas, están en `docs/PENDIENTE.md`.

Tests:

```text
cd circuito_virtual
python -m pytest
```
