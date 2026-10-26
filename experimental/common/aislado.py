"""Lanza learn_driver sin tocar producción: modelo y buffer en copia, progreso restaurado al terminar.

Uso (lo lanza la pestaña Experimental, o a mano):
    python experimental/common/aislado.py --experiment c0_log --speed-band 40 --laps 2
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "PCARS2-AI"
DATA = REPO / "experimental" / "data"

sys.path.insert(0, str(APP / "src"))
from learn_progress import progress_file  # noqa: E402


def build_argv(python: Path, experiment: str, speed_band: float, laps: int, stage: str = "l1_linea") -> List[str]:
    return [
        str(python), str(APP / "src" / "learn_driver.py"),
        "--reference", "src/refs/sugo_ai.json",
        "--model", str(DATA / f"{experiment}_model.pt"),
        "--buffer", str(DATA / f"{experiment}_buffer.jsonl"),
        "--stage", stage, "--speed-band", f"{speed_band:g}",
        "--max-laps", str(laps), "--learn-every", "99",  # sin fine-tune dentro de la prueba
        "--steer-comp", "--experiment", experiment,
    ]


def run_isolated(experiment: str, speed_band: float, laps: int, python: Optional[Path] = None) -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    model = DATA / f"{experiment}_model.pt"
    buffer = DATA / f"{experiment}_buffer.jsonl"
    shutil.copyfile(APP / "models" / "universal_bc.pt", model)
    buffer.unlink(missing_ok=True)

    progress = Path(progress_file())
    backup = progress.read_bytes() if progress.is_file() else None
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}
    try:
        return subprocess.run(
            build_argv(python or Path(sys.executable), experiment, speed_band, laps), cwd=APP, env=env,
        ).returncode
    finally:
        if backup is None:
            progress.unlink(missing_ok=True)
        else:
            progress.write_bytes(backup)
        print("[experimental] progreso de aprendizaje restaurado")


def latest_log(experiment: str, since: float) -> Optional[Path]:
    """Último log de `experiment` creado desde `since` (mira la cabecera, no el nombre)."""
    for p in sorted((APP / "logs" / "learning").glob("*.jsonl"), key=lambda q: q.stat().st_mtime, reverse=True):
        if p.stat().st_mtime < since:
            break
        with open(p, encoding="utf-8") as fh:
            try:
                head = json.loads(fh.readline())
            except json.JSONDecodeError:
                continue
        if head.get("experiment") == experiment:
            return p
    return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--experiment", default="c0_log")
    ap.add_argument("--speed-band", type=float, default=40.0)
    ap.add_argument("--laps", type=int, default=2)
    a = ap.parse_args()
    t0 = time.time() - 5
    code = run_isolated(a.experiment, a.speed_band, a.laps)
    log = latest_log(a.experiment, t0)
    if log is None:
        print("[experimental] no se encontró el log de la prueba; sin informe")
    else:
        try:
            sys.path.insert(0, str(REPO))
            from experimental.common.informe_c0 import build_report

            print(f"[experimental] informe: {build_report(log, open_browser=True)['html']}")
        except Exception as exc:  # noqa: BLE001 - el informe no debe tapar el resultado de la prueba
            print(f"[experimental] no se pudo generar el informe: {exc!r}")
    sys.exit(code)
