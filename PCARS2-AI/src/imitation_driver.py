"""
imitation_driver.py
Inferencia en vivo con política BC: modos BC_DRIVE, HYBRID y AUTONOMOUS.

Soporta modelo PPO clásico (19 obs) o universal (.pt con intención).

Uso:
    python imitation_driver.py --mode bc_drive --reference refs/sugo.json --model models/teacher_bc
    python imitation_driver.py --universal --model models/universal_bc.pt --reference refs/sugo.json
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from auto_shift import (
    NEUTRAL_RETRY_COOLDOWN_S,
    AutoShifter,
    auto_shift,
    maybe_engage_first_gear,
)
from pcars2_gear import cap_bc_to_speed_target, choose_bc_drive_pedals
from controller import DS4Controller, decode_action
from dataset_recorder import ORIGIN_MIXED, DatasetRecorder
from driver_cli import add_diag_track_arg, add_safety_profile_arg, ns_str
from drive_actions import blend_actions
from drive_session import DriveSession
from lap_session import (
    LapCompletionTracker,
    lap_tick_safety_flags,
    make_lap_buffer_tick,
    process_lap_rollover,
    rotate_lap_buffer,
)
from lap_transition import LapTransitionGuard
from lap_tracker import format_lap_time
from obs_builder import build_obs, encoded_action_tuple
from obs_universal import OBS_SCHEMA, build_obs_universal
from reference_recorder import ReferenceLine
from safety_monitor import SafetyMonitor
from session_log import TeachingSessionRecorder, default_log_path, vehicle_diag
from teacher_controller import TeacherConfig, TeachingController, resolve_teacher_decision
from track_deviation import maybe_build_track_diag
from teacher_intents import decode_reason_id, normalize_reason, rule_for_reason
from universal_policy import UniversalPolicy, load_universal_policy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PCARS2-AI — Imitation Driver (BC en vivo)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--mode", choices=["bc_drive", "hybrid", "autonomous"], default="bc_drive")
    parser.add_argument("--reference", "-r", required=True)
    parser.add_argument("--model", "-m", required=True, help="Modelo BC (.zip PPO o .pt universal)")
    parser.add_argument("--universal", action="store_true", help="Usar política universal (.pt)")
    parser.add_argument("--speed-target", type=float, default=20.0)
    parser.add_argument("--alpha", type=float, default=0.7,
                        help="Peso BC en modo hybrid (1.0 = solo BC)")
    parser.add_argument("--gamepad", choices=["xbox", "ds4"], default="xbox")
    parser.add_argument("--record", default="", help="JSONL opcional para grabar MIXED")
    parser.add_argument("--max-laps", type=int, default=0)
    parser.add_argument(
        "--no-speed-cap", action="store_true",
        help="No limitar al BC al objetivo de velocidad (por defecto sí, como en learn_driver)",
    )
    parser.add_argument("--log-every", type=int, default=50)
    parser.add_argument("--graduation-laps", type=int, default=5,
                        help="Vueltas limpias para graduar a autonomous en hybrid")
    parser.add_argument("--auto-shift", action=argparse.BooleanOptionalAction, default=True,
                        help="Cambio automático de marchas (RB/LB)")
    parser.add_argument("--session-log", default="", help="JSONL sesión (default: logs/imitation/...)")
    parser.add_argument("--open-report", action="store_true", help="Abrir HTML al terminar")
    add_safety_profile_arg(parser)
    add_diag_track_arg(parser)
    return parser.parse_args()


def load_ppo_policy(model_path: str):
    from stable_baselines3 import PPO
    import os

    path = model_path if model_path.endswith(".zip") else f"{model_path}.zip"
    if not os.path.isfile(path):
        print(f"[Error] Modelo no encontrado: {path}")
        sys.exit(1)
    return PPO.load(path, device="cpu")


@dataclass
class DriveMix:
    action: Tuple[float, float, float]
    drive_source: str
    used_teacher: bool
    mix_alpha: Optional[float]
    override_inc: bool


def select_bc_action(
    universal_model, ppo_policy, guard_active: bool, mode: str,
    telem, timings, ref, speed_target_ms: float, reason: str, teacher_tuple,
):
    """Devuelve (obs_record, bc_tuple, schema, reason_id) según el modelo disponible."""
    if universal_model is not None and not guard_active:
        obs_record = build_obs_universal(telem, timings, ref, speed_target_ms)
        if mode == "autonomous":
            bc_action, rid = universal_model.predict(obs_record, use_predicted_reason=True)
        else:
            bc_action, rid = universal_model.predict(obs_record, reason=reason)
        return obs_record, decode_action(bc_action), OBS_SCHEMA, rid
    if ppo_policy is not None and not guard_active:
        obs_record = build_obs(telem, timings, ref)
        bc_action, _ = ppo_policy.predict(obs_record, deterministic=True)
        return obs_record, decode_action(bc_action), "legacy_19", None
    if universal_model:
        obs_record = build_obs_universal(telem, timings, ref, speed_target_ms)
    else:
        obs_record = build_obs(telem, timings, ref)
    schema = OBS_SCHEMA if universal_model else "legacy_19"
    return obs_record, teacher_tuple, schema, None


def mix_drive_action(
    mode: str, alpha: float, bc_tuple, teacher_tuple, telem, override: bool, guard_active: bool,
) -> DriveMix:
    """Decide la acción final (BC / teacher / mezcla híbrida) antes del lap_guard."""
    if guard_active:
        return DriveMix(teacher_tuple, "teacher", True, None, False)
    ped, src, ovr_inc = choose_bc_drive_pedals(bc_tuple, teacher_tuple, telem, override, False)
    if mode == "hybrid" and src == "bc":
        cur_alpha = 0.0 if override else alpha
        final = blend_actions(bc_tuple, teacher_tuple, cur_alpha)
        if override:
            return DriveMix(final, "teacher", True, cur_alpha, True)
        return DriveMix(final, "hybrid", False, cur_alpha, False)
    return DriveMix(ped, src, src.startswith("teacher"), None, bool(ovr_inc))


def run(args: argparse.Namespace) -> int:
    ref = ReferenceLine.load(args.reference)
    teacher = TeachingController(ref, TeacherConfig(speed_target_kmh=args.speed_target))
    safety = SafetyMonitor(ref=ref, surface_profile=ns_str(args, "safety_profile"))
    session = DriveSession()

    universal_model: Optional[UniversalPolicy] = None
    ppo_policy: Any = None
    use_universal = args.universal or args.model.endswith(".pt")
    if use_universal:
        universal_model = load_universal_policy(args.model)
    else:
        ppo_policy = load_ppo_policy(args.model)

    mode = args.mode
    alpha = args.alpha
    override_count = 0
    clean_laps = 0

    recorder = None
    if args.record:
        recorder = DatasetRecorder(output_path=args.record, origin=ORIGIN_MIXED)
        recorder.open()

    phase_id = f"imit_{mode}"
    log_path = args.session_log or str(
        default_log_path(ref.track_name or "sugo", phase_id, category="imitation"),
    )
    session_rec = TeachingSessionRecorder.open(log_path, {
        "mode": mode,
        "phase": phase_id,
        "phase_label": f"Imitation — {mode}",
        "track": ref.track_name or "sugo",
        "reference": args.reference,
        "speed_target_kmh": args.speed_target,
        "model": args.model,
        "universal": use_universal,
        "reference_lap_s": round(ref.lap_time, 3) if ref.lap_time else None,
    })

    kind = "UNIVERSAL" if use_universal else "PPO"
    print(f"[Imitation] {kind} | Modo: {mode.upper()} | Modelo: {args.model}")
    print(f"[Imitation] alpha={alpha:.2f} | Objetivo: {args.speed_target:.0f} km/h")
    print(f"[Imitation] Safety superficie: {ns_str(args, 'safety_profile')}")
    print(f"[Imitation] Auto-shift: {'ON' if args.auto_shift else 'OFF'}")
    print(f"[Imitation] Session log: {log_path}")
    print("[Imitation] Esperando telemetría UDP...")

    if not session.wait_for_telemetry():
        print("[Error] Sin telemetría UDP.")
        return 1

    controller = DS4Controller(mode=args.gamepad)
    shifter = AutoShifter(neutral_retry_s=NEUTRAL_RETRY_COOLDOWN_S)
    start_lap = session.last_timings.current_lap if session.last_timings else 0
    lap_completion = LapCompletionTracker()
    laps_done = 0
    frame = 0
    lap_ticks: List[dict] = []
    lap_guard = LapTransitionGuard(track_length=ref.track_length)

    safety.reset(
        lap_distance=session.last_timings.lap_distance if session.last_timings else 0.0,
        current_lap=start_lap,
    )

    maybe_engage_first_gear(
        controller,
        shifter,
        lambda: session.last_telem,
        session.sync_physics_frame,
        args.auto_shift,
        "Imitation",
    )

    _init_dist = session.last_timings.lap_distance if session.last_timings else 0.0
    lap_guard.reset(start_lap, _init_dist)
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

            status = safety.update(telem, timings)
            teacher_decision = resolve_teacher_decision(
                teacher, telem, timings, safety, status,
            )
            teacher_tuple = teacher_decision.as_tuple()
            reason = normalize_reason(teacher_decision.reason)
            lap_guard.on_frame(timings.current_lap, timings.lap_distance)

            obs_record, bc_tuple, schema, rid = select_bc_action(
                universal_model, ppo_policy, lap_guard.active, mode,
                telem, timings, ref, teacher.speed_target_ms, reason, teacher_tuple,
            )

            override = teacher_decision.safety_override
            mix = mix_drive_action(
                mode, alpha, bc_tuple, teacher_tuple, telem, override, lap_guard.active,
            )
            final = mix.action
            drive_source = mix.drive_source
            used_teacher = mix.used_teacher
            mix_alpha_used = mix.mix_alpha
            if mix.override_inc:
                override_count += 1
            if not args.no_speed_cap and not lap_guard.active and not override and not used_teacher:
                final, capped = cap_bc_to_speed_target(
                    final, telem.speed, teacher.speed_target_ms,
                )
                if capped:
                    drive_source = "teacher:speed"

            settle = lap_guard.apply(teacher_tuple, final)
            if settle.active:
                final = (settle.throttle, settle.brake, settle.steering)
                used_teacher = True

            controller.apply_action(*final)
            shift_event = None
            if args.auto_shift:
                shift_event = auto_shift(controller, telem, final[0], final[1], shifter)

            flags = lap_tick_safety_flags(
                status, teacher_decision.cte, lap_guard.active,
            )
            lap_override = override if not lap_guard.active else False
            lap_ticks.append(make_lap_buffer_tick(
                session_rec.elapsed_s(),
                telem.speed * 3.6,
                teacher_decision.cte,
                lap_override,
                flags.off_track,
                flags.stuck,
                reason,
                settling=lap_guard.active,
                off_surface=flags.off_surface,
                off_track_cte=flags.off_track_cte,
            ))
            if settle.active:
                drive_source = f"settle:{settle.reason}"
            track_diag = maybe_build_track_diag(
                args.diag_track, telem, timings, ref, teacher_decision.signed_cte,
            )
            session_rec.record_tick(
                telem_speed_kmh=telem.speed * 3.6,
                lap=timings.current_lap,
                lap_distance=timings.lap_distance,
                cte=teacher_decision.cte,
                signed_cte=teacher_decision.signed_cte,
                heading_err=teacher_decision.heading_err,
                throttle=final[0],
                brake=final[1],
                steering=final[2],
                teacher_reason=reason,
                rule=rule_for_reason(reason),
                drive_source=drive_source,
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

            if recorder is not None and not lap_guard.active:
                recorder.maybe_record(
                    obs=obs_record,
                    action=encoded_action_tuple(*final),
                    lap_distance=timings.lap_distance,
                    cte=teacher_decision.cte,
                    heading_err=teacher_decision.heading_err,
                    teacher_reason="hybrid" if mode == "hybrid" else mode,
                    safety=override,
                    confidence=1.0 - (0.5 if used_teacher else 0.0),
                    mix_alpha=mix_alpha_used,
                    obs_schema=schema,
                    track_name=ref.track_name or "",
                )

            if frame % args.log_every == 0:
                spd = telem.speed * 3.6
                intent = decode_reason_id(rid) if rid is not None else reason
                print(
                    f"  f={frame} | {spd:5.1f} km/h | CTE={teacher_decision.cte:4.1f}m | "
                    f"intent={intent} | mode={mode} | teacher={'Y' if used_teacher else 'N'} | "
                    f"ovr={override_count}"
                )

            lap_result = process_lap_rollover(
                lap_ticks, timings.current_lap, timings.lap_distance,
                lap_completion, phase_id, session_rec,
            )
            if lap_result is not None:
                laps_done = lap_completion.laps_done
                if lap_result.clean:
                    clean_laps += 1
                else:
                    clean_laps = 0
                print(
                    f"[Imitation] Vuelta {laps_done} | {format_lap_time(lap_result.lap_time_s)} | "
                    f"{lap_result.lap_eval['summary']} | overrides={lap_result.lap_overrides} | "
                    f"clean_streak={clean_laps}"
                )
                lap_ticks = rotate_lap_buffer(lap_ticks)
                teacher.reset()

                if mode == "hybrid" and clean_laps >= args.graduation_laps:
                    mode = "autonomous"
                    print(f"[Imitation] Graduado a AUTONOMOUS tras {clean_laps} vueltas limpias.")

                if args.max_laps > 0 and laps_done >= args.max_laps:
                    break

    except KeyboardInterrupt:
        print("\n[Imitation] Detenido.")
    finally:
        controller.release()
        if recorder is not None:
            recorder.close()
        session_rec.record_event({
            "type": "session_stats",
            "clean_streak": clean_laps,
            "laps_completed": laps_done,
            "mode": mode,
        })
        report = session_rec.finish(laps_completed=laps_done, open_browser=args.open_report)
        if report.get("html"):
            print(f"[Imitation] Informe: {report['html']}")

    print(f"[Imitation] Total overrides del teacher: {override_count}")
    return 0


def main() -> None:
    sys.exit(run(parse_args()))


if __name__ == "__main__":
    main()
