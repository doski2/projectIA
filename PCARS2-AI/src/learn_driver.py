"""
learn_driver.py
Aprendizaje online: BC conduce, teacher corrige, fine-tune cada N vueltas + currículo L1→L7 por banda.

Uso:
    python learn_driver.py --reference src/refs/sugo_ai.json --model models/universal_bc.pt
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from auto_shift import (
    NEUTRAL_RETRY_COOLDOWN_S,
    AutoShifter,
    auto_shift,
    maybe_engage_first_gear,
)
from pcars2_gear import (
    STEER_DAMP_REF_MS,
    TEACHING_MAX_GEAR,
    cap_bc_to_speed_target,
    choose_bc_drive_pedals,
    damp_bc_steering,
    is_forward_gear,
)
from bc_training import fine_tune_universal
from curate_dataset import load_curated
from controller import DS4Controller, decode_action
import numpy as np

from dataset_recorder import ORIGIN_TEACHER, DatasetRecorder, load_universal_dataset
from driver_cli import add_diag_track_arg, add_safety_profile_arg, ns_str
from drive_session import DriveSession
from lap_session import (
    LapCompletionTracker,
    lap_summary_row_from_result,
    lap_tick_safety_flags,
    make_lap_buffer_tick,
    print_session_lap_board,
    process_lap_rollover,
    rotate_lap_buffer,
)
from lap_transition import LapTransitionGuard
from lap_tracker import format_lap_time
from ramp_gate import DROP, END_EVENTS, RISE, RampGate, bands_from
from speed_perturbation import SpeedPerturber
from ident_arc import ArcRamp, FREE_LATERAL_MS2
from ident_maneuver import KINDS as IDENT_KINDS, IdentManeuver, find_straights, select_straights
from brake_adapt import BrakeAdaptConfig, BrakeAdapter
from exit_adapt import ExitAdaptConfig, ExitAdapter
from lat_adapt import LatAdaptConfig, LatAdapter, load_map, save_map
from learn_guards import StuckOffTrackAbort, SustainedCteGuard, is_poor_demo
from learn_progress import read_saved_speed_band, read_saved_stage, save_learn_progress
from learning_curriculum import (
    DEFAULT_LEARN_STAGE,
    LEARN_STAGES,
    get_learn_stage,
    resolve_learn_speed,
    try_advance_speed_band,
    try_advance_stage,
)
from obs_builder import encoded_action_tuple
from brake_slip import BrakeSlipConfig, BrakeSlipLimiter
from obs_universal import OBS_SCHEMA, OBS_UNIVERSAL_DIM, build_obs_universal
from reference_recorder import ReferenceLine
from safety_monitor import SafetyMonitor
from session_log import DamageWatch, TeachingSessionRecorder, compound_diag, conditions_diag, default_log_path, rain_over_limit, timing_diag, vehicle_diag
from teacher_controller import TeacherConfig, TeachingController, resolve_teacher_decision
from track_deviation import maybe_build_track_diag
from teacher_intents import rule_for_reason
from universal_policy import UniversalPolicy, load_universal_policy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PCARS2-AI — Aprendizaje online (BC + teacher + fine-tune por vuelta)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--reference", "-r", required=True)
    parser.add_argument("--model", "-m", default="models/universal_bc.pt")
    parser.add_argument("--base-dataset", default="data/universal_teacher.jsonl",
                        help="Dataset inicial de record.bat (replay en fine-tune)")
    parser.add_argument("--buffer", default="data/online_buffer.jsonl",
                        help="Buffer incremental de correcciones del teacher")
    parser.add_argument("--curated", default="data/curated_buffer.npz",
                        help="Buffer compactado por curate_dataset.py (se suma al buffer nuevo)")
    parser.add_argument(
        "--stage",
        default=None,
        choices=list(LEARN_STAGES.keys()),
        help="Etapa inicial (omitir = última guardada en v2/user_learn_settings.json)",
    )
    parser.add_argument("--speed-band", type=float, default=0.0,
                        help="Banda fija km/h (0 = última guardada o 20)")
    parser.add_argument("--speed-target", type=float, default=0.0,
                        help="Override fino km/h (0 = usa banda de velocidad)")
    parser.add_argument("--learn-every", type=int, default=1,
                        help="Fine-tune cada N vueltas completas")
    parser.add_argument("--fine-tune-epochs", type=int, default=8)
    parser.add_argument("--max-laps", type=int, default=0, help="0 = sin límite")
    parser.add_argument(
        "--steer-comp", action="store_true",
        help="Compensa la curva de respuesta del volante del juego (steering_curve.py)",
    )
    parser.add_argument(
        "--max-gear", type=int, default=TEACHING_MAX_GEAR,
        help="Marcha más alta que sube el cambio automático (producción: 2). Más alta solo en sesiones de identificación A2.0 (X24).",
    )
    parser.add_argument(
        "--steer-ff-gain", type=float, default=0.0,
        help="Anticipación de volante del teacher escalada con la velocidad: factor 1 + G · (v² − 60²) por encima de 60 km/h (H58). 0 = producción.",
    )
    parser.add_argument(
        "--steer-ff-cap-kmh", type=float, default=0.0,
        help="Con --steer-ff-gain (V57): por encima de esta velocidad (p. ej. 100 km/h) el factor de la anticipación de volante deja de crecer; a más velocidad la anticipación se pasa de lo que pide el coche. 0 = sin tope (producción).",
    )
    parser.add_argument(
        "--pedal-technique", action="store_true",
        help="Técnica de pedales del teacher (V65), solo con --lat-accel-limit: gas cortado del todo antes de frenar y sin rebotes, freno que se suelta hasta el vértice y gas que solo sube desde el vértice. Sin esto, producción.",
    )
    parser.add_argument(
        "--brake-profile", action="store_true",
        help="Con --pedal-technique (V68, F1): la consigna de velocidad es un perfil continuo con el presupuesto del círculo de adherencia (sin el salto de 8 a 4 m/s² al entrar en la curva) y el freno lo sigue por avance, sin margen. Usa --brake-decel-straight como deceleración en recta. Sin esto, producción.",
    )
    parser.add_argument(
        "--brake-circle", type=float, default=14.6,
        help="Con --brake-profile: radio del círculo de adherencia en m/s² (por defecto la cota lateral de D21, 14,6).",
    )
    parser.add_argument(
        "--profile-peak-min-m", type=float, default=0.0,
        help="Con --brake-profile (V79, F13): quita de la consigna de velocidad los picos más estrechos que estos metros (se aplanan al valle más alto de alrededor): el coche deja de acelerar en tramos cortos entre curvas para frenar enseguida (p. ej. 60 = C5-C6, C9 y C10; 150 = también C12-C14). 0 = sin recorte.",
    )
    parser.add_argument(
        "--profile-peak-min-kmh", type=float, default=0.0,
        help="Con --profile-peak-min-m (V81): solo se aplana un pico si el recorte lo baja al menos estos km/h (medido sobre el perfil lateral, antes del barrido hacia atrás); deja intactos los picos pequeños, p. ej. el de 1,4 km/h junto a C4. 0 = sin umbral.",
    )
    parser.add_argument(
        "--lat-adapt", action="store_true",
        help="Límite lateral por curva que se ajusta solo vuelta a vuelta (lat_adapt.py): sube un 4 %% las curvas limpias con margen y baja un 8 %% las que salen fuera de V19. Necesita --lat-accel-limit. Sin esto, el mismo límite en toda la vuelta.",
    )
    parser.add_argument(
        "--lat-adapt-max-scale", type=float, default=1.15,
        help="Con --lat-adapt: multiplicador máximo de una curva sobre --lat-accel-limit (por defecto 1,15). Con un límite base prudente (p. ej. 6 en mojado) conviene subirlo.",
    )
    parser.add_argument(
        "--lat-adapt-cap", type=float, default=10.0,
        help="Con --lat-adapt: el límite lateral de ninguna curva pasa de este valor en m/s² (por defecto 10; con 10 en toda la vuelta se ganaba 1,9 s pero no cumplía V19).",
    )
    parser.add_argument(
        "--lat-adapt-save", default="",
        help="Con --lat-adapt: guarda en este JSON el mapa de multiplicadores por curva (con las condiciones: lluvia, pista, compuesto, gomas) al cerrar cada vuelta, solo si las dos últimas fueron limpias (ninguna curva baja). No sobrescribe con una sesión sucia.",
    )
    parser.add_argument(
        "--lat-adapt-load", default="",
        help="Con --lat-adapt: arranca con el mapa guardado en este JSON en vez de con 1,0 en todas las curvas. Solo se aplica si es compatible (seco con seco, mismo compuesto); con otras temperaturas de pista o de gomas el margen sobre 1,0 se recorta (más frío o más caliente) y la subida se frena. Nunca acelera respecto al ajuste normal.",
    )
    parser.add_argument(
        "--lat-adapt-fixed", action="store_true",
        help="Con --lat-adapt-load: usa el mapa cargado y no aprende más (se registra todo pero no cambia ningún multiplicador); para comparar una sola variable.",
    )
    parser.add_argument(
        "--brake-adapt", action="store_true",
        help="Deceleración de frenada por curva que se ajusta sola vuelta a vuelta (brake_adapt.py): mide con qué velocidad sobre el perfil se suelta el freno; baja un 8 %% la deceleración de una frenada que llega pasada (> 1 m/s) y sube un 4 %% la que llega por debajo con holgura (< −0,3 m/s) y sin forzar. Necesita --brake-profile, --pedal-technique y --brake-decel-straight.",
    )
    parser.add_argument("--brake-adapt-max-scale", type=float, default=1.15, help="Con --brake-adapt: multiplicador máximo de la deceleración de una frenada (por defecto 1,15).")
    parser.add_argument("--brake-adapt-save", default="", help="Con --brake-adapt: guarda el mapa de multiplicadores de frenada (mismo formato y misma regla de cola limpia que --lat-adapt-save).")
    parser.add_argument("--brake-adapt-load", default="", help="Con --brake-adapt: arranca con este mapa (mismas condiciones y recorte que --lat-adapt-load; nunca frena más tarde que el ajuste normal).")
    parser.add_argument("--brake-adapt-fixed", action="store_true", help="Con --brake-adapt-load: usa el mapa cargado y no aprende más (se mide y se registra, pero no cambia nada).")
    parser.add_argument(
        "--exit-adapt", action="store_true",
        help="Gas de salida por curva que se ajusta solo vuelta a vuelta (exit_adapt.py): el radio de --exit-circle de cada curva sube un 4 %% si su salida es limpia y el tope recortaba el gas, y baja un 8 %% si las traseras patinan, hay deriva > 5° o |CTE| > 2 m. Necesita --exit-circle y --pedal-technique.",
    )
    parser.add_argument("--exit-adapt-max-scale", type=float, default=1.3, help="Con --exit-adapt: multiplicador máximo del radio de una curva (por defecto 1,3).")
    parser.add_argument("--exit-adapt-save", default="", help="Con --exit-adapt: guarda el mapa de multiplicadores del gas de salida (mismo formato y misma regla de cola limpia que --lat-adapt-save).")
    parser.add_argument("--exit-adapt-load", default="", help="Con --exit-adapt: arranca con este mapa (mismas condiciones y recorte que --lat-adapt-load; nunca acelera más que el ajuste normal).")
    parser.add_argument("--exit-adapt-fixed", action="store_true", help="Con --exit-adapt-load: usa el mapa cargado y no aprende más (se mide y se registra, pero no cambia nada).")
    parser.add_argument(
        "--exit-circle", type=float, default=0.0,
        help="Con --pedal-technique (V72, F3): en la salida de curva el gas no pasa de gas_max · √(1 − (lateral medido / este radio)²) (p. ej. 14,6 = cota lateral de D21); con 11,7 m/s² laterales el tope es 0,60. 0 = sin tope.",
    )
    parser.add_argument(
        "--pedal-exit-slew", type=float, default=1.5,
        help="Con --pedal-technique: subida máxima del gas por segundo desde el vértice (1,5 = de 0 a fondo en ≈ 0,7 s; 0,8 = ≈ 1,2 s).",
    )
    parser.add_argument(
        "--steer-slip-gain", type=float, default=0.0,
        help="Contravolante del teacher por deriva (V17): volante por radián de deriva por encima de 3°, y la ganancia de CTE baja a 0 a los 8°. 0 = producción.",
    )
    parser.add_argument(
        "--steer-ff-v0-kmh", type=float, default=-1.0,
        help="Velocidad (km/h) desde la que crece la anticipación de volante con --steer-ff-gain: factor 1 + G · (v² − v0²). Por defecto 60; con 0 el factor es 1 + G · v² (V21). Negativo = el de siempre.",
    )
    parser.add_argument(
        "--steer-preview-s", type=float, default=0.0,
        help="Anticipación del volante por tiempo (V22): la curvatura que anticipa el volante se lee a v · T metros (mín. 4 m) en lugar de 30 m fijos. 0 = producción.",
    )
    parser.add_argument(
        "--brake-decel-straight", type=float, default=0.0,
        help="Frenada que el teacher supone en RECTA para anticipar la curva (m/s², V31). 0 = la de siempre (4 m/s²).",
    )
    parser.add_argument(
        "--brake-overspeed-straight-ms", type=float, default=8.0,
        help="En RECTA el pedal de freno es exceso de velocidad / este valor (m/s, V31). 8 = el de siempre; menor frena más fuerte.",
    )
    parser.add_argument(
        "--brake-slip-limit", type=float, default=0.0,
        help="Limitador de frenada por deslizamiento (V43): si 1 − rps delanteras / rps traseras pasa de este valor (p. ej. 0,2) el pedal baja y vuelve a subir al recuperar agarre; "
             "evita el bloqueo de las delanteras con cualquier agarre. Actúa sobre el pedal de cualquier origen (teacher, maniobra `frenar`). 0 = apagado (producción).",
    )
    parser.add_argument(
        "--brake-slip-hold", type=float, default=0.0,
        help="Con --brake-slip-limit (V49): memoria del pedal límite. Tras pasar del objetivo, el pedal sube deprisa solo hasta esta fracción (p. ej. 0,85) del pedal que lo provocó y despacio desde ahí, "
             "en lugar de volver siempre a 1,0 y oscilar. 0 = sin memoria.",
    )
    parser.add_argument(
        "--throttle-max", type=float, default=0.85,
        help="Tope del gas del teacher al acelerar (V24). 0,85 = producción; con 1,0 acelera a fondo como en A1.",
    )
    parser.add_argument(
        "--lat-gain-v0-kmh", type=float, default=0.0,
        help="Ganancia de CTE del teacher programada por velocidad (V18): por encima de esta velocidad se multiplica por (v0/v)². 0 = producción.",
    )
    parser.add_argument(
        "--steer-damp-kmh", type=float, default=STEER_DAMP_REF_MS * 3.6,
        help="Por encima de esta velocidad el volante del BC se reduce ∝ 1/v (0 = desactivado)",
    )
    parser.add_argument("--gamepad", choices=["xbox", "ds4"], default="xbox")
    parser.add_argument("--log-every", type=int, default=50)
    parser.add_argument("--session-log", default="")
    parser.add_argument(
        "--experiment",
        default="",
        help="Nombre del experimento (carpeta experimental/). Marca la cabecera del log: origin=experimental.",
    )
    parser.add_argument(
        "--stop-on-damage", action="store_true",
        help="Cierra la sesión ante un daño que contamina los datos: neumático arrancado, choque grave, salto brusco "
             "de un canal (--damage-jump) o un canal que acumula --damage-limit. El desgaste lento no para. "
             "El evento `damage` se registra siempre, con o sin esta opción.",
    )
    parser.add_argument(
        "--damage-limit", type=float, default=25.0,
        help="%% de la escala del byte de daño que, sumado a lo largo de la sesión en cualquier canal, cierra la sesión "
             "con --stop-on-damage. 0 = cualquier empeoramiento. Valor inicial sin validar (P15).",
    )
    parser.add_argument(
        "--damage-jump", type=float, default=10.0,
        help="%% de la escala que un canal puede empeorar en ~1 s antes de contarse como golpe. Valor inicial sin validar.",
    )
    parser.add_argument(
        "--lat-accel-limit", type=float, default=0.0,
        help="Aceleración lateral máxima (m/s²) que el profesor supone para fijar la velocidad en curva: "
             "v = sqrt(a/|curvatura|), con anticipación de frenada. 0 = regla heurística de siempre. "
             "Valor provisional hasta medir el límite del coche (plan A).",
    )
    parser.add_argument(
        "--rain-limit", type=int, default=0,
        help="Cierra la sesión cuando la densidad de lluvia del juego (0-255) llega a este valor. 0 = sin límite. "
             "El evento `conditions` registra la lluvia siempre. Sin valor calibrado: hace falta lluvia real (P21).",
    )
    parser.add_argument(
        "--hold-stage", action="store_true",
        help="No sube de etapa ni de banda y no cierra la sesión al cumplir el objetivo: acaba solo por --max-laps (o Ctrl+C). "
             "Sin esta opción, dos vueltas limpias dan el objetivo por cumplido y cierran la sesión aunque --max-laps sea mayor "
             "(las sesiones --ident ya están exentas).",
    )
    parser.add_argument(
        "--teacher-only", action="store_true",
        help="Conduce el profesor en toda la vuelta (sin consultar al BC): sirve para medir sus pedales, el PI de "
             "velocidad y el modelo físico de curva (P16). Los ticks salen con drive_source=teacher:only.",
    )
    parser.add_argument(
        "--perturb-every", type=float, default=0.0,
        help="Cada N metros de vuelta el coche rueda sin gas ni freno hasta perder --perturb-drop-kmh y se suelta, "
             "para probar si quien conduce (el BC) recupera la velocidad; el teacher etiqueta la recuperación. "
             "Los ticks perturbados salen con drive_source=perturb:coast. 0 = sin perturbación (P24).",
    )
    parser.add_argument(
        "--perturb-drop-kmh", type=float, default=4.5,
        help="Velocidad que se deja perder en cada perturbación (4,5 km/h cruza con holgura el umbral de accel_straight).",
    )
    parser.add_argument(
        "--ident", choices=IDENT_KINDS + ("arco",), default="",
        help="Maniobra de identificación del coche (A1): en las rectas largas, `acel` acelera a fondo hasta --ident-cap-kmh y "
             "`rodar` rueda sin pedales hasta --ident-floor-kmh; el resto lo conduce el teacher. Ticks con drive_source=ident:*; "
             "no se graban en el buffer. `arco` (A1.3) no impone pedales: sube por vueltas la consigna del teacher en una ventana de curvas "
             "(--ident-arc-speeds) hasta que algún criterio de corte marca el límite lateral.",
    )
    parser.add_argument("--ident-arc-speeds", default="", help="`arco`: velocidades de las pasadas, de menor a mayor (p. ej. 80,85,90).")
    parser.add_argument("--ident-arc-window", default="3200,600",
                        help="`arco`: inicio y fin de la ventana en metros de vuelta (Sugo: la recta de salida y las curvas de 228-600 m).")
    parser.add_argument("--ident-arc-cte", type=float, default=2.5, help="`arco`: |CTE| que corta la pasada (m).")
    parser.add_argument("--ident-arc-heading", type=float, default=0.30, help="`arco`: error de rumbo que corta la pasada (rad).")
    parser.add_argument("--ident-arc-decay", type=float, default=6.0, help="`arco`: km/h por segundo que baja la consigna tras un corte.")
    parser.add_argument("--ident-cap-kmh", type=float, default=0.0, help="Techo de velocidad de `acel` y `acelrodar` (km/h).")
    parser.add_argument(
        "--ident-caps", default="",
        help="`frenar`: velocidades de entrada de las frenadas, de menor a mayor y separadas por comas (p. ej. 60,80,100); "
             "cada una acelera a fondo hasta ella y frena a fondo hasta --ident-floor-kmh.",
    )
    parser.add_argument("--ident-floor-kmh", type=float, default=30.0, help="Suelo de velocidad de `rodar` y de las frenadas (km/h).")
    parser.add_argument(
        "--ident-straights", default="",
        help="Rectas donde se hace la maniobra, por posición en la lista que imprime la sesión (`1`, `0,1`); vacío = todas.",
    )
    parser.add_argument(
        "--ident-end-margin-m", type=float, default=150.0,
        help="Metros antes de la curva en que la maniobra termina para que el teacher frene; sin validar por encima de 100 km/h.",
    )
    parser.add_argument(
        "--ramp", action="store_true",
        help="Rampa de velocidad con puerta por ciclos (C1): empieza en --speed-band y sube --ramp-step km/h tras 2 ciclos "
             "limpios (salida + 2 vueltas lanzadas, con ajuste en meta). Un ciclo sucio se repite; 3 seguidos bajan una banda.",
    )
    parser.add_argument("--ramp-ceiling", type=float, default=80.0, help="Techo de la rampa en km/h (D20: 80 en C1).")
    parser.add_argument("--ramp-step", type=float, default=5.0, help="Paso de la rampa en km/h.")
    parser.add_argument(
        "--ramp-state", default="",
        help="JSON con el estado de la puerta para retomar la rampa (por defecto <buffer>.ramp.json).",
    )
    parser.add_argument("--open-report", action="store_true")
    parser.add_argument("--auto-shift", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--min-buffer-samples", type=int, default=200)
    add_safety_profile_arg(parser)
    add_diag_track_arg(parser)
    return parser.parse_args()


FINE_TUNE_MIN_QUALITY = 0.5  # alineado con pretrain_universal.py --min-quality


def _concat_universal_chunks(chunks: list) -> tuple:
    obs_parts, act_parts, rid_parts, meta = [], [], [], []
    for obs, act, rid, rows in chunks:
        if len(obs) == 0:
            continue
        obs_parts.append(obs)
        act_parts.append(act)
        rid_parts.append(rid)
        meta.extend(rows)
    if not obs_parts:
        return (
            np.zeros((0, OBS_UNIVERSAL_DIM), dtype=np.float32),
            np.zeros((0, 3), dtype=np.float32),
            np.zeros(0, dtype=np.int64),
            [],
        )
    return np.concatenate(obs_parts), np.concatenate(act_parts), np.concatenate(rid_parts), meta


def _load_training_data(
    buffer_path: str,
    base_path: str,
    stage_id: str,
    speed_band_kmh: float,
    track_name: str = "",
    curated_path: str = "",
) -> tuple:
    """Base teacher sin filtro; curado y buffer online filtrados por etapa + banda + pista."""
    chunks = []
    if os.path.isfile(base_path):
        chunks.append(load_universal_dataset(base_path, min_quality=FINE_TUNE_MIN_QUALITY))
    if curated_path and os.path.isfile(curated_path):
        chunks.append(load_curated(
            curated_path,
            learn_stage=stage_id,
            speed_band_kmh=speed_band_kmh,
            track_name=track_name or None,
        ))
    if os.path.isfile(buffer_path):
        chunks.append(load_universal_dataset(
            buffer_path,
            min_quality=FINE_TUNE_MIN_QUALITY,
            learn_stage=stage_id,
            speed_band_kmh=speed_band_kmh,
            track_name=track_name or None,
        ))
    if not chunks:
        return load_universal_dataset(
            buffer_path,
            min_quality=FINE_TUNE_MIN_QUALITY,
            learn_stage=stage_id,
            speed_band_kmh=speed_band_kmh,
            track_name=track_name or None,
        )
    if len(chunks) == 1:
        return chunks[0]
    return _concat_universal_chunks(chunks)


@dataclass
class LearnProgress:
    """Estado de progreso del currículo durante una sesión de aprendizaje."""

    stage_id: str
    speed_band: float
    clean_streak: int = 0
    max_clean_streak: int = 0
    goal_reached: bool = False
    autonomy_announced: bool = False

    def record_lap(self, clean: bool) -> None:
        self.clean_streak = self.clean_streak + 1 if clean else 0
        self.max_clean_streak = max(self.max_clean_streak, self.clean_streak)


def advance_progress(prog: LearnProgress, persist: Callable[[], None]) -> None:
    """Intenta subir de etapa y de banda de velocidad tras una vuelta."""
    new_stage, advanced, msg = try_advance_stage(prog.stage_id, prog.clean_streak)
    if advanced:
        prog.stage_id = new_stage
        prog.clean_streak = 0
        prog.goal_reached = True
        persist()
        print(f"[Learn] *** {msg} ***")
    else:
        print(f"[Learn] {msg}")

    new_band, band_advanced, band_stage, band_msg = try_advance_speed_band(
        prog.speed_band, prog.stage_id, prog.clean_streak,
    )
    if band_advanced:
        prog.speed_band = new_band
        prog.stage_id = band_stage
        prog.clean_streak = 0
        prog.goal_reached = True
        prog.autonomy_announced = False
        persist()
        print(f"[Learn] *** {band_msg} ***")
    elif band_msg:
        print(f"[Learn] {band_msg}")
        prog.goal_reached = True


def advance_ramp(
    prog: LearnProgress, ramp: RampGate, clean: bool, save_ramp: Callable[[], None], persist: Callable[[], None],
) -> Optional[str]:
    """Registra la vuelta en la puerta por ciclos; si cambia la banda la pasa al progreso, y si la rampa termina cierra el objetivo."""
    event = ramp.on_lap(clean)
    print(f"[Learn] Rampa: {ramp.message}")
    if event in (RISE, DROP):
        prog.speed_band = ramp.band
        prog.clean_streak = 0
        persist()
    if event in END_EVENTS:
        prog.goal_reached = True
    save_ramp()
    return event


def announce_autonomy(prog: LearnProgress) -> None:
    stage_now = get_learn_stage(prog.stage_id)
    if (
        not prog.autonomy_announced
        and stage_now.autonomous_ready
        and prog.max_clean_streak >= stage_now.clean_laps_required
    ):
        prog.autonomy_announced = True
        print(
            "[Learn] *** Listo para autonomía total — "
            "usa imitar_autonomo.bat cuando quieras ***"
        )


class BackgroundFineTuner:
    """Fine-tune del modelo (síncrono o en hilo) y recarga protegida por lock."""

    def __init__(
        self,
        args: argparse.Namespace,
        prog: LearnProgress,
        lap_guard: LapTransitionGuard,
        model: Optional[UniversalPolicy],
        track_name: str = "",
    ) -> None:
        self.args = args
        self.track_name = track_name
        self.prog = prog
        self.lap_guard = lap_guard
        self.model = model
        self.lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def finished(self) -> bool:
        return self._thread is not None and not self._thread.is_alive()

    def _reload_model(self) -> None:
        if os.path.isfile(self.args.model):
            self.model = load_universal_policy(self.args.model)

    def run_sync(self) -> None:
        args = self.args
        obs, act, rid, _ = _load_training_data(
            args.buffer, args.base_dataset, self.prog.stage_id, self.prog.speed_band,
            self.track_name, args.curated,
        )
        result = fine_tune_universal(
            model_path=args.model,
            obs_array=obs,
            act_array=act,
            reason_ids=rid,
            output_path=args.model,
            epochs=args.fine_tune_epochs,
            min_samples=args.min_buffer_samples,
        )
        if result.get("trained"):
            with self.lock:
                self._reload_model()
            print(f"[Learn] Fine-tune OK — loss={result.get('best_loss', 0):.6f}")

    def start_async(self) -> bool:
        if self.running:
            print("[Learn] Fine-tune ya en curso — se omite")
            return False
        # Frena en meta. El BC no sale hasta que el modelo está cargado y hay 1ª.
        self.lap_guard.set_fine_tuning(True)
        self._thread = threading.Thread(target=self.run_sync, daemon=True)
        self._thread.start()
        print("[Learn] Fine-tune en curso — frenando en meta; arranca solo con 1ª puesta")
        return True


def run(args: argparse.Namespace) -> int:
    stage_id = args.stage or read_saved_stage(DEFAULT_LEARN_STAGE)
    speed_band = args.speed_band if args.speed_band > 0 else read_saved_speed_band()
    ramp: Optional[RampGate] = None
    ramp_state = ""
    if getattr(args, "ramp", False):
        ramp_state = args.ramp_state or f"{args.buffer}.ramp.json"
        ramp = RampGate.load(ramp_state)
        if ramp is None:
            ramp = RampGate(bands=bands_from(speed_band, args.ramp_ceiling, args.ramp_step))
        else:
            ramp.restart_cycle()
            print(f"[Learn] Rampa retomada de {ramp_state}: banda {ramp.band:g} km/h (se ignora --speed-band); "
                  f"{ramp.clean_cycles} ciclo(s) limpio(s) y {ramp.dirty_cycles} sucio(s) seguidos")
        speed_band = ramp.band
        args.learn_every = ramp.cycle_laps  # salida + vueltas lanzadas, y ajuste en meta tras cada ciclo
    ref = ReferenceLine.load(args.reference)
    stage = get_learn_stage(stage_id)
    effective_speed = resolve_learn_speed(stage_id, speed_band, args.speed_target)
    teacher = TeachingController(ref, TeacherConfig(
        speed_target_kmh=effective_speed, lat_accel_limit=args.lat_accel_limit or None,
        ff_speed_gain=float(getattr(args, "steer_ff_gain", 0.0) or 0.0),
        ff_speed_cap_kmh=float(getattr(args, "steer_ff_cap_kmh", 0.0) or 0.0),
        pedal_technique=bool(getattr(args, "pedal_technique", False)),
        brake_profile=bool(getattr(args, "brake_profile", False)),
        brake_circle=float(getattr(args, "brake_circle", 14.6) or 14.6),
        exit_circle=float(getattr(args, "exit_circle", 0.0) or 0.0),
        profile_peak_min_m=float(getattr(args, "profile_peak_min_m", 0.0) or 0.0),
        profile_peak_min_kmh=float(getattr(args, "profile_peak_min_kmh", 0.0) or 0.0),
        exit_slew_per_s=float(getattr(args, "pedal_exit_slew", 1.5) or 1.5),
        slip_steer_gain=float(getattr(args, "steer_slip_gain", 0.0) or 0.0),
        lat_gain_v0_kmh=float(getattr(args, "lat_gain_v0_kmh", 0.0) or 0.0),
        steer_preview_s=float(getattr(args, "steer_preview_s", 0.0) or 0.0),
        throttle_max=float(getattr(args, "throttle_max", 0.85) or 0.85),
        brake_decel_straight=float(getattr(args, "brake_decel_straight", 0.0) or 0.0),
        brake_overspeed_straight_ms=float(getattr(args, "brake_overspeed_straight_ms", 8.0) or 8.0),
        **({"ff_speed_v0_kmh": float(args.steer_ff_v0_kmh)} if getattr(args, "steer_ff_v0_kmh", -1.0) >= 0.0 else {}),
        max_gear=int(getattr(args, "max_gear", TEACHING_MAX_GEAR) or TEACHING_MAX_GEAR),
    ))
    lat_adapter: Optional[LatAdapter] = None
    if getattr(args, "lat_adapt", False):
        if not args.lat_accel_limit:
            raise SystemExit("--lat-adapt necesita --lat-accel-limit")
        curvas_json = Path(args.reference).with_name("curvas.json")
        if not curvas_json.is_file():
            raise SystemExit(f"--lat-adapt necesita el catálogo de curvas junto a la referencia: {curvas_json}")
        if getattr(args, "lat_adapt_fixed", False) and not getattr(args, "lat_adapt_load", ""):
            raise SystemExit("--lat-adapt-fixed necesita --lat-adapt-load")
        lat_adapter = LatAdapter.from_curvas_json(
            curvas_json, base_limit=float(args.lat_accel_limit), track_length=float(ref.track_length),
            config=LatAdaptConfig(max_scale=float(args.lat_adapt_max_scale), learn=not getattr(args, "lat_adapt_fixed", False)),
            cap_limit=float(args.lat_adapt_cap),
        )
        if getattr(args, "lat_adapt_load", ""):
            try:
                lat_adapter.load_prior(load_map(Path(args.lat_adapt_load)))
            except (OSError, ValueError) as exc:
                raise SystemExit(f"--lat-adapt-load: no puedo leer el mapa {args.lat_adapt_load}: {exc}") from exc
            print(f"[Learn] --lat-adapt-load: mapa {args.lat_adapt_load} (se aplica al llegar las condiciones de hoy; si no son compatibles se ignora)"
                  + (" · mapa fijo: no aprende" if getattr(args, "lat_adapt_fixed", False) else ""))
        print(f"[Learn] --lat-adapt: límite lateral por curva, base {args.lat_accel_limit:g} m/s², multiplicador {lat_adapter.cfg.min_scale:g}-{lat_adapter.max_scale:g}, "
              f"tope {args.lat_adapt_cap:g} m/s² (el ajuste va en la vuelta siguiente)")
    exit_adapter: Optional[ExitAdapter] = None
    if getattr(args, "exit_adapt", False):
        if not float(getattr(args, "exit_circle", 0.0) or 0.0) or not getattr(args, "pedal_technique", False):
            raise SystemExit("--exit-adapt necesita --exit-circle y --pedal-technique")
        curvas_json = Path(args.reference).with_name("curvas.json")
        if not curvas_json.is_file():
            raise SystemExit(f"--exit-adapt necesita el catálogo de curvas junto a la referencia: {curvas_json}")
        if getattr(args, "exit_adapt_fixed", False) and not getattr(args, "exit_adapt_load", ""):
            raise SystemExit("--exit-adapt-fixed necesita --exit-adapt-load")
        exit_adapter = ExitAdapter.from_curvas_json(
            curvas_json, base_limit=float(args.exit_circle), track_length=float(ref.track_length),
            config=ExitAdaptConfig(max_scale=float(args.exit_adapt_max_scale), learn=not getattr(args, "exit_adapt_fixed", False)),
        )
        if getattr(args, "exit_adapt_load", ""):
            try:
                exit_adapter.load_prior(load_map(Path(args.exit_adapt_load)))
            except (OSError, ValueError) as exc:
                raise SystemExit(f"--exit-adapt-load: no puedo leer el mapa {args.exit_adapt_load}: {exc}") from exc
            print(f"[Learn] --exit-adapt-load: mapa {args.exit_adapt_load} (se aplica al llegar las condiciones de hoy; si no son compatibles se ignora)"
                  + (" · mapa fijo: no aprende" if getattr(args, "exit_adapt_fixed", False) else ""))
        print(f"[Learn] --exit-adapt: radio del círculo de salida por curva, base {args.exit_circle:g}, multiplicador {exit_adapter.cfg.min_scale:g}-{exit_adapter.max_scale:g} (el ajuste va en la vuelta siguiente)")
    exit_started = False
    exit_save_path = str(getattr(args, "exit_adapt_save", "") or "")
    brake_adapter: Optional[BrakeAdapter] = None
    if getattr(args, "brake_adapt", False):
        if not float(getattr(args, "brake_decel_straight", 0.0) or 0.0) or not getattr(args, "brake_profile", False) or not getattr(args, "pedal_technique", False):
            raise SystemExit("--brake-adapt necesita --brake-decel-straight, --brake-profile y --pedal-technique")
        curvas_json = Path(args.reference).with_name("curvas.json")
        if not curvas_json.is_file():
            raise SystemExit(f"--brake-adapt necesita el catálogo de curvas junto a la referencia: {curvas_json}")
        if getattr(args, "brake_adapt_fixed", False) and not getattr(args, "brake_adapt_load", ""):
            raise SystemExit("--brake-adapt-fixed necesita --brake-adapt-load")
        brake_adapter = BrakeAdapter.from_curvas_json(
            curvas_json, base_limit=float(args.brake_decel_straight), track_length=float(ref.track_length),
            config=BrakeAdaptConfig(max_scale=float(args.brake_adapt_max_scale), learn=not getattr(args, "brake_adapt_fixed", False)),
        )
        if getattr(args, "brake_adapt_load", ""):
            try:
                brake_adapter.load_prior(load_map(Path(args.brake_adapt_load)))
            except (OSError, ValueError) as exc:
                raise SystemExit(f"--brake-adapt-load: no puedo leer el mapa {args.brake_adapt_load}: {exc}") from exc
            print(f"[Learn] --brake-adapt-load: mapa {args.brake_adapt_load} (se aplica al llegar las condiciones de hoy; si no son compatibles se ignora)"
                  + (" · mapa fijo: no aprende" if getattr(args, "brake_adapt_fixed", False) else ""))
        print(f"[Learn] --brake-adapt: deceleración de frenada por curva, base {args.brake_decel_straight:g} m/s², multiplicador {brake_adapter.cfg.min_scale:g}-{brake_adapter.max_scale:g} (el ajuste va en la vuelta siguiente)")
    brake_started = False
    brake_save_path = str(getattr(args, "brake_adapt_save", "") or "")
    adapt_started = False  # el mapa cargado y las condiciones de salida se fijan en el primer tick con las condiciones conocidas
    adapt_save_path = str(getattr(args, "lat_adapt_save", "") or "")
    safety = SafetyMonitor(ref=ref, surface_profile=ns_str(args, "safety_profile"))
    brake_slip_limit = float(getattr(args, "brake_slip_limit", 0.0) or 0.0)
    brake_slip_hold = float(getattr(args, "brake_slip_hold", 0.0) or 0.0)
    brake_slip = BrakeSlipLimiter(BrakeSlipConfig(limit=brake_slip_limit, hold_frac=brake_slip_hold)) if brake_slip_limit > 0.0 else None
    if brake_slip is not None:
        print(f"[Learn] Limitador de frenada por deslizamiento: objetivo {brake_slip_limit:g} (1 − rps delanteras / rps traseras)"
              + (f", memoria del pedal límite al {brake_slip_hold:g}" if brake_slip_hold > 0.0 else ""))
    session = DriveSession()
    perturb_every = float(getattr(args, "perturb_every", 0.0) or 0.0)
    perturber = (
        SpeedPerturber(perturb_every, float(getattr(args, "perturb_drop_kmh", 4.5)))
        if perturb_every > 0 else None
    )
    ident_kind = str(getattr(args, "ident", "") or "")
    ident: Optional[IdentManeuver] = None
    arc: Optional[ArcRamp] = None
    if ident_kind == "arco":
        try:
            win = [float(w) for w in str(args.ident_arc_window).split(",")]
            arc = ArcRamp(
                [float(v) for v in str(args.ident_arc_speeds).split(",") if v.strip()], win[0], win[1], ref.track_length,
                band_kmh=effective_speed, cte_limit_m=float(args.ident_arc_cte), heading_limit_rad=float(args.ident_arc_heading),
                decay_kmh_s=float(args.ident_arc_decay),
            )
        except (ValueError, IndexError) as exc:
            print(f"[Learn] --ident arco: {exc}")
            return 1
        print(f"[Learn] Identificación A1.3 (arcos): ventana {win[0]:.0f}-{win[1]:.0f} m, velocidades "
              f"{', '.join(f'{v:g}' for v in arc.speeds)} km/h, corte por |CTE| > {arc.cte_limit_m:g} m, rumbo > "
              f"{arc.heading_limit_rad:g} rad o rueda fuera del asfalto")
    elif ident_kind:
        all_straights = find_straights(ref.curvature, ref.track_length)
        print("[Learn] Rectas de la pista: " + ", ".join(
            f"{i}: {a:.0f}-{b:.0f} m" for i, (a, b) in enumerate(all_straights)))
        try:
            chosen = select_straights(all_straights, str(getattr(args, "ident_straights", "") or ""))
        except ValueError as exc:
            print(f"[Learn] --ident-straights: {exc}")
            return 1
        try:
            ident = IdentManeuver(
                ident_kind, chosen, ref.track_length,
                cap_kmh=float(args.ident_cap_kmh), floor_kmh=float(args.ident_floor_kmh),
                end_margin_m=float(args.ident_end_margin_m),
                caps_kmh=[float(c) for c in str(args.ident_caps).split(",") if c.strip()] if args.ident_caps else None,
                max_gear=teacher.config.max_gear,
            )
        except ValueError as exc:
            print(f"[Learn] --ident: {exc}")
            return 1
        if not ident.windows:
            print("[Learn] --ident: la pista no tiene rectas largas para la maniobra")
            return 1
        print(f"[Learn] Identificación A1 ({ident_kind}): {len(ident.windows)} recta(s) de "
              f"{', '.join(f'{span:.0f} m' for _, span in ident.windows)}")

    model: Optional[UniversalPolicy] = None
    if os.path.isfile(args.model):
        model = load_universal_policy(args.model)
    else:
        print(f"[Learn] Modelo no encontrado ({args.model}) — se creará en el primer fine-tune")

    buffer_rec = DatasetRecorder(output_path=args.buffer, origin=ORIGIN_TEACHER)
    buffer_rec.open()

    experiment = ns_str(args, "experiment") if hasattr(args, "experiment") else ""
    log_path = args.session_log or str(
        default_log_path(ref.track_name or "sugo", stage.id, category="learning"),
    )
    session_rec = TeachingSessionRecorder.open(log_path, {
        "mode": "learn",
        "phase": stage.id,
        "phase_label": stage.label,
        "track": ref.track_name or "sugo",
        "reference": args.reference,
        "speed_target_kmh": effective_speed,
        "speed_band_kmh": speed_band,
        "stage_speed_kmh": stage.speed_target_kmh,
        "speed_override_kmh": args.speed_target if args.speed_target > 0 else None,
        "model": args.model,
        "learn_every": args.learn_every,
        "reference_lap_s": round(ref.lap_time, 3) if ref.lap_time else None,
        "origin": "experimental" if experiment else "main",
        "experiment": experiment or None,
        "ramp": ramp.to_dict() if ramp is not None else None,
    })

    if ramp is not None:
        print(f"[Learn] Rampa {ramp.bands[0]:g} -> {ramp.bands[-1]:g} km/h | ciclo: salida + {ramp.laps_per_cycle} lanzadas | "
              f"estado: {ramp_state}")
    if args.speed_target > 0:
        speed_note = f"{effective_speed:.0f} km/h (override fino)"
    else:
        speed_note = f"banda {speed_band:.0f} km/h"
    if args.stage is None:
        print(f"[Learn] Etapa guardada: {stage_id}")
    if args.speed_band <= 0:
        print(f"[Learn] Banda guardada: {speed_band:.0f} km/h")
    print(f"[Learn] Etapa: {stage.label} @ {speed_note}")
    print(f"[Learn] Fine-tune cada {args.learn_every} vuelta(s) | Buffer: {args.buffer}")
    print(f"[Learn] Safety superficie: {ns_str(args, 'safety_profile')}")
    print(f"[Learn] Session log: {log_path}")
    print("[Learn] Esperando telemetría UDP...")

    if not session.wait_for_telemetry():
        print("[Error] Sin telemetría UDP.")
        return 1

    controller = DS4Controller(mode=args.gamepad, steer_comp=args.steer_comp)
    shifter = AutoShifter(neutral_retry_s=NEUTRAL_RETRY_COOLDOWN_S, max_gear=teacher.config.max_gear)
    start_lap = session.last_timings.current_lap if session.last_timings else 0
    lap_completion = LapCompletionTracker()
    laps_done = 0
    laps_since_learn = 0
    override_count = 0
    lap_ticks: List[dict] = []
    frame = 0
    prog = LearnProgress(stage_id=stage_id, speed_band=speed_band)
    lap_guard = LapTransitionGuard(track_length=ref.track_length)
    cte_guard = SustainedCteGuard()
    stuck_abort = StuckOffTrackAbort()
    tuner = BackgroundFineTuner(
        args, prog, lap_guard, model, ref.track_name or "",
    )
    lap_summary_rows: List[dict] = []

    def _persist_progress() -> None:
        save_learn_progress(
            stage_id=prog.stage_id,
            reference=args.reference,
            speed_target_kmh=args.speed_target,
            speed_band_kmh=prog.speed_band,
        )

    safety.reset(
        lap_distance=session.last_timings.lap_distance if session.last_timings else 0.0,
        current_lap=start_lap,
    )

    maybe_engage_first_gear(
        controller, shifter,
        lambda: session.last_telem,
        session.sync_physics_frame,
        args.auto_shift,
        "Learn",
    )

    if tuner.model is None and os.path.isfile(args.base_dataset):
        print("[Learn] Sin modelo — entrenamiento inicial desde dataset base...")
        lap_guard.set_fine_tuning(True)
        try:
            tuner.run_sync()
        finally:
            lap_guard.set_fine_tuning(False)

    _init_dist = session.last_timings.lap_distance if session.last_timings else 0.0
    lap_guard.reset(start_lap, _init_dist)
    print_session_lap_board(lap_summary_rows)
    lap_completion.reset(start_lap, _init_dist)
    last_conditions: Optional[dict] = None
    last_compound: Optional[list] = None
    damage_watch = DamageWatch(limit_pct=args.damage_limit, jump_pct=args.damage_jump)
    base_lat_limit = teacher.config.lat_accel_limit
    arc_closing = False
    arc_prev = (0.0, 0.0, False, False)  # CTE, rumbo, fuera de asfalto y control tomado, del tick anterior (este aún no está decidido)

    try:
        while True:
            if not session.sync_physics_frame():
                continue
            if session.last_telem is None or session.last_timings is None:
                continue

            telem = session.last_telem
            timings = session.last_timings
            frame += 1

            tune_done = (
                lap_guard.fine_tuning
                and tuner.finished
            )
            if tune_done and telem.gear == 1:
                if prog.goal_reached:
                    print("[Learn] Objetivo cumplido — 1ª puesta, cerrando sesión")
                    break
                lap_guard.set_fine_tuning(False)
                print("[Learn] Fine-tune terminado — 1ª puesta, el BC vuelve a conducir")

            stage = get_learn_stage(prog.stage_id)
            teacher.config.speed_target_kmh = resolve_learn_speed(
                prog.stage_id, prog.speed_band, args.speed_target,
            )
            arc_dec = None
            if arc is not None:
                arc_dec = arc.update(
                    timings.lap_distance, telem.speed, arc_prev[0], arc_prev[1], arc_prev[2], session_rec.elapsed_s(),
                    allowed=not lap_guard.active and not arc_prev[3] and (telem.gear == 0 or is_forward_gear(telem)),
                )
                if arc_dec.event is not None:
                    session_rec.record_event(arc_dec.event)
                    if arc_dec.event["phase"] == "end":
                        verdict = "limpia" if arc_dec.event["result"] == "clean" else f"LÍMITE ({arc_dec.event['reason']})"
                        print(f"[Learn] Arco a {arc_dec.event['target_kmh']:g} km/h: {verdict}")
                if arc_dec.target_kmh is not None:
                    teacher.config.speed_target_kmh = arc_dec.target_kmh
                    teacher.config.lat_accel_limit = FREE_LATERAL_MS2
                else:
                    teacher.config.lat_accel_limit = base_lat_limit
                if arc.finished and not arc_closing:
                    arc_closing = True
                    args.max_laps = laps_done + 1 if args.max_laps <= 0 else min(args.max_laps, laps_done + 1)
                    why = arc.limit_reason or "todas las velocidades hechas"
                    print(f"[Learn] A1.3: fin de la rampa ({why}); la sesión se cierra al terminar esta vuelta")

            status = safety.update(telem, timings)
            if lap_guard.active:
                # El fine-tune mantiene el coche frenado a propósito: no cuenta como atasco.
                safety.hold(timings)
            decision = resolve_teacher_decision(teacher, telem, timings, safety, status)
            if stuck_abort.update(decision.cte, telem.speed):
                print(
                    f"[Learn] Coche parado a {abs(decision.cte):.0f} m de la línea más de "
                    f"{stuck_abort.hold_s:.0f} s (¿muro?) — cierro la sesión; "
                    "reinicia el coche y vuelve a lanzar."
                )
                break
            teacher_tuple = decision.as_tuple()
            reason = decision.reason
            obs_record = build_obs_universal(telem, timings, ref, teacher.speed_target_ms)
            lap_guard.on_frame(timings.current_lap, timings.lap_distance)

            if tuner.model is not None and not lap_guard.active and not args.teacher_only:
                with tuner.lock:
                    bc_action, _ = tuner.model.predict(obs_record, reason=reason)
                bc_tuple = decode_action(bc_action)
            else:
                bc_tuple = teacher_tuple

            override = decision.safety_override
            proposed, drive_source, ovr_inc = choose_bc_drive_pedals(
                bc_tuple, teacher_tuple, telem, override, lap_guard.active,
            )
            cte_takeover = (
                cte_guard.update(decision.cte, telem.speed, decision.heading_err)
                and not override
                and not lap_guard.active
            )
            if cte_takeover:
                proposed, drive_source, ovr_inc = teacher_tuple, "teacher:cte", True
            if args.teacher_only and drive_source == "bc":
                proposed, drive_source = teacher_tuple, "teacher:only"
            if ovr_inc:
                override_count += 1
            if drive_source == "bc" and not lap_guard.active:
                proposed = damp_bc_steering(proposed, telem.speed, args.steer_damp_kmh / 3.6)
            if not lap_guard.active and not override and not cte_takeover:
                proposed, capped = cap_bc_to_speed_target(
                    proposed, telem.speed, teacher.speed_target_ms,
                    soft=teacher.config.lat_accel_limit is not None,
                )
                if capped:
                    drive_source = "teacher:speed"

            if perturber is not None and perturber.update(
                timings.lap_distance, telem.speed, teacher.speed_target_ms, session_rec.elapsed_s(),
                allowed=not (lap_guard.active or override or cte_takeover or ovr_inc) and is_forward_gear(telem),
            ):
                proposed, drive_source = (0.0, 0.0, proposed[2]), "perturb:coast"

            if ident is not None:
                imposed = ident.update(
                    timings.lap_distance, telem.speed, decision.cte, session_rec.elapsed_s(),
                    allowed=not (lap_guard.active or override or cte_takeover or ovr_inc)
                    and (telem.gear == 0 or is_forward_gear(telem)),  # marcha atrás = 15 en el UDP
                    neutral=telem.gear == 0,  # el AutoShifter pasa ≈ 0,2 s por punto muerto en cada cambio
                )
                if imposed is not None:
                    proposed, drive_source = (imposed[0], imposed[1], proposed[2]), ident.drive_source

            settle = lap_guard.apply(
                teacher_tuple, proposed, speed_ms=telem.speed, gear=telem.gear,
            )
            if settle.active:
                final = (settle.throttle, settle.brake, settle.steering)
                drive_source = f"settle:{settle.reason}"
            else:
                final = proposed

            if arc_dec is not None and arc_dec.tag:
                drive_source = arc_dec.tag  # los ticks de la pasada salen con su etiqueta y no entran en el buffer

            if brake_slip is not None:
                final = (final[0], brake_slip.apply(final[1], telem.tyre_rps), final[2])  # V43: el pedal que sale al juego ya va limitado

            if drive_source in ("bc", "teacher:speed", "perturb:coast") or drive_source.startswith("ident:"):
                teacher.track_applied_pedals(final[0], final[1])  # anti-windup: el PI no integra lo que el BC no sigue

            controller.apply_action(*final)
            shift_event = None
            if args.auto_shift:
                shift_event = auto_shift(controller, telem, final[0], final[1], shifter)

            if not lap_guard.active and not is_poor_demo(reason) and not drive_source.startswith("ident:"):
                buffer_rec.maybe_record(
                    obs=obs_record,
                    action=encoded_action_tuple(*teacher_tuple),
                    lap_distance=timings.lap_distance,
                    cte=decision.cte,
                    heading_err=decision.heading_err,
                    teacher_reason=reason,
                    safety=override,
                    confidence=1.0,
                    obs_schema=OBS_SCHEMA,
                    track_name=ref.track_name or "",
                    learn_stage=prog.stage_id,
                    speed_band_kmh=prog.speed_band,
                )

            flags = lap_tick_safety_flags(status, decision.cte, lap_guard.active)
            arc_prev = (decision.cte, decision.heading_err, bool(flags.off_surface or flags.off_track), bool(override or cte_takeover))
            lap_override = (override or cte_takeover) if not lap_guard.active else False
            lap_ticks.append(make_lap_buffer_tick(
                session_rec.elapsed_s(),
                telem.speed * 3.6,
                decision.cte,
                lap_override,
                flags.off_track,
                flags.stuck,
                reason,
                settling=lap_guard.active,
                off_surface=flags.off_surface,
                off_track_cte=flags.off_track_cte,
                throttle=final[0],
                brake=final[1],
                straight=teacher.free_straight(timings.lap_distance),
            ))

            track_diag = maybe_build_track_diag(
                args.diag_track, telem, timings, ref, decision.signed_cte,
            )
            session_rec.record_tick(
                telem_speed_kmh=telem.speed * 3.6,
                lap=timings.current_lap,
                lap_distance=timings.lap_distance,
                cte=decision.cte,
                signed_cte=decision.signed_cte,
                heading_err=decision.heading_err,
                throttle=final[0],
                brake=final[1],
                steering=final[2],
                teacher_reason=reason,
                rule=rule_for_reason(reason),
                drive_source=drive_source,
                learn_stage=prog.stage_id,
                safety_override=override,
                off_track=flags.off_track,
                off_surface=flags.off_surface,
                off_track_cte=flags.off_track_cte,
                stuck=flags.stuck,
                gear=telem.gear,
                num_gears=telem.num_gears,
                rpm=telem.rpm,
                shift_event=shift_event,
                track_diag=track_diag,
                vehicle={**vehicle_diag(telem), **(brake_slip.diag() if brake_slip is not None else {})},
                timing=timing_diag(timings),
            )
            if lat_adapter is not None and not adapt_started:
                game_state_now = session.game_state
                if game_state_now is not None or session_rec.elapsed_s() >= 30.0:  # el paquete del tiempo llega cada ~10 s
                    adapt_started = True
                    cond = conditions_diag(game_state_now) or {}
                    tyres_now = list(getattr(telem, "tyre_temp", None) or ())
                    compound_now = compound_diag(telem)
                    now_cond = {"rain": cond.get("rain", 0), "track_c": cond.get("track_c"), "ambient_c": cond.get("ambient_c"),
                                "tyre_start_c": round(sum(tyres_now) / len(tyres_now), 1) if tyres_now else None,
                                "compound": "/".join(compound_now) if compound_now else None}
                    start_info = lat_adapter.start(now_cond)
                    session_rec.record_event({"type": "lat_adapt_start", "conditions": now_cond, **(start_info or {"applied": False, "reason": "sin mapa cargado"})})
                    if start_info is not None and start_info["applied"]:
                        teacher.set_lat_scales(lat_adapter.scales_per_m(int(ref.track_length)))
                        print(f"[Learn] --lat-adapt-load: mapa aplicado, desajuste de condiciones {start_info['mismatch']:g} (pista {start_info['mismatch_track']:g}, gomas {start_info['mismatch_tyre']:g}; 0 = iguales, 1 = recorta el margen entero) | límites m/s²: "
                              + " ".join(f"C{k}={v:g}" for k, v in lat_adapter.limits().items()))
                    elif start_info is not None:
                        print(f"[Learn] --lat-adapt-load: mapa IGNORADO ({start_info['reason']}); sigo con el ajuste desde 1,0")
            if brake_adapter is not None and not brake_started:
                game_state_now = session.game_state
                if game_state_now is not None or session_rec.elapsed_s() >= 30.0:
                    brake_started = True
                    cond = conditions_diag(game_state_now) or {}
                    tyres_now = list(getattr(telem, "tyre_temp", None) or ())
                    compound_now = compound_diag(telem)
                    now_cond = {"rain": cond.get("rain", 0), "track_c": cond.get("track_c"), "ambient_c": cond.get("ambient_c"),
                                "tyre_start_c": round(sum(tyres_now) / len(tyres_now), 1) if tyres_now else None,
                                "compound": "/".join(compound_now) if compound_now else None}
                    start_info = brake_adapter.start(now_cond)
                    session_rec.record_event({"type": "brake_adapt_start", "conditions": now_cond, **(start_info or {"applied": False, "reason": "sin mapa cargado"})})
                    if start_info is not None and start_info["applied"]:
                        teacher.set_brake_scales(brake_adapter.scales_per_m(int(ref.track_length)))
                        print(f"[Learn] --brake-adapt-load: mapa aplicado, desajuste de condiciones {start_info['mismatch']:g} | deceleraciones m/s²: "
                              + " ".join(f"C{k}={v:g}" for k, v in brake_adapter.limits().items()))
                    elif start_info is not None:
                        print(f"[Learn] --brake-adapt-load: mapa IGNORADO ({start_info['reason']}); sigo con el ajuste desde 1,0")
            if brake_adapter is not None:
                tyres_tick = telem.tyre_temp
                brake_upd = brake_adapter.observe(
                    timings.current_lap, timings.lap_distance, decision.signed_cte,
                    telem.local_velocity[0], telem.local_velocity[2], flags.off_surface,
                    tyre_c=(sum(tyres_tick) / len(tyres_tick)) if tyres_tick else None,
                    braking=teacher.entry_phase, pedal=final[1], limiter_scale=(brake_slip.scale if brake_slip is not None else 1.0),
                    over_ms=telem.speed - teacher.profile_at(timings.lap_distance),
                )
                if brake_upd is not None:
                    teacher.set_brake_scales(brake_adapter.scales_per_m(int(ref.track_length)))
                    session_rec.record_event({"type": "brake_adapt", **brake_upd})
                    if brake_save_path and brake_adapter.cfg.learn and brake_adapter.clean_tail():
                        save_map(Path(brake_save_path), brake_adapter.snapshot({"experiment": str(getattr(args, "experiment", "") or ""), "lap": brake_upd["lap"]}))
                        print(f"[Learn] --brake-adapt-save: mapa guardado en {brake_save_path} (vuelta {brake_upd['lap']}, dos últimas limpias)")
                    cambios = {k: v for k, v in brake_upd["decisions"].items() if v in ("sube", "baja")}
                    print(f"[Learn] --brake-adapt, vuelta {brake_upd['lap']}: " + (", ".join(f"C{k} {v}" for k, v in cambios.items()) or "sin cambios")
                          + " | deceleraciones m/s²: " + " ".join(f"C{k}={v:g}" for k, v in brake_adapter.limits().items()))
            if exit_adapter is not None and not exit_started:
                game_state_now = session.game_state
                if game_state_now is not None or session_rec.elapsed_s() >= 30.0:
                    exit_started = True
                    cond = conditions_diag(game_state_now) or {}
                    tyres_now = list(getattr(telem, "tyre_temp", None) or ())
                    compound_now = compound_diag(telem)
                    now_cond = {"rain": cond.get("rain", 0), "track_c": cond.get("track_c"), "ambient_c": cond.get("ambient_c"),
                                "tyre_start_c": round(sum(tyres_now) / len(tyres_now), 1) if tyres_now else None,
                                "compound": "/".join(compound_now) if compound_now else None}
                    start_info = exit_adapter.start(now_cond)
                    session_rec.record_event({"type": "exit_adapt_start", "conditions": now_cond, **(start_info or {"applied": False, "reason": "sin mapa cargado"})})
                    if start_info is not None and start_info["applied"]:
                        teacher.set_exit_scales(exit_adapter.scales_per_m(int(ref.track_length)))
                        print(f"[Learn] --exit-adapt-load: mapa aplicado, desajuste de condiciones {start_info['mismatch']:g} | radios: "
                              + " ".join(f"C{k}={v:g}" for k, v in exit_adapter.limits().items()))
                    elif start_info is not None:
                        print(f"[Learn] --exit-adapt-load: mapa IGNORADO ({start_info['reason']}); sigo con el ajuste desde 1,0")
            if exit_adapter is not None:
                tyres_tick = telem.tyre_temp
                rps_tick = telem.tyre_rps
                exit_upd = exit_adapter.observe(
                    timings.current_lap, timings.lap_distance, decision.signed_cte,
                    telem.local_velocity[0], telem.local_velocity[2], flags.off_surface,
                    tyre_c=(sum(tyres_tick) / len(tyres_tick)) if tyres_tick else None,
                    exit_phase=teacher.exit_phase, cap_bound=teacher.exit_bound, throttle=final[0],
                    rps_front=(abs(rps_tick[0]) + abs(rps_tick[1])) / 2.0, rps_rear=(abs(rps_tick[2]) + abs(rps_tick[3])) / 2.0,
                )
                if exit_upd is not None:
                    teacher.set_exit_scales(exit_adapter.scales_per_m(int(ref.track_length)))
                    session_rec.record_event({"type": "exit_adapt", **exit_upd})
                    if exit_save_path and exit_adapter.cfg.learn and exit_adapter.clean_tail():
                        save_map(Path(exit_save_path), exit_adapter.snapshot({"experiment": str(getattr(args, "experiment", "") or ""), "lap": exit_upd["lap"]}))
                        print(f"[Learn] --exit-adapt-save: mapa guardado en {exit_save_path} (vuelta {exit_upd['lap']}, dos últimas limpias)")
                    cambios = {k: v for k, v in exit_upd["decisions"].items() if v in ("sube", "baja")}
                    print(f"[Learn] --exit-adapt, vuelta {exit_upd['lap']}: " + (", ".join(f"C{k} {v}" for k, v in cambios.items()) or "sin cambios")
                          + " | radios: " + " ".join(f"C{k}={v:g}" for k, v in exit_adapter.limits().items()))
            if lat_adapter is not None:
                tyres_tick = telem.tyre_temp
                adapt = lat_adapter.observe(
                    timings.current_lap, timings.lap_distance, decision.signed_cte,
                    telem.local_velocity[0], telem.local_velocity[2], flags.off_surface,
                    tyre_c=(sum(tyres_tick) / len(tyres_tick)) if tyres_tick else None,
                )
                if adapt is not None:
                    teacher.set_lat_scales(lat_adapter.scales_per_m(int(ref.track_length)))
                    session_rec.record_event({"type": "lat_adapt", **adapt})
                    if adapt_save_path and lat_adapter.cfg.learn and lat_adapter.clean_tail():
                        save_map(Path(adapt_save_path), lat_adapter.snapshot({"experiment": str(getattr(args, "experiment", "") or ""), "lap": adapt["lap"]}))
                        print(f"[Learn] --lat-adapt-save: mapa guardado en {adapt_save_path} (vuelta {adapt['lap']}, dos últimas limpias)")
                    changed = {k: v for k, v in adapt["decisions"].items() if v in ("sube", "baja")}
                    print(f"[Learn] --lat-adapt, vuelta {adapt['lap']}: " + (", ".join(f"C{k} {v}" for k, v in changed.items()) or "sin cambios")
                          + " | límites m/s²: " + " ".join(f"C{k}={v:g}" for k, v in lat_adapter.limits().items()))
            conditions = conditions_diag(session.game_state)
            if conditions is not None and conditions != last_conditions:
                session_rec.record_event({"type": "conditions", **conditions})  # llega cada ~10 s; solo si cambia
                last_conditions = conditions
            compound = compound_diag(telem)
            if compound is not None and compound != last_compound:  # solo si cambia: el nombre del compuesto de cada rueda (lisos / lluvia)
                session_rec.record_event({"type": "tyre_compound", "compound": compound})
                last_compound = compound
            game_state = session.game_state
            if game_state is not None and rain_over_limit(game_state, args.rain_limit):
                session_rec.record_event({"type": "rain_stop", "rain": int(game_state.rain_density),
                                          "limit": args.rain_limit})
                print(f"[Learn] --rain-limit: lluvia {game_state.rain_density} >= {args.rain_limit}; cierro la sesión.")
                break
            damage = damage_watch.update(telem, timings.lap_distance)
            if damage is not None:
                session_rec.record_event(damage)
                print(f"[Learn] Daño: {sorted(damage['changed'])} a {damage['context']['speed_kmh']} km/h")
                if args.stop_on_damage and damage["stop"]:
                    print(f"[Learn] --stop-on-damage ({sorted(damage['stop_reasons'])}): cierro la sesión; "
                          "repara o reinicia el coche antes de repetir.")
                    break

            if frame % args.log_every == 0:
                print(
                    f"  f={frame} | {telem.speed * 3.6:5.1f} km/h | "
                    f"CTE={decision.cte:4.1f}m | {prog.stage_id}@{prog.speed_band:.0f} | "
                    f"src={drive_source} | ovr={override_count}"
                )

            lap_result = process_lap_rollover(
                lap_ticks, timings.current_lap, timings.lap_distance,
                lap_completion, prog.stage_id, session_rec,
                speed_band_kmh=prog.speed_band,
            )
            if lap_result is not None:
                laps_done = lap_completion.laps_done
                lap_eval = lap_result.lap_eval
                prog.record_lap(lap_result.clean)

                print(
                    f"[Learn] Vuelta {laps_done} | {format_lap_time(lap_result.lap_time_s)} | "
                    f"{lap_eval['summary']} | CTE={lap_eval['avg_cte']}m | "
                    f"ovr={lap_eval.get('pct_override', 0)}% | clean_streak={prog.clean_streak}"
                )
                lap_summary_rows.append(
                    lap_summary_row_from_result(lap_result, prog.clean_streak),
                )
                print_session_lap_board(lap_summary_rows)

                lap_ticks = rotate_lap_buffer(lap_ticks)

                if ramp is not None:
                    advance_ramp(prog, ramp, lap_result.clean, lambda: ramp.save(ramp_state), _persist_progress)
                elif not (ident_kind or args.hold_stage):  # las sesiones de identificación (A1) y --hold-stage no avanzan el currículo: acaban por --max-laps o por la maniobra
                    advance_progress(prog, _persist_progress)

                laps_since_learn += 1
                teacher.reset()
                cte_guard.reset()

                if laps_since_learn >= args.learn_every:
                    if tuner.start_async():
                        laps_since_learn = 0

                if prog.goal_reached and not tuner.running and not (ident_kind or args.hold_stage):
                    print("[Learn] Objetivo cumplido — cerrando sesión")
                    break

                announce_autonomy(prog)

                if args.max_laps > 0 and laps_done >= args.max_laps:
                    break

    except KeyboardInterrupt:
        print("\n[Learn] Ctrl+C — guardando sesión y abriendo el informe...")
    finally:
        _persist_progress()
        controller.release()
        buffer_rec.close()
        session_rec.record_event({
            "type": "session_stats",
            "clean_streak": prog.clean_streak,
            "max_clean_streak": prog.max_clean_streak,
            "final_stage": prog.stage_id,
            "speed_band_kmh": prog.speed_band,
            "laps_completed": laps_done,
        })
        report = session_rec.finish(laps_completed=laps_done, open_browser=args.open_report)
        if report.get("html"):
            print(f"[Learn] Informe: {report['html']}")

    print(f"[Learn] Overrides totales: {override_count} | Buffer: {args.buffer}")
    return 0


def main() -> None:
    sys.exit(run(parse_args()))


if __name__ == "__main__":
    main()
