# Plan A: límites del coche (profesor físico)

Contexto: sección 2 y 5 de [ESTUDIO_SIMULADOR_Y_LIMITES.md](ESTUDIO_SIMULADOR_Y_LIMITES.md).
Código: `experimental/identificacion/` · Estado: **sin empezar** · Depende de: C0 (log ampliado)

## Hipótesis

Con unos pocos parámetros (`μ`, `k`, `a_freno(v)`, `a_acel(v, marcha)`) se puede calcular el perfil de velocidad
máxima de cualquier pista y predecir tiempos de vuelta con error < 3 %.

## Pasos

| # | Paso | Éxito si… | Estado |
| --- | --- | --- | --- |
| A0 | Analizar los logs actuales | Hecho: solo cubren ≤ 0,7 g y ≤ 61 km/h | Hecho |
| A1 | Sesiones de identificación (dejar rodar, frenadas, aceleraciones, círculos, barridos) | Curvas `a(v)` limpias | Pendiente |
| A2 | Ajustar el perfil y predecir tiempos de vueltas conocidas | Error < 3 % | Pendiente |
| A3 | Validar en una segunda pista | Mismos parámetros, mismo error | Pendiente |
| A4 | Usar el perfil como objetivo del profesor | Vuelta limpia a mayor ritmo | Pendiente |

## Riesgos a vigilar

Agarre variable (neumáticos, combustible, clima), reglaje, dificultad de llegar al límite con mando virtual.
Ver sección 2.4 del estudio.
