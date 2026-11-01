# Pendiente de circuito_virtual

Orden de trabajo. Lo que no es del circuito (rampa del BC, PPO, daño de motor P26, controles de
seco, reentreno v2) sigue en `experimental/docs/PENDIENTE.md`.

1. **G1b en el juego (con el usuario delante, en seco):** G1 otra vez con la línea suavizada.

`C:\Users\doski\projectIA\.venv\Scripts\python.exe
C:\Users\doski\projectIA\experimental\common\aislado.py --ident acel --speed-band 60 --ident-cap-kmh
135 --max-gear 3 --ident-straights 1 --reference
C:\Users\doski\projectIA\circuito_virtual\pistas\sugo_gp\sugo_smooth.json --experiment
a1_acel_g3_suave_60 --laps 3`
Éxito: llega a 135 km/h sin corte por CTE en 3300-3345 m y el volante en ±0,05 en la recta. Si no
basta: `--steer-ff-gain 0.003`, y después un corte de CTE más ancho solo en recta.

1b. ~~**A2 con la IA a ritmo real**~~ **Hecho (V12, V13):** f = 0,697 → error −0,2 % y correlación 0,94 con 4 vueltas de prueba. Siguiente: que el agente ruede una vuelta completa sobre la línea suavizada y comparar con el solver, y A3 (segunda pista).
2. ~~**D0:**~~ **Hecho (V7, 2026-11-01):** coordenadas (s, n), `src/mapa.py`,

   `pistas/sugo_gp/mapa.json`; ida y vuelta con error < 0,3 cm.

3. **D1a hecho (V9, V10: bordes izq. 15,4 %, dcha. 6,8 % con 106 logs).** **D1b, pendiente de visto bueno:** (diseño en `docs/PLAN.md`) lanzador del

   mapeo de bordes (copias de la referencia desplazadas ±0,5, ±1, ±1,5... m, rodadas a 30 km/h con
   `--reference`) y extractor de bordes desde el terreno de las ruedas. Antes, revisar que la
   guardia de superficie no aborte la sesión al primer toque de césped.

4. **D2:** línea óptima con el solver (`src/perfil_velocidad.py`) dentro del pasillo, con margen a

   los bordes y curvatura continua; gráfico en planta, desplazamiento lateral y perfil de velocidad.

5. **A2.0:** el agente ruedando vueltas completas sobre la línea suavizada (teacher en modo físico,

   límite lateral ≈ 12,5 m/s², tope de 125 km/h) para comparar el tiempo predicho con el medido
   (criterio: < 3 %).

6. **G3:** frenadas en 3ª desde 100, 110 y 115 km/h (`aislado.py --ident frenar --ident-caps

   100,110,115 --max-gear 3 --ident-straights 1`), para la bajada de marcha y la distancia.

7. **A1.3b:** arcos en 3ª y 4ª, para ver cuánto cambia el límite lateral con la marcha (D23) y fijar

   `k`.

8. **Comprobar** si el paquete de tiempos del juego trae la posición de los rivales (hoy solo se lee

   al participante propio), antes de D5.
