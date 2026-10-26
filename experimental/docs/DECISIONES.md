# Decisiones

> Estado al 2026-10-26. Las decisiones tomadas van arriba; las pendientes abajo, con una propuesta.

## 1. Tomadas

| # | Decisión | Motivo |
| --- | --- | --- |
| D1 | La carpeta `experimental/` está en la raíz del repositorio (`projectIA/`), al lado de `PCARS2-AI/` | Es transversal: no pertenece a la GUI ni a `src` |
| D2 | `experimental/` puede importar de `PCARS2-AI/src`; al revés, nunca | Borrar la carpeta no rompe nada |
| D3 | Los logs de sesión **no se separan por carpeta**: todos van a `PCARS2-AI/logs/` como hasta ahora. Se distinguen por la cabecera (D4) | Un solo sitio y un solo formato; la separación es de logística, no de ubicación |
| D4 | El log es **siempre completo**: los campos nuevos se añaden al final del bloque `vehicle` en todas las sesiones. La **cabecera** de la sesión (primera línea del JSONL) lleva `log_schema` (versión del esquema), `origin` (`main` o `experimental`) y `experiment` (p. ej. `rampa_bc`) | Saber qué sesiones tienen datos completos y de dónde vienen sin abrir los ticks; los lectores actuales no se rompen al añadir claves al final |
| D5 | Tests de esta carpeta en `experimental/tests/`, fuera de la suite principal | La suite principal no se ensucia ni se ralentiza |
| D6 | Formato de grabación: **JSONL** (sin cambios). Para analizar y archivar, un paso aparte convierte a **Parquet** (en `experimental/common/`), con la cabecera como metadatos | JSONL aguanta cortes a mitad de sesión; Parquet es mucho más pequeño y rápido de leer |

## 2. Cambios mínimos en código existente (excepciones a la regla)

Cada uno hay que hacerlo con la menor huella posible y apuntar aquí cuando se haga.

| # | Archivo | Cambio | Estado |
| --- | --- | --- | --- |
| X1 | `PCARS2-AI/src/session_log.py` y `learn_driver.py` | `vehicle_diag` escribe siempre los campos nuevos al final (`local_velocity`, `a_long`, `a_vert`, roll/pitch…). La cabecera incorpora `log_schema`, `origin` y `experiment`. `learn_driver` recibe `--experiment <nombre>` (la pestaña Experimental lo pasa siempre); sin él, `origin` es `main`. Test: sin el argumento, ruta y nombre no cambian | Pendiente |
| X2 | `PCARS2-AI/v2/gui.py` (líneas 94-103) | Añadir la pestaña Experimental con importación protegida (`try/except ImportError`) | Pendiente |
| X3 | `.gitignore` | Ignorar `experimental/data/` y `experimental/logs/` | Pendiente |

X1 solo toca `learn_driver` por ahora (el que usa la Idea C); `imitation_driver` y `teaching_driver` quedan para después.

## 3. Por decidir

| # | Pregunta | Propuesta |
| --- | --- | --- |
| P1 | ¿Cuánto engordan los logs con los campos nuevos? | Medirlo en C0 con un par de vueltas; si es mucho, convertir a Parquet más a menudo (D6) |
| P2 | ¿Un `.bat` por experimento o un lanzador único con subcomandos? | Lanzador único `experimental.bat <modo>` |
| P3 | ¿Se versionan los planes y el diario? | Sí; datos y salidas de análisis no |
| P4 | ¿Cuándo se promueve algo a `PCARS2-AI/src`? | Cuando cumple el criterio de éxito de su plan, tiene tests y se anota aquí |
| P5 | Orden de trabajo | C0 (log ampliado) → C1 (rampa 60→80) → sesiones de identificación → A1-A2 → B0 solo si A2 sale bien (ver sección 6 del estudio) |
| P6 | Preguntas de la Idea C (sección 4.6 del estudio): vueltas por escalón, paso, techo, qué es vuelta limpia, día o noche, sustituir o convivir | Se resuelven en `PLAN_C_RAMPA_BC.md` |
| P7 | ¿`pyarrow` está en el entorno? Si no, añadirlo a `requirements.txt` | Comprobar antes de D6 |

## 4. Cómo registrar una decisión nueva

Mover la fila de "Por decidir" a "Tomadas" con la fecha y el motivo, y, si implica tocar código existente, añadirla a la sección 2.
