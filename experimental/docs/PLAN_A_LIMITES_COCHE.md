# Plan A: límites del coche (profesor físico)

Contexto: sección 2 y 5 de [ESTUDIO_SIMULADOR_Y_LIMITES.md](ESTUDIO_SIMULADOR_Y_LIMITES.md).
Código: `experimental/identificacion/` · Estado: **A1.1 en código** · Depende de: C0 (log ampliado)

## Hipótesis

Con unos pocos parámetros (`μ`, `k`, `a_freno(v)`, `a_acel(v, marcha)`) se puede calcular el perfil
de velocidad
máxima de cualquier pista y predecir tiempos de vuelta con error < 3 %.

## Pasos

| #   | Paso                                                                                                                                                                                 | Éxito si…                              | Estado                                                                                                                           |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| A0  | Analizar los logs actuales                                                                                                                                                           | Hecho: solo cubren ≤ 0,7 g y ≤ 61 km/h | Hecho                                                                                                                            |
| A1  | Sesiones de identificación (dejar rodar, frenadas, aceleraciones, círculos, barridos), por fases: A1.1 rodar + aceleración, A1.2 frenadas, A1.3 arcos, A1.4 barridos (fuera hasta B) | Curvas `a(v)` limpias                  | En curso: A1.1 hecho con datos limpios de 0 a 120 km/h (H47-H50); A1.2 hecho (H51); A1.3 en código (X22), sin probar en el juego |
| A2  | Ajustar el perfil y predecir tiempos de vueltas conocidas                                                                                                                            | Error < 3 %                            | Pendiente                                                                                                                        |
| A3  | Validar en una segunda pista                                                                                                                                                         | Mismos parámetros, mismo error         | Pendiente                                                                                                                        |
| A4  | Usar el perfil como objetivo del profesor                                                                                                                                            | Vuelta limpia a mayor ritmo            | Pendiente                                                                                                                        |

## Riesgos a vigilar

Agarre variable (neumáticos, combustible, clima), reglaje, dificultad de llegar al límite con mando
virtual.
Ver sección 2.4 del estudio.

## La lluvia como variable (D13)

Con «Clima real» habrá sesiones con lluvia. Para A no son datos a descartar: el agarre máximo
depende de la humedad
y la pérdida con neumáticos de seco es parte de lo que se quiere medir. Condiciones:

- Ajustar los parámetros (`μ`, `k`, `a_freno(v)`, `a_acel(v, marcha)`) **por nivel de lluvia**, no

  con una mezcla.

- El UDP da la densidad de lluvia, no la humedad de la pista: usar una lluvia acumulada reciente y

  comprobarla
  contra el agarre medido en las curvas.

- Las sesiones de identificación (A1) se hacen **primero en seco** para tener una referencia limpia.

## Diseño de A1.3: arcos con velocidad creciente (aprobado por el usuario el 2026-10-31; código en X22)

Es la fase que más puede salirse: se busca el límite lateral del coche. Se lanza con el usuario
delante del juego, en seco, en bloques de 3-4 vueltas, y solo después de confirmarlo (decisión del
usuario 2026-10-31).

- **Zona:** las curvas de 228-600 m de Sugo (radios ≈ 51-55 m, H52), entradas desde la recta de

  3113-3784 m (670 m). El teacher las toma a 60 km/h con 7 m/s² laterales y a 80 km/h con 11-13 (≈
  1,3 g), así que el límite está cerca.

- **Mecanismo:** una consigna de velocidad local. Dentro de la ventana [3200 m → 600 m] se sustituye

  la consigna del teacher por la velocidad de la pasada y se desactiva su límite lateral; el teacher
  conserva el volante, la línea y su PI de velocidad. No se imponen pedales (a diferencia de
  A1.1/A1.2). Cambio mínimo en `learn_driver.py` (`--ident arco`, `--ident-arc-speeds`).

- **Rampa:** 80, 85, 90, 95, 100, 105, 110 km/h, una pasada por vuelta (≈ 3:35 a banda 60). Techo

  110, por debajo de los 115 de H50: en 2ª el motor se acerca al corte de encendido a 120. Cada
  pasada solo se lanza si la anterior fue limpia. La primera que dispara un criterio de corte da el
  límite, y la sesión se cierra tras el aterrizaje. Para retomar: `--ident-arc-speeds` con la lista
  que falte.

- **Criterios de corte (cualquiera):** |CTE| > 2,5 m (la rutina llega a 1,5, H52); rueda fuera del

  asfalto (`off_surface`/`off_track`); error de rumbo > 0,30 rad (el casi trompo de H50 llegó a
  0,35); `safety_override` o `cte_takeover` del teacher; evento de daño con `stop`
  (`--stop-on-damage`).

- **Aterrizaje suave:** al cortar, la consigna baja 6 km/h por segundo hasta la banda, manteniendo

  desactivado el límite lateral para que el teacher no frene a fondo con el volante girado (lo que
  casi hizo trompear el coche en H50). No hay freno de emergencia automático.

- **Medidas (`analisis_a1.py`):** lateral del eje 0 de `local_accel` (p95 y máximo por pasada),

  velocidad en curva, CTE, volante y rumbo máximos, temperaturas y desgaste de neumáticos por pasada
  (el agarre cambia con ellos), y el ajuste de lateral frente a v² para ver dónde deja de crecer.

- **Riesgos:** (1) salirse y golpear: el corte por CTE llega a 2,5 m del eje, no es un seguro contra

  el muro; (2) el agarre cambia a lo largo de las 7 vueltas (neumáticos que se calientan y se
  gastan); (3) el volante del teacher no está validado por encima de 80 km/h en curva; (4) a ≈
  90-100 km/h el coche puede estar ya en el límite y no avisar.

- **Por decidir:** velocidad de partida (80) y paso (5); techo (110); umbral de CTE (2,5); si se

  prefiere una primera tanda 80-90 y revisar antes de seguir.
