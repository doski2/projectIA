# Plan C: rampa continua de velocidad del BC

Contexto: sección 4 de [ESTUDIO_SIMULADOR_Y_LIMITES.md](ESTUDIO_SIMULADOR_Y_LIMITES.md).
Código: `experimental/rampa_bc/` · Estado: **sin empezar**

## Hipótesis

Un BC que aprende en pista con una puerta de velocidad (ciclos de 2 vueltas lanzadas, subir +5 km/h tras 2 ciclos
limpios) llega más arriba de 60 km/h y deja datos útiles para A y B.

## Pasos

| # | Paso | Éxito si… | Estado |
| --- | --- | --- | --- |
| C0 | Log con campos nuevos al final (D4/X1), verificar ejes en una curva conocida | Informe de C0 (D8) sin fallos y con ejes coherentes en un par de vueltas | Listo para ejecutar desde la pestaña Experimental (botón «Lanzar C0») |
| C1 | Rampa 60 → 80 km/h con puerta | Llega a 80 limpio o se registra el escalón de rotura | Pendiente |
| C2 | Subir el techo a ~100-110 km/h | Datos hasta ~1 g de aceleración lateral implícita | Pendiente |
| C3 | Analizar aceleraciones y error del BC por velocidad | Curvas útiles para A1 y B0 | Pendiente |
| C4 | Re-destilar a PPO y repetir la noche protegida | El PPO parte de un conductor de 65-100 km/h | Pendiente |

## Perfil de juego

C1 se ejecuta ya en el perfil auténtico RA (`DECISIONES.md`, D11 y sección 6): daños completos, fallos mecánicos,
desgaste de neumáticos, combustible real y tiempo real. Antes de C1 hacen falta la guardia de daños (P15) y
el teacher de un solo eje de pedal con el BC reentrenado (P16), y un C0 corto en RA (paso 7 de la línea de trabajo).

## Decidido para C1 (2026-10-30, D20)

Respuestas a las preguntas de la sección 4.6 del estudio:

- **Vueltas y paso:** ciclo de 2 vueltas lanzadas, 2 ciclos limpios seguidos para subir, paso de 5 km/h.
- **Techo:** 80 km/h en C1. Subirlo se decide en C2.
- **Vuelta limpia:** velocidad mínima y desviación solo en recta, solape ≈ 0; CTE y overrides sin aflojar salvo que los datos lo pidan.
- **Sesiones de identificación antes de la rampa:** sí (A1, paso 9, antes de C1; el usuario: «adelante es hacerlo»). Fijan el techo con el límite real del coche.
- **Subida de 20 a 60 km/h:** bucle completo en cada banda (30, 40, 50, 55, 60): check sin fine-tune, puerta y prueba de perturbaciones (`--perturb-every`); fine-tune solo si falla; al final un BC reentrenado con todas las bandas.

## Día o noche y escalera (decididos)

- **Día o noche:** C1 con el usuario pendiente, en bloques de pocas vueltas (2-3 ciclos). Las sesiones sin vigilar y de muchas vueltas se dejan para el PPO. Una vuelta a 60-80 km/h dura 3-5 min; un ciclo (salida + 2 lanzadas + ajuste) ≈ 12-15 min y un escalón (2 ciclos) 25-30 min.
- **Sustituir la escalera L1→L7:** sí, después de que C1 llegue limpio a 80 y con la prueba de perturbaciones pasada en cada banda; hasta entonces la rampa va como modo aparte y la escalera queda detrás de una opción.

## Hecho en código (X19)

`learn_driver --ramp` con la puerta por ciclos (`ramp_gate.py`), recta libre del teacher y velocidad mínima por recta; `aislado.py --ramp --resume` para encadenar bloques. Sin probar en el juego.

## Orden de trabajo

1. Subir de 20 a 60 km/h con el bucle completo en cada banda (30, 40, 50, 55, 60): check sin fine-tune y prueba de perturbaciones.
2. A1: sesiones de identificación (`PLAN_A_LIMITES_COCHE.md`); fijan el techo con el límite real del coche.
3. C1: rampa de 60 a 80 km/h con `--ramp`.

## Qué reutiliza de `src/` (sin modificarlo)

`learn_driver`, `learn_progress`, `LapTransitionGuard`, `SpeedGate` (`ppo_guard.py`), guardias de seguridad.
