# experimental/

Zona de pruebas del proyecto, separada del código que ya funciona (`PCARS2-AI/`).
Aquí viven las ideas A, B y C del estudio, sus planes de trabajo y sus resultados.

## Reglas

1. **Dependencia en un solo sentido.** `experimental/` puede importar de `PCARS2-AI/src`; el código de
   `PCARS2-AI/` nunca importa de `experimental/`. Borrar esta carpeta no debe romper nada.
2. **Excepciones puntuales y anotadas.** Los cambios mínimos en código existente (p. ej. los campos nuevos y la
   cabecera del log, o añadir la pestaña a la GUI) se listan en `docs/DECISIONES.md` con su motivo.
3. **Logs de sesión en el mismo sitio** (`PCARS2-AI/logs/`), distinguidos por la cabecera (`origin`,
   `experiment`, `log_schema`). Los datos derivados y análisis van a `experimental/data/` y `experimental/logs/`.
4. **Tests propios** en `experimental/tests/`, fuera de la suite principal (`PCARS2-AI/tests`).
5. **Cada experimento termina en una decisión:** promover a `PCARS2-AI/src` (con tests), archivar o
   descartar, y se anota en `docs/DIARIO.md`.

## Estructura

| Carpeta | Contenido |
| --- | --- |
| `docs/` | Estudio, planes de trabajo, decisiones y diario |
| `common/` | Piezas compartidas (log ampliado, utilidades) |
| `rampa_bc/` | Idea C: rampa continua de velocidad del BC |
| `identificacion/` | Sesiones de identificación y modelo físico (Idea A) |
| `simulador/` | Simulador aprendido (Idea B) |
| `tests/` | Tests de esta carpeta |
| `data/`, `logs/` | Salidas (no se versionan) |

## Documentos

- [docs/DECISIONES.md](docs/DECISIONES.md): decisiones tomadas y por tomar. **Empezar aquí.**
- [docs/ESTUDIO_SIMULADOR_Y_LIMITES.md](docs/ESTUDIO_SIMULADOR_Y_LIMITES.md): estudio de contexto.
- [docs/PLAN_C_RAMPA_BC.md](docs/PLAN_C_RAMPA_BC.md), [docs/PLAN_A_LIMITES_COCHE.md](docs/PLAN_A_LIMITES_COCHE.md),
  [docs/PLAN_B_SIMULADOR.md](docs/PLAN_B_SIMULADOR.md): planes de trabajo.
- [docs/DIARIO.md](docs/DIARIO.md): resultados de cada experimento.
