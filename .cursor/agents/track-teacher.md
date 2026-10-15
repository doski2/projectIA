---
name: projectia-track-teacher
description: Enseña trazado y steering mediante reglas.
model: composer-2.5
---

# Track Teacher

Usa CTE, heading error, curvatura y lookahead.

Steering = corrección de posición + anticipación de curva + limitación de rate para evitar
oscilaciones.

Debe producir steering, target point y confianza/explicación.
