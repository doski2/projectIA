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

# Aceleración lateral que el profesor supone en curva (P16). Provisional: ~0,66 g, del orden de lo que la
# conducción tranquila ya alcanzó (p99 de v·yaw_rate de 5-7 m/s² a 40-60 km/h). El plan A la medirá.
LAT_ACCEL_LIMIT = 6.5


def experiment_name(speed_band: float, teacher_only: bool, name: str = "") -> str:
    """Con el teacher al volante cada banda tiene su experimento (`teacher_40`), así no se pisan log ni buffer."""
    if name:
        return name
    return f"teacher_{speed_band:g}" if teacher_only else "c0_log"


def base_sources(data: Optional[Path] = None) -> List[Path]:
    """Datos del teacher nuevo que sirven de base en el fine-tune: `c0_log` (banda 40), `teacher_<banda>` y los antiguos
    reetiquetados. Los buffers de pruebas del BC (`bc7c_20`, ...) no entran: sus filas dependen de quién conducía."""
    data = data or DATA
    files = [data / "c0_log_buffer.jsonl"] + sorted(data.glob("teacher_*_buffer.jsonl"))
    files.append(data / "universal_teacher_sinsolape.jsonl")
    return [f for f in files if f.is_file()]


def build_base_dataset(out: Path, sources: Optional[List[Path]] = None) -> int:
    """Concatena las fuentes en un solo JSONL (`out`), que `learn_driver` lee como `--base-dataset`. Devuelve las filas."""
    sources = base_sources(out.parent) if sources is None else sources
    if not sources:
        raise FileNotFoundError("no hay datos del teacher nuevo en experimental/data para armar la base")
    rows = 0
    with open(out, "w", encoding="utf-8", newline="\n") as dst:
        for src in sources:
            with open(src, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        dst.write(line if line.endswith("\n") else line + "\n")
                        rows += 1
    return rows


def build_argv(
    python: Path, experiment: str, speed_band: float, laps: int, stage: str = "l1_linea", teacher_only: bool = False,
    learn_every: int = 99, base_dataset: Optional[Path] = None, perturb_every: float = 0.0,
) -> List[str]:
    argv = [
        str(python), str(APP / "src" / "learn_driver.py"),
        "--reference", "src/refs/sugo_ai.json",
        "--model", str(DATA / f"{experiment}_model.pt"),
        "--buffer", str(DATA / f"{experiment}_buffer.jsonl"),
        "--stage", stage, "--speed-band", f"{speed_band:g}",
        "--max-laps", str(laps), "--learn-every", str(learn_every),  # 99 = sin fine-tune dentro de la prueba
        "--steer-comp", "--experiment", experiment, "--stop-on-damage",
        "--lat-accel-limit", f"{LAT_ACCEL_LIMIT:g}",
    ]
    if base_dataset is not None:  # fine-tune: la base es el teacher nuevo, no los datos antiguos de producción
        argv += ["--base-dataset", str(base_dataset), "--curated", ""]
    if perturb_every > 0:  # P24: el coche rueda sin pedales cada N m y se mide la recuperación
        argv += ["--perturb-every", f"{perturb_every:g}"]
    return argv + (["--teacher-only"] if teacher_only else [])


def run_isolated(
    experiment: str, speed_band: float, laps: int, python: Optional[Path] = None, teacher_only: bool = False,
    model_src: Optional[Path] = None, finetune_every: int = 0, perturb_every: float = 0.0,
) -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    model = DATA / f"{experiment}_model.pt"
    buffer = DATA / f"{experiment}_buffer.jsonl"
    shutil.copyfile(model_src or APP / "models" / "universal_bc.pt", model)
    buffer.unlink(missing_ok=True)
    base: Optional[Path] = None
    if finetune_every > 0:
        base = DATA / f"{experiment}_base.jsonl"
        print(f"[experimental] base del fine-tune: {build_base_dataset(base)} filas en {base.name}")

    progress = Path(progress_file())
    backup = progress.read_bytes() if progress.is_file() else None
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}
    try:
        return subprocess.run(
            build_argv(
                python or Path(sys.executable), experiment, speed_band, laps, teacher_only=teacher_only,
                learn_every=finetune_every or 99, base_dataset=base, perturb_every=perturb_every,
            ),
            cwd=APP, env=env,
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
    ap.add_argument("--experiment", default="", help="Por defecto c0_log, o teacher_<banda> con --teacher-only")
    ap.add_argument("--speed-band", type=float, default=40.0)
    ap.add_argument("--laps", type=int, default=2)
    ap.add_argument("--teacher-only", action="store_true", help="Conduce el profesor, no el BC (P16)")
    ap.add_argument("--model-src", type=Path, default=None,
                    help="BC de partida (por defecto el de producción, models/universal_bc.pt)")
    ap.add_argument("--finetune-every", type=int, default=0,
                    help="Fine-tune cada N vueltas con el teacher nuevo como base (0 = sin fine-tune, D7)")
    ap.add_argument("--perturb-every", type=float, default=0.0,
                    help="Cada N metros el coche rueda sin gas ni freno hasta perder 4,5 km/h y se suelta (P24)")
    a = ap.parse_args()
    t0 = time.time() - 5
    experiment = experiment_name(a.speed_band, a.teacher_only, a.experiment)
    code = run_isolated(experiment, a.speed_band, a.laps, teacher_only=a.teacher_only, model_src=a.model_src,
                       finetune_every=a.finetune_every, perturb_every=a.perturb_every)
    log = latest_log(experiment, t0)
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
