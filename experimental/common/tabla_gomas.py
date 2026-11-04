"""Temperatura de las gomas -> agarre lateral conseguido limpio, en seco y en mojado (solo lectura de logs).

Lee todos los logs A2 (`a2_*`, `log_schema` 3) de `PCARS2-AI/logs/learning`, separa seco y mojado por el campo `rain` del registro de condiciones y, por tramos de 5 °C de la media de las
4 gomas, da la aceleración lateral que el coche consiguió **limpia** (deriva <= 4°, |CTE| <= 1,8 m y sin ruedas fuera) y el porcentaje de ticks no limpios cuando el lateral pasa de 7 m/s².
Cuidado al leerla: es agarre **conseguido**, no el máximo posible; lo que el teacher pidió también cuenta (límite 9,5 en seco, 6 en mojado), y en mojado la temperatura va unida
al número de vuelta y a si el ajuste automático estaba encendido. Solo vueltas >= 2 y a más de 40 km/h.

Uso:
    python experimental/common/tabla_gomas.py
"""

import glob
import json
import math
import os
import statistics as st
import sys
from pathlib import Path

REPO = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, os.path.join(REPO, "PCARS2-AI", "src"))
from pcars2_surface import RACING_TERRAIN_IDS  # noqa: E402
from session_log import tick_accels  # noqa: E402

LOGS = sorted(glob.glob(os.path.join(REPO, "PCARS2-AI", "logs", "learning", "*_sugo_gp_l1_linea.jsonl")))
filas = {"seco": [], "mojado": []}
usados = {"seco": [], "mojado": []}
for f in LOGS:
    with open(f, encoding="utf-8") as fh:
        cab = json.loads(fh.readline())
        if not str(cab.get("experiment") or "").startswith("a2_") or int(cab.get("log_schema") or 0) < 3:
            continue
        lluvia = 0.0
        ticks = []
        for linea in fh:
            if '"type": "conditions"' in linea:
                lluvia = max(lluvia, float(json.loads(linea).get("rain") or 0))
            elif '"type": "tick"' in linea:
                t = json.loads(linea)
                if int(t["lap"]) < 2:
                    continue
                v = t.get("vehicle") or {}
                acc = tick_accels(v)
                tt = v.get("tyre_temp")
                lv = v.get("local_velocity")
                if not acc or not tt or not lv or t["speed_kmh"] < 40:
                    continue
                beta = abs(math.degrees(math.atan2(lv[0], -lv[2]))) if -lv[2] > 5 else 0.0
                fuera = any(x not in RACING_TERRAIN_IDS for x in v.get("terrain", []))
                ticks.append((sum(tt) / len(tt), abs(acc[0]), beta, abs(float(t["signed_cte"])), fuera))
    clase = "mojado" if lluvia > 0 else "seco"
    filas[clase].extend(ticks)
    usados[clase].append(os.path.basename(f)[:16])

print("logs usados:", {k: len(v) for k, v in usados.items()})
for clase in ("seco", "mojado"):
    print(f"\n=== {clase} ({len(filas[clase])} ticks, vueltas >= 2, v > 40 km/h)")
    print("gomas °C |    n  | lateral limpio p50 / p95 / p99 / máx | ticks con lateral >= 7: n, % no limpios (deriva>4, |CTE|>1,8 o rueda fuera)")
    cubos = {}
    for tm, lat, beta, cte, fuera in filas[clase]:
        cubos.setdefault(int(tm // 5) * 5, []).append((lat, beta, cte, fuera))
    for k in sorted(cubos):
        v = cubos[k]
        if len(v) < 200:
            continue
        limpios = [lat for lat, beta, cte, fuera in v if beta <= 4 and cte <= 1.8 and not fuera]
        exigentes = [(beta > 4 or cte > 1.8 or fuera) for lat, beta, cte, fuera in v if lat >= 7]
        q = st.quantiles(limpios, n=100) if len(limpios) > 100 else [0] * 99
        pct = f"{100 * sum(exigentes) / len(exigentes):5.1f} %" if exigentes else "   -"
        print(f"{k:3d}-{k + 4:<3d} | {len(v):6d} | {st.median(limpios):5.1f} / {q[94]:5.1f} / {q[98]:5.1f} / {max(limpios):5.1f}     | {len(exigentes):6d}, {pct}")
