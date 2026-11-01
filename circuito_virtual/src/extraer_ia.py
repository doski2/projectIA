"""Extrae las vueltas de la IA a ritmo real de la referencia original de Sugo (`PCARS2-AI/src/refs/sugo_ai.json` del primer commit, 97,7 s por vuelta).

La referencia vigente (213,9 s, grabada a 60 km/h con el limitador de pit y mando) la sustituyó el 2026-10-10; la original sigue en el historial de git y es el único dato
de **vueltas a ritmo real** que hay (14 vueltas consistentes de 97,7-98,3 s, 135,5 km/h de media, hasta 184 km/h). Se guarda aquí en columnas compactas: por metro de vuelta,
posición (x, z), altura y, velocidad, freno, marcha, régimen y las aceleraciones locales (eje 0 lateral, eje 2 longitudinal con el signo del juego, H1/H52).

El campo de gas de la IA vale 255 en todos los puntos, así que **no sirve** para saber cuándo iba a fondo; el freno sí varía (0-172).
Las aceleraciones locales (`lacc`) de este archivo **no están en m/s²**: la correlación con v · guiñada es 0,986 pero la pendiente es 0,459 (en los logs actuales es 0,99, H52). Se guarda también la guiñada (`yaw`, eje 1 de la velocidad angular) para calcular el lateral real como |v · yaw|; la aceleración longitudinal se obtiene de la derivada de la velocidad.

Uso:
    python circuito_virtual/src/extraer_ia.py [--commit 2c972a4] [--salida circuito_virtual/pistas/sugo_gp/ia_ritmo_real.json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Dict, List

REPO = Path(__file__).resolve().parents[2]
RUTA_GIT = "PCARS2-AI/src/refs/sugo_ai.json"
SALIDA = REPO / "circuito_virtual" / "pistas" / "sugo_gp" / "ia_ritmo_real.json"
MAX_VUELTA_S = 98.5  # la vuelta 15 (105 s) y las incompletas se descartan
MIN_PUNTOS = 3500


def extraer(datos: Dict, max_vuelta_s: float = MAX_VUELTA_S) -> Dict:
    vueltas: List[Dict] = []
    for v in datos.get("all_laps", []):
        pts = v["points"]
        if v["lap_time"] > max_vuelta_s or len(pts) < MIN_PUNTOS:
            continue
        vueltas.append({
            "vuelta": v["lap_num"], "tiempo_s": v["lap_time"],
            "d": [round(p["d"], 1) for p in pts], "x": [round(p["pos"][0], 2) for p in pts], "y": [round(p["pos"][1], 2) for p in pts],
            "z": [round(p["pos"][2], 2) for p in pts], "v_ms": [round(p["spd"], 2) for p in pts], "freno": [int(p["brk"]) for p in pts],
            "marcha": [int(p["gear"]) for p in pts], "rpm": [int(p["rpm"]) for p in pts],
            "a_lat": [round(p["lacc"][0], 2) for p in pts], "a_long": [round(p["lacc"][2], 2) for p in pts],
            "yaw": [round(p["avel"][1], 4) for p in pts],
        })
    return {"pista": str(datos.get("track_name", "")).split("\x00")[0].strip(), "longitud_m": datos["track_length"],
            "origen": "sugo_ai.json del primer commit (IA a ritmo real)", "nota": "el gas de la IA vale 255 siempre: no usar. a_lat y a_long (lacc) NO están en m/s²: valen ≈ 0,46 de v·yaw; la aceleración lateral real es |v·yaw| y la longitudinal sale de la derivada de la velocidad", "vueltas": vueltas}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--commit", default="2c972a4")
    ap.add_argument("--archivo", type=Path, default=None, help="usar este JSON en vez del historial de git")
    ap.add_argument("--salida", type=Path, default=SALIDA)
    args = ap.parse_args(argv)
    if args.archivo:
        datos = json.loads(args.archivo.read_text(encoding="utf-8"))
    else:
        datos = json.loads(subprocess.run(["git", "show", f"{args.commit}:{RUTA_GIT}"], cwd=REPO, capture_output=True, check=True).stdout.decode("utf-8"))
    out = extraer(datos)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    t = [v["tiempo_s"] for v in out["vueltas"]]
    print(f"{len(t)} vueltas ({min(t):.3f}-{max(t):.3f} s) -> {args.salida} ({args.salida.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
