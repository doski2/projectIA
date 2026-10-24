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
from typing import Callable, List, Optional

from auto_shift import (
    NEUTRAL_RETRY_COOLDOWN_S,
    AutoShifter,
    auto_shift,
    maybe_engage_first_gear,
)
from pcars2_gear import cap_bc_to_speed_target, choose_bc_drive_pedals
from bc_training import fine_tune_universal
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
from obs_universal import OBS_SCHEMA, OBS_UNIVERSAL_DIM, build_obs_universal
from reference_recorder import ReferenceLine
from safety_monitor import SafetyMonitor
from session_log import TeachingSessionRecorder, default_log_path, vehicle_diag
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
    parser.add_argument("--gamepad", choices=["xbox", "ds4"], default="xbox")
    parser.add_argument("--log-every", type=int, default=50)
    parser.add_argument("--session-log", default="")
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
) -> tuple:
    """Base teacher sin filtro; buffer online filtrado por etapa + banda + pista."""
    chunks = []
    if os.path.isfile(base_path):
        chunks.append(load_universal_dataset(base_path, min_quality=FINE_TUNE_MIN_QUALITY))
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
            self.track_name,
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
    ref = ReferenceLine.load(args.reference)
    stage = get_learn_stage(stage_id)
    effective_speed = resolve_learn_speed(stage_id, speed_band, args.speed_target)
    teacher = TeachingController(ref, TeacherConfig(speed_target_kmh=effective_speed))
    safety = SafetyMonitor(ref=ref, surface_profile=ns_str(args, "safety_profile"))
    session = DriveSession()

    model: Optional[UniversalPolicy] = None
    if os.path.isfile(args.model):
        model = load_universal_policy(args.model)
    else:
        print(f"[Learn] Modelo no encontrado ({args.model}) — se creará en el primer fine-tune")

    buffer_rec = DatasetRecorder(output_path=args.buffer, origin=ORIGIN_TEACHER)
    buffer_rec.open()

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
    })

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

    controller = DS4Controller(mode=args.gamepad)
    shifter = AutoShifter(neutral_retry_s=NEUTRAL_RETRY_COOLDOWN_S)
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

            status = safety.update(telem, timings)
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

            if tuner.model is not None and not lap_guard.active:
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
            if ovr_inc:
                override_count += 1
            if not lap_guard.active and not override and not cte_takeover:
                proposed, capped = cap_bc_to_speed_target(
                    proposed, telem.speed, teacher.speed_target_ms,
                )
                if capped:
                    drive_source = "teacher:speed"

            settle = lap_guard.apply(
                teacher_tuple, proposed, speed_ms=telem.speed, gear=telem.gear,
            )
            if settle.active:
                final = (settle.throttle, settle.brake, settle.steering)
                drive_source = f"settle:{settle.reason}"
            else:
                final = proposed

            controller.apply_action(*final)
            shift_event = None
            if args.auto_shift:
                shift_event = auto_shift(controller, telem, final[0], final[1], shifter)

            if not lap_guard.active and not is_poor_demo(reason):
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
                vehicle=vehicle_diag(telem),
            )

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

                advance_progress(prog, _persist_progress)

                laps_since_learn += 1
                teacher.reset()
                cte_guard.reset()

                if laps_since_learn >= args.learn_every:
                    if tuner.start_async():
                        laps_since_learn = 0

                if prog.goal_reached and not tuner.running:
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
