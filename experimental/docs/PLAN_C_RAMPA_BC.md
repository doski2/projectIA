# Plan C: rampa continua de velocidad del BC

Contexto: sección 4 de [ESTUDIO_SIMULADOR_Y_LIMITES.md](ESTUDIO_SIMULADOR_Y_LIMITES.md).
Código: `experimental/rampa_bc/` · Estado: **sin empezar**

## Hipótesis

Un BC que aprende en pista con una puerta de velocidad (ciclos de 2 vueltas lanzadas, subir +5 km/h tras 2 ciclos
limpios) llega más arriba de 60 km/h y deja datos útiles para A y B.

## Pasos

| # | Paso | Éxito si… | Estado |
| --- | --- | --- | --- |
| C0 | Log con campos nuevos al final (D4/X1), verificar ejes en una curva conocida | Valores coherentes en un par de vueltas | Pendiente |
| C1 | Rampa 60 → 80 km/h con puerta | Llega a 80 limpio o se registra el escalón de rotura | Pendiente |
| C2 | Subir el techo a ~100-110 km/h | Datos hasta ~1 g de aceleración lateral implícita | Pendiente |
| C3 | Analizar aceleraciones y error del BC por velocidad | Curvas útiles para A1 y B0 | Pendiente |
| C4 | Re-destilar a PPO y repetir la noche protegida | El PPO parte de un conductor de 65-100 km/h | Pendiente |

## Por resolver antes de C1

Las preguntas de la sección 4.6 del estudio (vueltas por escalón, paso, techo, umbrales de vuelta limpia,
día o noche, sustituir o convivir). Se anotan las respuestas en este plan y en `DECISIONES.md`.

## Qué reutiliza de `src/` (sin modificarlo)

`learn_driver`, `learn_progress`, `LapTransitionGuard`, `SpeedGate` (`ppo_guard.py`), guardias de seguridad.
