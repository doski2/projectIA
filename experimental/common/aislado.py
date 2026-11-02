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
from ident_arc import MAX_ARC_KMH as IDENT_MAX_ARC_KMH  # noqa: E402
from ident_maneuver import MAX_CAP_KMH as IDENT_MAX_CAP_KMH  # noqa: E402, F401  (se reexporta: los tests la leen)
from ident_maneuver import max_cap_kmh as ident_max_cap_kmh  # noqa: E402
from learn_progress import progress_file  # noqa: E402

# Aceleración lateral que el profesor supone en curva (P16). Provisional: ~0,66 g, del orden de lo que la
# conducción tranquila ya alcanzó (p99 de v·yaw_rate de 5-7 m/s² a 40-60 km/h). El plan A la medirá.
LAT_ACCEL_LIMIT = 6.5


DEFAULT_REFERENCE = "src/refs/sugo_ai.json"
A2_PREFIX = "a2_"  # vueltas completas con límite lateral o marcha propios (A2.0): tampoco pueden llamarse como los buffers de entrenamiento
MAX_LAT_ACCEL_LIMIT = 14.6  # cota inferior validada del límite lateral del coche (D21); por encima no hay datos
IDENT_PREFIX = "a1_"  # los experimentos de identificación no pueden llamarse como los buffers de entrenamiento (`teacher_40`, ...)


def experiment_name(speed_band: float, teacher_only: bool, name: str = "", ident: str = "") -> str:
    """Con el teacher al volante cada banda tiene su experimento (`teacher_40`), así no se pisan log ni buffer.
    La identificación (A1) usa `a1_<maniobra>_<banda>`, y cualquier nombre suyo debe empezar por `a1_`: `run_isolated`
    borra el buffer del experimento al empezar y `teacher_*` son datos que no se pueden recuperar."""
    if ident:
        if name and not name.startswith(IDENT_PREFIX):
            raise ValueError(f"con --ident el experimento debe empezar por {IDENT_PREFIX!r} (recibido {name!r})")
        return name or f"{IDENT_PREFIX}{ident}_{speed_band:g}"
    if name:
        return name
    return f"teacher_{speed_band:g}" if teacher_only else "c0_log"


def a2_error(ident: str, max_gear: int, lat_accel_limit: float, teacher_only: bool, experiment: str, speed_band: float, cap_limit: float,
             extra_teacher_options: bool = False) -> Optional[str]:
    """Por qué no se puede lanzar la combinación de opciones de A2.0 (vueltas completas del teacher con marcha o límite lateral propios), o None si vale."""
    if not 0 < lat_accel_limit <= MAX_LAT_ACCEL_LIMIT:
        return f"--lat-accel-limit {lat_accel_limit:g}: debe estar entre 0 y {MAX_LAT_ACCEL_LIMIT:g} m/s² (D21)"
    if ident or (max_gear == 2 and lat_accel_limit == LAT_ACCEL_LIMIT and not extra_teacher_options):
        return None
    if not teacher_only:
        return "--max-gear, --lat-accel-limit y las opciones del teacher (--steer-*, --lat-gain-v0-kmh) distintos de los de producción solo se usan con --ident o con --teacher-only (X24, A2.0)"
    if not experiment.startswith(A2_PREFIX):
        return (f"sin --ident, las opciones propias del teacher exigen --experiment con prefijo {A2_PREFIX!r}: el nombre por defecto "
                "(teacher_<banda>) borraría el buffer de datos del teacher")
    if speed_band > cap_limit:
        return f"--speed-band {speed_band:g} supera el máximo permitido ({cap_limit:g}) con --max-gear {max_gear}: H50"
    return None


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
    ramp: bool = False, ramp_ceiling: float = 80.0, ramp_step: float = 5.0, steer_damp_kmh: Optional[float] = None,
    ident: str = "", ident_cap_kmh: float = 0.0, ident_floor_kmh: float = 30.0, ident_end_margin_m: float = 150.0,
    ident_straights: str = "", ident_caps: str = "",
    ident_arc_speeds: str = "", ident_arc_window: str = "3200,600", ident_arc_cte: float = 2.5, steer_ff_gain: float = 0.0,
    max_gear: int = 2, reference: str = DEFAULT_REFERENCE, lat_accel_limit: float = LAT_ACCEL_LIMIT, steer_slip_gain: float = 0.0,
    lat_gain_v0_kmh: float = 0.0, steer_ff_v0_kmh: float = -1.0, steer_preview_s: float = 0.0,
    throttle_max: float = 0.85, brake_decel_straight: float = 0.0, brake_overspeed_straight_ms: float = 8.0,
    brake_slip_limit: float = 0.0, brake_slip_hold: float = 0.0, steer_ff_cap_kmh: float = 0.0,
) -> List[str]:
    argv = [
        str(python), str(APP / "src" / "learn_driver.py"),
        "--reference", reference,
        "--model", str(DATA / f"{experiment}_model.pt"),
        "--buffer", str(DATA / f"{experiment}_buffer.jsonl"),
        "--stage", stage, "--speed-band", f"{speed_band:g}",
        "--max-laps", str(laps), "--learn-every", str(learn_every),  # 99 = sin fine-tune dentro de la prueba
        "--steer-comp", "--experiment", experiment, "--stop-on-damage",
        "--lat-accel-limit", f"{lat_accel_limit:g}",
    ]
    if base_dataset is not None:  # fine-tune: la base es el teacher nuevo, no los datos antiguos de producción
        argv += ["--base-dataset", str(base_dataset), "--curated", ""]
    if perturb_every > 0:  # P24: el coche rueda sin pedales cada N m y se mide la recuperación
        argv += ["--perturb-every", f"{perturb_every:g}"]
    if ramp:  # C1: rampa con puerta por ciclos; el estado queda en <buffer>.ramp.json
        argv += ["--ramp", "--ramp-ceiling", f"{ramp_ceiling:g}", "--ramp-step", f"{ramp_step:g}"]
    if steer_damp_kmh is not None:  # None = el valor de producción (45 km/h); 0 = sin reducir el volante del BC
        argv += ["--steer-damp-kmh", f"{steer_damp_kmh:g}"]
    if ident:  # A1: maniobras en las rectas largas; la sesión solo vale en seco, así que cualquier lluvia la cierra
        argv += ["--ident", ident, "--ident-cap-kmh", f"{ident_cap_kmh:g}", "--ident-floor-kmh", f"{ident_floor_kmh:g}",
                 "--ident-end-margin-m", f"{ident_end_margin_m:g}", "--rain-limit", "1"]
        if ident_straights:
            argv += ["--ident-straights", ident_straights]
        if ident_caps:
            argv += ["--ident-caps", ident_caps]
        if ident == "arco":  # A1.3: la rampa de velocidades por vueltas y sus límites
            argv += ["--ident-arc-speeds", ident_arc_speeds, "--ident-arc-window", ident_arc_window,
                     "--ident-arc-cte", f"{ident_arc_cte:g}"]
    if steer_slip_gain:  # V17: contravolante por deriva; 0 = el de producción
        argv += ["--steer-slip-gain", f"{steer_slip_gain:g}"]
    if brake_decel_straight:  # V31: frenada fuerte en recta; 0 / 8 = la de producción
        argv += ["--brake-decel-straight", f"{brake_decel_straight:g}"]
    if brake_overspeed_straight_ms != 8.0:
        argv += ["--brake-overspeed-straight-ms", f"{brake_overspeed_straight_ms:g}"]
    if throttle_max != 0.85:  # V24: tope del gas del teacher al acelerar (producción 0,85)
        argv += ["--throttle-max", f"{throttle_max:g}"]
    if steer_preview_s:  # V22: anticipación del volante por tiempo; 0 = 30 m fijos de producción
        argv += ["--steer-preview-s", f"{steer_preview_s:g}"]
    if steer_ff_v0_kmh >= 0.0:  # V21: velocidad desde la que crece la anticipación de volante (por defecto 60)
        argv += ["--steer-ff-v0-kmh", f"{steer_ff_v0_kmh:g}"]
    if lat_gain_v0_kmh:  # V18: ganancia de CTE programada por velocidad; 0 = producción
        argv += ["--lat-gain-v0-kmh", f"{lat_gain_v0_kmh:g}"]
    if max_gear != 2:  # X24: el cambio automático sube hasta esa marcha (producción: 2)
        argv += ["--max-gear", str(max_gear)]
    if steer_ff_gain:  # H58: anticipación de volante escalada con la velocidad; 0 = la de producción
        argv += ["--steer-ff-gain", f"{steer_ff_gain:g}"]
    if steer_ff_cap_kmh:  # V57: tope de velocidad en el factor de la anticipación; 0 = sin tope
        argv += ["--steer-ff-cap-kmh", f"{steer_ff_cap_kmh:g}"]
    if brake_slip_limit:  # V43: limitador de frenada por deslizamiento; 0 = apagado
        argv += ["--brake-slip-limit", f"{brake_slip_limit:g}"]
    if brake_slip_hold:  # V49: memoria del pedal límite del limitador; 0 = sin memoria
        argv += ["--brake-slip-hold", f"{brake_slip_hold:g}"]
    return argv + (["--teacher-only"] if teacher_only else [])


def run_isolated(
    experiment: str, speed_band: float, laps: int, python: Optional[Path] = None, teacher_only: bool = False,
    model_src: Optional[Path] = None, finetune_every: int = 0, perturb_every: float = 0.0,
    ramp: bool = False, ramp_ceiling: float = 80.0, ramp_step: float = 5.0, resume: bool = False,
    steer_damp_kmh: Optional[float] = None,
    ident: str = "", ident_cap_kmh: float = 0.0, ident_floor_kmh: float = 30.0, ident_end_margin_m: float = 150.0,
    ident_straights: str = "", ident_caps: str = "",
    ident_arc_speeds: str = "", ident_arc_window: str = "3200,600", ident_arc_cte: float = 2.5, steer_ff_gain: float = 0.0,
    max_gear: int = 2, reference: str = DEFAULT_REFERENCE, lat_accel_limit: float = LAT_ACCEL_LIMIT, steer_slip_gain: float = 0.0,
    lat_gain_v0_kmh: float = 0.0, steer_ff_v0_kmh: float = -1.0, steer_preview_s: float = 0.0,
    throttle_max: float = 0.85, brake_decel_straight: float = 0.0, brake_overspeed_straight_ms: float = 8.0,
    brake_slip_limit: float = 0.0, brake_slip_hold: float = 0.0, steer_ff_cap_kmh: float = 0.0,
) -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    model = DATA / f"{experiment}_model.pt"
    buffer = DATA / f"{experiment}_buffer.jsonl"
    if resume and model.is_file():  # sigue el bloque anterior: mismo modelo, buffer y estado de la rampa
        print(f"[experimental] retomo {experiment}: modelo y buffer se conservan")
    else:
        shutil.copyfile(model_src or APP / "models" / "universal_bc.pt", model)
        buffer.unlink(missing_ok=True)
        Path(f"{buffer}.ramp.json").unlink(missing_ok=True)
    if ramp and not finetune_every:
        finetune_every = 3  # la rampa ajusta en meta tras cada ciclo; learn_driver fija el valor exacto
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
                ramp=ramp, ramp_ceiling=ramp_ceiling, ramp_step=ramp_step, steer_damp_kmh=steer_damp_kmh,
                ident=ident, ident_cap_kmh=ident_cap_kmh, ident_floor_kmh=ident_floor_kmh,
                ident_end_margin_m=ident_end_margin_m, ident_straights=ident_straights, ident_caps=ident_caps,
                ident_arc_speeds=ident_arc_speeds, ident_arc_window=ident_arc_window, ident_arc_cte=ident_arc_cte,
                steer_ff_gain=steer_ff_gain, max_gear=max_gear, reference=reference, lat_accel_limit=lat_accel_limit,
                steer_slip_gain=steer_slip_gain, lat_gain_v0_kmh=lat_gain_v0_kmh,
                steer_ff_v0_kmh=steer_ff_v0_kmh, steer_preview_s=steer_preview_s,
                throttle_max=throttle_max, brake_decel_straight=brake_decel_straight,
                brake_overspeed_straight_ms=brake_overspeed_straight_ms, brake_slip_limit=brake_slip_limit,
                brake_slip_hold=brake_slip_hold, steer_ff_cap_kmh=steer_ff_cap_kmh,
            ),
            cwd=APP, env=env,
        ).returncode
    except KeyboardInterrupt:  # Ctrl+C llega también a la prueba, que cierra el log y el informe por su cuenta
        print("[experimental] Ctrl+C: prueba interrumpida")
        return 130
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
    ap.add_argument("--ramp", action="store_true",
                    help="Rampa de velocidad con puerta por ciclos (C1): empieza en --speed-band y sube de --ramp-step en --ramp-step")
    ap.add_argument("--ramp-ceiling", type=float, default=80.0)
    ap.add_argument("--ramp-step", type=float, default=5.0)
    ap.add_argument("--steer-damp-kmh", type=float, default=None,
                    help="Velocidad desde la que se reduce el volante del BC ∝ 1/v (producción: 45; 0 = desactivado)")
    ap.add_argument("--reference", default=DEFAULT_REFERENCE,
                    help="Línea de referencia del teacher (por defecto src/refs/sugo_ai.json). Para alta velocidad: circuito_virtual/pistas/sugo_gp/sugo_smooth.json, "
                         "de identificacion/linea_suave.py (H61)")
    ap.add_argument("--max-gear", type=int, default=2,
                    help="Marcha más alta que sube el cambio automático (producción: 2). Con 3 o 4 sube el techo de las maniobras de A1 (X24); "
                         "con --ident, o con --teacher-only y un experimento a2_* (A2.0: vueltas completas, --speed-band hasta el techo de esa marcha)")
    ap.add_argument("--lat-accel-limit", type=float, default=LAT_ACCEL_LIMIT,
                    help=f"Aceleración lateral (m/s²) que el teacher supone en curva (por defecto {LAT_ACCEL_LIMIT:g}). Otro valor: solo con --teacher-only y un "
                         f"experimento a2_* (A2.0); máximo {MAX_LAT_ACCEL_LIMIT:g}, la cota validada (D21)")
    ap.add_argument("--steer-slip-gain", type=float, default=0.0,
                    help="Contravolante del teacher por deriva (V17): volante por radián de deriva por encima de 3° (la ganancia de CTE baja a 0 a los 8°); 0 = producción")
    ap.add_argument("--brake-decel-straight", type=float, default=0.0,
                    help="Frenada que el teacher supone en RECTA para anticipar la curva (m/s², V31); 0 = la de siempre (4)")
    ap.add_argument("--brake-overspeed-straight-ms", type=float, default=8.0,
                    help="En RECTA el pedal de freno es exceso de velocidad / este valor (m/s, V31); 8 = el de siempre, menor frena más fuerte")
    ap.add_argument("--brake-slip-limit", type=float, default=0.0,
                    help="Limitador de frenada por deslizamiento (V43): si 1 − rps delanteras / rps traseras pasa de este valor (p. ej. 0,2) el pedal baja y sube al recuperar agarre; "
                         "evita el bloqueo de las delanteras con cualquier agarre, también en la maniobra --ident frenar; 0 = apagado")
    ap.add_argument("--brake-slip-hold", type=float, default=0.0,
                    help="Con --brake-slip-limit (V49): memoria del pedal límite; tras pasar del objetivo el pedal sube deprisa solo hasta esta fracción (p. ej. 0,85) del pedal que lo provocó y despacio desde ahí; 0 = sin memoria")
    ap.add_argument("--throttle-max", type=float, default=0.85,
                    help="Tope del gas del teacher al acelerar (V24); 0,85 = producción, 1,0 = a fondo como en A1")
    ap.add_argument("--steer-preview-s", type=float, default=0.0,
                    help="Anticipación del volante por tiempo (V22): la curvatura que anticipa el volante se lee a v · T metros (mín. 4 m) en lugar de 30 m fijos; 0 = producción")
    ap.add_argument("--steer-ff-v0-kmh", type=float, default=-1.0,
                    help="Velocidad (km/h) desde la que crece la anticipación de volante de --steer-ff-gain (por defecto 60); con 0 el factor es 1 + G · v² (V21)")
    ap.add_argument("--lat-gain-v0-kmh", type=float, default=0.0,
                    help="Ganancia de CTE del teacher programada por velocidad (V18): por encima de esta velocidad se multiplica por (v0/v)²; 0 = producción")
    ap.add_argument("--steer-ff-cap-kmh", type=float, default=0.0,
                    help="Con --steer-ff-gain (V57): por encima de esta velocidad (p. ej. 100 km/h) el factor de la anticipación de volante deja de crecer; 0 = sin tope (producción)")
    ap.add_argument("--steer-ff-gain", type=float, default=0.0,
                    help="Anticipación de volante del teacher escalada con la velocidad (H58): factor 1 + G · (v² − 60²) por encima de 60 km/h; 0 = producción")
    ap.add_argument("--ident", choices=("acel", "rodar", "acelrodar", "frenar", "arco"), default="",
                    help="Identificación del coche (A1): en las rectas largas acelera a fondo hasta --ident-cap-kmh (acel), "
                         "rueda sin pedales hasta --ident-floor-kmh (rodar), las dos cosas seguidas (acelrodar) o frena a fondo desde "
                         "cada velocidad de --ident-caps (frenar) o sube por vueltas la velocidad en una ventana de curvas hasta "
                         "encontrar el límite lateral (arco, A1.3, --ident-arc-speeds); "
                         "conduce el teacher en todo lo demás")
    ap.add_argument("--ident-cap-kmh", type=float, default=0.0, help="Techo de velocidad de acel (km/h)")
    ap.add_argument("--ident-floor-kmh", type=float, default=30.0, help="Suelo de velocidad de rodar (km/h)")
    ap.add_argument("--ident-end-margin-m", type=float, default=150.0,
                    help="Metros antes de la curva en que termina la maniobra (sin validar por encima de 100 km/h)")
    ap.add_argument("--ident-caps", default="",
                    help="frenar: velocidades de entrada de las frenadas, de menor a mayor (60,80,100); cada una acelera a fondo "
                         "hasta ella y frena a fondo hasta --ident-floor-kmh")
    ap.add_argument("--ident-arc-speeds", default="",
                    help="arco: velocidades de las pasadas, una por vuelta y de menor a mayor (80,85,90); cada una solo se lanza si la "
                         "anterior fue limpia")
    ap.add_argument("--ident-arc-window", default="3200,600",
                    help="arco: inicio y fin de la ventana en metros de vuelta (por defecto, Sugo: recta de salida y curvas de 228-600 m)")
    ap.add_argument("--ident-arc-cte", type=float, default=2.5, help="arco: |CTE| en metros que corta la pasada y marca el límite")
    ap.add_argument("--ident-straights", default="",
                    help="Rectas donde se hace la maniobra, por posición (la sesión imprime la lista): 1 o 0,1; vacío = todas")
    ap.add_argument("--resume", action="store_true",
                    help="Conserva el modelo, el buffer y el estado de la rampa del experimento (siguiente bloque)")
    a = ap.parse_args()
    try:
        cap_limit = ident_max_cap_kmh(a.max_gear)
    except ValueError as exc:
        ap.error(str(exc))
    problem = a2_error(a.ident, a.max_gear, a.lat_accel_limit, a.teacher_only, a.experiment, a.speed_band, cap_limit,
                         bool(a.steer_ff_gain or a.steer_slip_gain or a.lat_gain_v0_kmh or a.steer_ff_v0_kmh >= 0.0 or a.steer_preview_s
                         or a.throttle_max != 0.85 or a.brake_decel_straight or a.brake_overspeed_straight_ms != 8.0 or a.brake_slip_limit or a.brake_slip_hold or a.steer_ff_cap_kmh))
    if problem:
        ap.error(problem)
    if a.ident in ("acel", "acelrodar") and a.ident_cap_kmh <= a.speed_band:
        ap.error(f"--ident {a.ident} necesita --ident-cap-kmh mayor que --speed-band (la maniobra acelera desde la banda hasta el techo)")
    if a.ident == "arco":
        try:
            arc_speeds = [float(c) for c in a.ident_arc_speeds.split(",") if c.strip()]
        except ValueError:
            arc_speeds = []
        if not arc_speeds:
            ap.error("--ident arco necesita --ident-arc-speeds con las velocidades de las pasadas, p. ej. 80,85,90")
        if max(arc_speeds) > IDENT_MAX_ARC_KMH:
            ap.error(f"--ident-arc-speeds {a.ident_arc_speeds}: la mayor ({max(arc_speeds):g}) supera el máximo permitido "
                     f"({IDENT_MAX_ARC_KMH:g}), H50")
        if min(arc_speeds) < a.speed_band + 5:
            ap.error(f"--ident-arc-speeds: la menor ({min(arc_speeds):g}) debe superar --speed-band ({a.speed_band:g}) en 5 km/h o más")
    if a.ident == "frenar":
        try:
            caps = [float(c) for c in a.ident_caps.split(",") if c.strip()]
        except ValueError:
            caps = []
        if not caps:
            ap.error("--ident frenar necesita --ident-caps con las velocidades de entrada, p. ej. 60,80,100")
        if max(caps) > cap_limit:
            ap.error(f"--ident-caps {a.ident_caps}: la mayor ({max(caps):g}) supera el máximo permitido ({cap_limit:g}) con --max-gear {a.max_gear}, H50")
    if a.ident and a.ident_cap_kmh > cap_limit:
        ap.error(f"--ident-cap-kmh {a.ident_cap_kmh:g} supera el máximo permitido ({cap_limit:g}) con --max-gear {a.max_gear}: "
                 "a ≈ 120 km/h la 2ª llega al corte de encendido y el coche se descontrola (H50)")
    if a.reference != DEFAULT_REFERENCE and not Path(a.reference).is_file() and not (APP / a.reference).is_file():
        ap.error(f"--reference {a.reference}: no existe (¿falta ejecutar identificacion/linea_suave.py?)")
    if a.brake_decel_straight < 0 or a.brake_decel_straight > 11.0:
        ap.error("--brake-decel-straight debe estar entre 0 y 11 m/s² (G3: 11,5-11,8 a pedal 1,0)")
    if a.brake_overspeed_straight_ms <= 0:
        ap.error("--brake-overspeed-straight-ms debe ser positivo")
    if not 0.0 <= a.brake_slip_limit < 1.0:
        ap.error("--brake-slip-limit debe estar entre 0 (apagado) y 1 (sin incluir); un valor típico es 0,2")
    if not 0.0 <= a.brake_slip_hold <= 1.0:
        ap.error("--brake-slip-hold debe estar entre 0 (sin memoria) y 1; un valor típico es 0,85")
    if a.brake_slip_hold and not a.brake_slip_limit:
        ap.error("--brake-slip-hold necesita --brake-slip-limit (la memoria es del limitador)")
    if not 0.0 < a.throttle_max <= 1.0:
        ap.error("--throttle-max debe estar entre 0 (sin incluir) y 1")
    if a.steer_ff_cap_kmh < 0:
        ap.error("--steer-ff-cap-kmh no puede ser negativo (0 = sin tope)")
    if a.steer_ff_cap_kmh and not a.steer_ff_gain:
        ap.error("--steer-ff-cap-kmh necesita --steer-ff-gain (el tope es del factor de esa anticipación)")
    if a.steer_ff_gain < 0 or a.steer_slip_gain < 0 or a.lat_gain_v0_kmh < 0 or a.steer_preview_s < 0:
        ap.error("--steer-ff-gain, --steer-slip-gain, --lat-gain-v0-kmh y --steer-preview-s no pueden ser negativos")
    if a.ident:
        a.teacher_only = True  # el BC no conduce en A1
    t0 = time.time() - 5
    try:
        experiment = experiment_name(a.speed_band, a.teacher_only, a.experiment, a.ident)
    except ValueError as exc:
        ap.error(str(exc))
    code = run_isolated(experiment, a.speed_band, a.laps, teacher_only=a.teacher_only, model_src=a.model_src,
                       finetune_every=a.finetune_every, perturb_every=a.perturb_every,
                       ramp=a.ramp, ramp_ceiling=a.ramp_ceiling, ramp_step=a.ramp_step, resume=a.resume,
                       steer_damp_kmh=a.steer_damp_kmh, ident=a.ident, ident_cap_kmh=a.ident_cap_kmh,
                       ident_floor_kmh=a.ident_floor_kmh, ident_end_margin_m=a.ident_end_margin_m,
                       ident_straights=a.ident_straights, ident_caps=a.ident_caps,
                       ident_arc_speeds=a.ident_arc_speeds, ident_arc_window=a.ident_arc_window, ident_arc_cte=a.ident_arc_cte,
                       steer_ff_gain=a.steer_ff_gain, max_gear=a.max_gear, reference=a.reference, lat_accel_limit=a.lat_accel_limit, steer_slip_gain=a.steer_slip_gain,
                       lat_gain_v0_kmh=a.lat_gain_v0_kmh, steer_ff_v0_kmh=a.steer_ff_v0_kmh, steer_preview_s=a.steer_preview_s,
                       throttle_max=a.throttle_max, brake_decel_straight=a.brake_decel_straight,
                       brake_overspeed_straight_ms=a.brake_overspeed_straight_ms, brake_slip_limit=a.brake_slip_limit,
                       brake_slip_hold=a.brake_slip_hold, steer_ff_cap_kmh=a.steer_ff_cap_kmh)
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
