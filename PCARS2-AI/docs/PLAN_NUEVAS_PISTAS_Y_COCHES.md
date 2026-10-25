# Plan — nuevas pistas y nuevos coches

**Estado:** plan (no probado fuera de Sugo + Formula Rookie)
**Actualizado:** 2026-10-25
**Prerrequisito:** L1→L7 en banda 20 dominado y Hybrid/Autónomo limpios (hecho en Sugo).
La configuración del juego y del mando con la que se grabó todo está en
[CONFIGURACION_JUEGO.md](CONFIGURACION_JUEGO.md): comprobar que coincide antes de grabar en otra
pista y apuntar los cambios en su registro.

Objetivo: que una pista o un coche nuevo **aprenda la pista**, no los básicos (seguir línea,
acelerar, frenar). Eso ya lo sabe el modelo; hay que reutilizarlo, no repetir L1 desde cero.

---

## Qué se reutiliza y qué hay que rehacer

La observación es agnóstica de pista (`universal_v1`, 17 valores relativos: CTE, curvatura,
lookahead, velocidad, aceleraciones; ver [obs_universal.py](../src/obs_universal.py)). Por eso el
modelo `models/universal_bc.pt` es el punto de partida en cualquier pista.

| Elemento                    | Nueva pista (mismo coche)      | Nuevo coche (misma pista)             |
| --------------------------- | ------------------------------ | ------------------------------------- |
| `universal_bc.pt`           | Reutilizar y afinar            | Reutilizar solo como arranque         |
| Referencia (`refs/*.json`)  | **Nueva** (una por pista)      | Reutilizable                          |
| `universal_teacher.jsonl`   | Añadir vueltas de la pista     | **Regrabar** (otra respuesta del coche) |
| `online_buffer`             | Uno por pista (filtro `track_name`) | Nuevo (vacío)                    |
| Ajustes del mando en el juego | Iguales                      | **Recalibrar** (ver Fase C)           |
| Cambio de marchas           | Igual                          | Revisar `TEACHING_MAX_GEAR` y rpm     |
| Ganancias del teacher       | Iguales                        | Posible ajuste                        |

Lo que depende del **coche** (hay que medirlo, no suponerlo): la respuesta del volante, gas y
freno a lo que enviamos; las marchas disponibles; la velocidad máxima (normalización
`MAX_SPEED_MS`); el comportamiento al límite (subviraje).

---

## Flujo A — Nueva pista, mismo coche

1. **Referencia.** Graba la línea con `reference_recorder.py` (IA del juego o tu vuelta):

   ```bat
   python src\reference_recorder.py --source ai --laps 3 --output src\refs\<pista>_ai.json
   ```

2. **Teacher en la pista nueva.** `record.bat` con la referencia nueva, ≥3 vueltas, a 20 km/h.
   Añade al dataset: el entrenamiento mezcla pistas, no sustituye Sugo.
3. **Reentrenar el BC offline** con Sugo + pista nueva juntas (`entrenar_bc.bat`). Parte del
   modelo actual, no de cero. Mide con `eval_bc.bat` antes de salir a pista.
4. **Probar sin entrenar.** Hybrid corto (panel de la GUI) a 20 km/h en la pista nueva.
   - Si sale limpio: sáltate L1-L3 y pasa a **L4-L7 en banda 20** para afinar, no a L1.
   - Si hay overrides o salidas de pista: `aprender` desde L1 en la pista nueva (rápido, el
     modelo ya sabe lo básico).
5. **Subir banda** (30 → 40 …) igual que en Sugo, con buffer propio de la pista.
6. **Volver a Sugo** con Hybrid para comprobar que no se ha olvidado la pista anterior.

**Criterio de "pista aprendida":** 5 vueltas limpias seguidas en Hybrid y en Autónomo a esa
banda, con override ≈ 0-2 % y CTE por debajo de ~1,5 m.

---

## Flujo B — Nuevo coche

Aplica antes de cualquier pista nueva con ese coche.

1. **Ajustes del mando.** Mismos valores que ahora (zona muerta de dirección 0, sensibilidad de
   dirección y pedales 50, sensibilidad de velocidad 0). Cambian por coche solo si el juego los
   guarda por coche.
   Tabla completa en [CONFIGURACION_JUEGO.md](CONFIGURACION_JUEGO.md).
2. **Calibración corta.** Una sesión de `aprender` de 5-10 min y la tabla "enviado / aplicado"
   de volante, gas y freno (campo `vehicle` de cada tick). Esperado: pendiente razonable y sin
   zona muerta. Si no, ajustar el mando antes de seguir.
3. **Marchas.** Comprobar el log: marcha por velocidad y `teacher:gear`. Si el coche tiene otras
   marchas o rpm, revisar `TEACHING_MAX_GEAR` y los umbrales de [auto_shift.py](../src/auto_shift.py).
4. **Teacher del coche.** Regrabar con `record.bat` en una pista ya conocida (Sugo): así se
   aísla el efecto del coche.
5. **Reentrenar BC** con el dataset del coche nuevo. No mezclar datos de coches distintos en
   un solo modelo sin una variable que los distinga; usar un modelo por coche al principio.
6. **Currículo corto.** L1→L7 en banda 20 solo si Hybrid no sale limpio.

---

## Gestión de datos

- **Buffer por pista.** El cargador ya filtra el buffer por `track_name`
  (`load_universal_dataset(..., track_name=...)`, usado por `learn_driver`). Aun así, usa un
  archivo distinto por pista para que no crezca sin control: en la GUI, ruta de buffer
  `data/online_buffer_<pista>.jsonl`.
- **Dataset base compartido.** `universal_teacher.jsonl` acepta varias pistas. Sin filtro, así
  que cada fine-tune lo lee entero: si crece mucho, conviene un archivo por coche.
- **Tamaño.** El buffer de Sugo tiene ~1 706 000 filas (1,45 GB) y cada fine-tune lo lee entero
  para filtrarlo (~27 s de análisis solo para leerlo). El 49 % de las filas son casi idénticas a
  la anterior (60 Hz) y el 85 % son `maintain_speed`. Antes de mezclar una segunda pista conviene
  **compactarlo** (un tick de cada ~4, conservando todas las situaciones raras) y archivar los
  buffers de bandas ya superadas.
- **Solape de gas y freno.** El 64 % de las etiquetas de `universal_teacher.jsonl` lo tienen (por
  el suavizado del teacher). Reetiquetar (poner a 0 el pedal menor) al compactar, para no
  arrastrar el hábito a la pista nueva. Ver «Deuda de conducción» en
  [ROADMAP_CONDICIONES.md](ROADMAP_CONDICIONES.md).
- **Las bases son de una sola pista.** `universal_teacher.jsonl` solo tiene `SUGO_GP`; el buffer
  se filtra por `track_name`. Una pista nueva empieza con buffer propio.
- **Archivar antes de cambiar** (`archivar_sesion.bat`), no borrar.

---

## Riesgos y lo que no se sabe

- **No está probado que el BC de Sugo generalice a otra pista.** Se sabrá con el primer Hybrid
  en pista nueva; por eso el paso 3 reentrena con las dos pistas.
- **La referencia define el trazado.** Una referencia mala (línea pegada al borde, como en la
  curva de los 800 m de Sugo) limita lo que aprende el BC.
- **Coches muy distintos** (más potencia, más marchas, aerodinámica) pueden necesitar más
  cambios de los listados; mide antes de asumir.
- **Condiciones** (lluvia, desgaste, temperatura): fuera de este plan, ver
  [ROADMAP_CONDICIONES.md](ROADMAP_CONDICIONES.md).

---

## Orden recomendado

1. Terminar L1→L7 por banda en Sugo (hoy en 55 km/h, con la compensación del volante activa) y
   dejar Hybrid y Autónomo limpios.
2. Compactar y reetiquetar la base (ver «Gestión de datos»).
3. **Segunda pista con el mismo coche** (Flujo A): es el test que más información da.
4. Nuevo coche (Flujo B).
5. PPO en solitario para ser competitivo contra el reloj, y después reglaje, condiciones y
   rivales: «Secuencia hacia la carrera» en [ROADMAP_CONDICIONES.md](ROADMAP_CONDICIONES.md).
