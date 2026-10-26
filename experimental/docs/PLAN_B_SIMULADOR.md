# Plan B: simulador aprendido

Contexto: sección 3 de [ESTUDIO_SIMULADOR_Y_LIMITES.md](ESTUDIO_SIMULADOR_Y_LIMITES.md).
Código: `experimental/simulador/` · Estado: **en espera** · Depende de: C0, C1 y A2 resueltos

## Hipótesis

Una red que aprende la dinámica del coche en ejes propios (sin depender de la pista), con la cinemática y la
observación calculadas de forma exacta, permite entrenar a cientos de pasos por segundo.

## Pasos

| # | Paso | Pasa si… | Estado |
| --- | --- | --- | --- |
| B0 | Revisar logs: estado completo en > 1 millón de ticks | Hay datos suficientes | Pendiente |
| B1 | Modelo de un paso | Error por debajo de la resolución de la telemetría | Pendiente |
| B2 | Rollouts de 1-2 s | Error lateral < 0,5 m a 2 s sin deriva | Pendiente |
| B3 | Política entrenada en el simulador, probada en el juego | Vueltas limpias casi sin ajuste | Pendiente |
| B4 | Ciclo simulador → juego → datos | Mejora por iteración con pocas horas de juego | Pendiente |

**Puerta de entrada:** no empezar hasta que A2 salga bien (ver riesgos de la sección 3.5 del estudio).

## La lluvia como variable (D13)

La densidad de lluvia (y la lluvia acumulada reciente) pasa a ser una variable de estado del simulador, junto con la
temperatura de pista, el desgaste y el combustible. Si no hay datos mojados suficientes, el simulador se declara
válido solo para seco y se usa la política en el juego real para el resto. Un modelo entrenado solo con seco inventa
el comportamiento en mojado (riesgo de cobertura de la sección 3.5 del estudio).
