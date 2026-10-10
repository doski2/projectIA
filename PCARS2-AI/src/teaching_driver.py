"""
teaching_driver.py
Entry point del Teaching Driver: modos TEACHER y RECORD.

Uso:
    python teaching_driver.py --mode teacher --reference src/refs/sugo_ai.json
    python teaching_driver.py --mode record --reference src/refs/sugo_ai.json --output data/sugo_teacher.jsonl
"""

from __future__ import annotations

import argparse
import sys
from typing import List

from auto_shift import AutoShifter, auto_shift, maybe_engage_first_gear, rpm_ratio
from controller import DS4Controller
from dataset_recorder import ORIGIN_TEACHER, DatasetRecorder
from driver_cli import add_diag_track_arg, add_safety_profile_arg, ns_str
from drive_session import DriveSession
from lap_session import (
    LapCompletionTracker,
    make_lap_buffer_tick,
    process_lap_rollover,
    rotate_lap_buffer,
)
from lap_tracker import format_lap_time
from teaching_diag import TeachingDiagnostics
from obs_builder import build_obs, encoded_action_tuple
from obs_universal import OBS_SCHEMA, build_obs_universal
from reference_recorder import ReferenceLine
from safety_monitor import SafetyMonitor, session_tick_flags
from session_log import TeachingSessionRecorder, default_log_path
from teacher_intents import rule_for_reason
from teacher_controller import TeacherConfig, TeachingController, resolve_teacher_decision
from track_deviation import maybe_build_track_diag
from validation_phases import DEFAULT_PHASE, get_phase


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PCARS2-AI — Teaching Driver (reglas + grabación)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--mode", choices=["teacher", "record"], default="teacher",
                        help="teacher: solo reglas; record: reglas + dataset JSONL")
    parser.add_argument("--reference", "-r", required=True, help="JSON de línea de referencia")
    parser.add_argument("--output", "-o", default="", help="Ruta JSONL (modo record)")
    parser.add_argument("--speed-target", type=float, default=None, metavar="KMH",
                        help="Velocidad objetivo en km/h (default: la de la fase)")
    parser.add_argument("--gamepad", choices=["xbox", "ds4"], default="xbox")
    parser.add_argument("--max-laps", type=int, default=0, help="0 = sin límite")
    parser.add_argument("--log-every", type=int, default=50, help="Frames entre logs")
    parser.add_argument("--universal", action="store_true",
                        help="Grabar obs universal + intención (multi-pista)")
    parser.add_argument("--phase", default=DEFAULT_PHASE,
                        choices=["f1_linea", "f2_acelerar", "f3_frenar", "f4_combinado"],
                        help="Fase de validación Teaching (ver docs/VALIDACION_TEACHING_SUGO.md)")
    parser.add_argument("--session-log", default="",
                        help="Ruta JSONL de sesión (default: logs/teaching/...)")
    parser.add_argument("--open-report", action="store_true",
                        help="Abrir HTML al terminar la sesión")
    parser.add_argument("--auto-shift", action=argparse.BooleanOptionalAction, default=True,
                        help="Cambio automático de marchas (RB/LB)")
    add_safety_profile_arg(parser)
    add_diag_track_arg(parser)
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    ref = ReferenceLine.load(ns_str(args, "reference"))
    phase = get_phase(args.phase)
    speed_target = args.speed_target if args.speed_target is not None else phase.speed_target_kmh

    config = TeacherConfig(speed_target_kmh=speed_target)
    teacher = TeachingController(ref, config=config)
    safety = SafetyMonitor(ref=ref, surface_profile=ns_str(args, "safety_profile"))
    session = DriveSession()

    print(f"[Teacher] Referencia: {ref.track_name} ({ref.track_length:.0f} m)")
    schema = OBS_SCHEMA if args.universal else "legacy_19"
    print(f"[Teacher] Fase: {phase.id} — {phase.label}")
    print(f"[Teacher] Modo: {args.mode.upper()} | Objetivo: {speed_target:.0f} km/h")
    print(f"[Teacher] Auto-shift: {'ON' if args.auto_shift else 'OFF'} | Log cada {args.log_every} frames")
    print(f"[Teacher] Safety superficie: {ns_str(args, 'safety_profile')}")
    if args.universal:
        print(f"[Teacher] Schema: {schema} (obs agnóstico + regla when/why/how)")
    print("[Teacher] Esperando telemetría UDP (puerto 5606)...")

    if not session.wait_for_telemetry():
        print("[Error] Sin telemetría UDP. ¿PCARS2 en pista con UDP activo?")
        return 1

    log_path = args.session_log or str(default_log_path(ref.track_name or "sugo", phase.id))
    session_rec = TeachingSessionRecorder.open(log_path, {
        "mode": args.mode,
        "phase": phase.id,
        "phase_label": phase.label,
        "track": ref.track_name or "sugo",
        "reference": ns_str(args, "reference"),
        "speed_target_kmh": speed_target,
        "safety_profile": ns_str(args, "safety_profile"),
        "universal_schema": args.universal,
        "reference_lap_s": round(ref.lap_time, 3) if ref.lap_time else None,
    })
    print(f"[Teacher] Session log: {log_path}")

    dataset_rec: DatasetRecorder | None = None
    if args.mode == "record":
        default_name = "universal_teacher" if args.universal else ORIGIN_TEACHER.lower()
        out = args.output or DatasetRecorder.default_output_path(
            ref.track_name or "track", "formula_rookie__sugo", default_name,
        )
        dataset_rec = DatasetRecorder(output_path=out, origin=ORIGIN_TEACHER)
        dataset_rec.open()
        print(f"[Teacher] Dataset: {out}")

    controller = DS4Controller(mode=args.gamepad)
    shifter = AutoShifter()
    diag = TeachingDiagnostics(log_every=args.log_every)
    start_lap = session.last_timings.current_lap if session.last_timings else 0
    lap_completion = LapCompletionTracker()
    laps_done = 0
    cte_sum = 0.0
    cte_count = 0
    lap_ticks: List[dict] = []

    safety.reset(
        lap_distance=session.last_timings.lap_distance if session.last_timings else 0.0,
        current_lap=start_lap,
    )
    lap_completion.reset(
        start_lap,
        session.last_timings.lap_distance if session.last_timings else 0.0,
    )

    maybe_engage_first_gear(
        controller,
        shifter,
        lambda: session.last_telem,
        session.sync_physics_frame,
        args.auto_shift,
        "Teacher",
    )

    try:
        while True:
            if not session.sync_physics_frame():
                continue
            if session.last_telem is None or session.last_timings is None:
                continue

            telem = session.last_telem
            timings = session.last_timings

            status = safety.update(telem, timings)
            decision = resolve_teacher_decision(teacher, telem, timings, safety, status)

            controller.apply_action(*decision.as_tuple())
            shift_event = None
            if args.auto_shift:
                shift_event = auto_shift(
                    controller, telem, decision.throttle, decision.brake, shifter,
                )
                if shift_event:
                    diag.on_shift(shift_event, telem)

            for event in diag.frame_events(status, telem, timings, decision.cte, shift_event):
                session_rec.record_event(event)

            flags = session_tick_flags(status, decision.cte)
            rpm_pct = rpm_ratio(telem) * 100.0
            lap_ticks.append(make_lap_buffer_tick(
                session_rec.elapsed_s(),
                telem.speed * 3.6,
                decision.cte,
                decision.safety_override,
                flags.off_track,
                flags.stuck,
                decision.reason,
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
                throttle=decision.throttle,
                brake=decision.brake,
                steering=decision.steering,
                teacher_reason=decision.reason,
                rule=rule_for_reason(decision.reason),
                safety_override=decision.safety_override,
                safety_event=status.reason if status.active else None,
                off_track=flags.off_track,
                off_surface=flags.off_surface,
                off_track_cte=flags.off_track_cte,
                stuck=flags.stuck,
                gear=telem.gear,
                num_gears=telem.num_gears,
                rpm=telem.rpm,
                rpm_pct=rpm_pct,
                shift_event=shift_event,
                stuck_steps=status.stuck_steps,
                track_diag=track_diag,
            )

            if dataset_rec is not None:
                obs = (
                    build_obs_universal(telem, timings, ref, teacher.speed_target_ms)
                    if args.universal
                    else build_obs(telem, timings, ref)
                )
                dataset_rec.maybe_record(
                    obs=obs,
                    action=encoded_action_tuple(*decision.as_tuple()),
                    lap_distance=timings.lap_distance,
                    cte=decision.cte,
                    heading_err=decision.heading_err,
                    teacher_reason=decision.reason,
                    safety=status.active,
                    obs_schema=schema,
                    track_name=ref.track_name or "",
                )

            cte_sum += decision.cte
            cte_count += 1

            avg_cte = cte_sum / max(cte_count, 1)
            diag.periodic_log(
                telem,
                timings,
                decision.reason,
                decision.cte,
                avg_cte,
                shift_event,
                dataset_rec.samples_written if dataset_rec else None,
            )

            lap_result = process_lap_rollover(
                lap_ticks, timings.current_lap, timings.lap_distance,
                lap_completion, phase.id, session_rec,
            )
            if lap_result is not None:
                laps_done = lap_completion.laps_done
                print(
                    f"[Teacher] Vuelta {laps_done} | {format_lap_time(lap_result.lap_time_s)} | "
                    f"{lap_result.lap_eval['summary']} | CTE={lap_result.lap_eval['avg_cte']}m"
                )
                lap_ticks = rotate_lap_buffer(lap_ticks)
                cte_sum = 0.0
                cte_count = 0
                teacher.reset()
                if args.max_laps > 0 and laps_done >= args.max_laps:
                    print(f"[Teacher] Límite de {args.max_laps} vueltas alcanzado.")
                    break

    except KeyboardInterrupt:
        print("\n[Teacher] Detenido por el usuario.")
    finally:
        controller.release()
        if dataset_rec is not None:
            dataset_rec.close()
            print(
                f"[Teacher] Dataset: {dataset_rec.samples_written} muestras, "
                f"{dataset_rec.samples_skipped} omitidas"
            )
        print(
            f"[Teacher] Diagnóstico: shifts={diag.shift_count} | "
            f"safety_events={diag.safety_events} | frames={diag.frame}"
        )
        report = session_rec.finish(laps_completed=laps_done, open_browser=args.open_report)
        if report.get("evaluation"):
            ev = report["evaluation"]
            print(f"[Teacher] Validación: {ev.get('summary', '')}")

    return 0


def main() -> None:
    sys.exit(run(parse_args()))


if __name__ == "__main__":
    main()
