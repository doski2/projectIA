# Diario de circuito_virtual

Lo más reciente arriba. Historia anterior en `experimental/docs/DIARIO.md`.

- **2026-11-01 — A2 con la IA a ritmo real hecho (V12, V13).** Las `lacc` del archivo de la IA valen 0,46 de lo real: se usan la guiñada y la derivada de la velocidad. Con ellas el solver predice 82,4 s sin calibrar (−15,8 %: la IA va a ≈ 70 % de su envolvente) y **97,90 s con un factor de ritmo f = 0,697** frente a 98,06 s (−0,2 %), correlación de v(s) 0,94. La aceleración y la frenada de la IA coinciden con las de A1. El lateral de la IA a 85 km/h (≈ 19,5 m/s²) supera la cota de D21. 43 tests en `circuito_virtual`.

- **2026-11-01 — Más datos en los logs y la IA a ritmo real (V10, V11).** El usuario sospecha que hay más sobre los márgenes en todos los logs y acierta: 59 logs más con terreno (sin posición; se usan con el CTE) elevan los bordes medidos al 15,4 % (izquierda) y 6,8 % (derecha) de la vuelta, con asfalto comprobado de 5,24 m de anchura mediana. Además, **la referencia original de `sugo_ai.json` era una IA a ritmo real (97,7 s, 14 vueltas, hasta 184 km/h) y está en el historial de git**; exportada a `pistas/sugo_gp/ia_ritmo_real.json`. Va por casi la misma línea que la nuestra (±2 m) y con lateral máximo de 11,9 m/s². Sirve para validar A2. 37 tests.

- **2026-11-01 — D1a hecho (V8, V9).** `src/bordes_logs.py` recorre los 47 logs de esquema 2 y saca

  por metro y lado dos cotas (rueda aún en superficie de carrera y rueda ya fuera);
  `src/informe_mapa.py` hace el informe HTML (distinto del de `experimental`). Resultado: asfalto
  comprobado en toda la vuelta, bordes medidos solo en el 1,7 % (izquierda) y el 0,5 % (derecha).
  Diseño de D1b (sesiones de mapeo) en `docs/PLAN.md`, pendiente de visto bueno. 33 tests en
  `circuito_virtual`.

- **2026-11-01 — D0 hecho (V7).** `src/mapa.py`: eje a 1 punto por metro desde la referencia

  suavizada, `sn_a_xz` / `xz_a_sn` (ida y vuelta con error de s ≤ 0,3 cm y de n ≈ 0 con |n| ≤ 6 m),
  curvatura, pendiente, bordes en NaN (D1) y guardado/carga. n positivo a la derecha y κ positiva a
  la izquierda, iguales que en producción (comprobado con `signed_lateral_error` y
  `ReferenceLine.curvature`). `pistas/sugo_gp/mapa.json` de 164 KB. 26 tests en `circuito_virtual`
  (9 nuevos).

- **2026-11-01 — Nace la carpeta (V1-V6).** El usuario decide un mapa virtual de la pista y una

  línea óptima que sirva para cualquier circuito, con los márgenes y la línea ideal en un gráfico, y
  que el comportamiento aprendido
sea una selección del agente dentro del pasillo. Se mueven aquí el solver de perfil de velocidad, el
suavizado de la referencia, sus tests y el plan. Los logs de sesión se quedan en `PCARS2-AI/logs/`.
Suites: 17 aquí, 61 en `experimental`, 471 en `PCARS2-AI`.
