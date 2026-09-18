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
from typing import Any, Optional

from auto_shift import auto_shift
from controller import DS4Controller, decode_action
from dataset_recorder import ORIGIN_MIXED, DatasetRecorder
from drive_actions import blend_actions
from drive_session import DriveSession
from obs_builder import build_obs, encoded_action_tuple
from obs_universal import OBS_SCHEMA, build_obs_universal
from reference_recorder import ReferenceLine
from safety_monitor import SafetyMonitor
from teacher_controller import TeacherConfig, TeachingController, resolve_teacher_decision
from teacher_intents import decode_reason_id, normalize_reason
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
    parser.add_argument("--log-every", type=int, default=50)
    parser.add_argument("--graduation-laps", type=int, default=5,
                        help="Vueltas limpias para graduar a autonomous en hybrid")
    parser.add_argument("--auto-shift", action=argparse.BooleanOptionalAction, default=True,
                        help="Cambio automático de marchas (RB/LB)")
    return parser.parse_args()


def load_ppo_policy(model_path: str):
    from stable_baselines3 import PPO
    import os

    path = model_path if model_path.endswith(".zip") else f"{model_path}.zip"
    if not os.path.isfile(path):
        print(f"[Error] Modelo no encontrado: {path}")
        sys.exit(1)
    return PPO.load(path, device="cpu")


def run(args: argparse.Namespace) -> int:
    ref = ReferenceLine.load(args.reference)
    teacher = TeachingController(ref, TeacherConfig(speed_target_kmh=args.speed_target))
    safety = SafetyMonitor(ref=ref)
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
    lap_overrides = 0

    recorder = None
    if args.record:
        recorder = DatasetRecorder(output_path=args.record, origin=ORIGIN_MIXED)
        recorder.open()

    kind = "UNIVERSAL" if use_universal else "PPO"
    print(f"[Imitation] {kind} | Modo: {mode.upper()} | Modelo: {args.model}")
    print(f"[Imitation] alpha={alpha:.2f} | Objetivo: {args.speed_target:.0f} km/h")
    print(f"[Imitation] Auto-shift: {'ON' if args.auto_shift else 'OFF'}")
    print("[Imitation] Esperando telemetría UDP...")

    if not session.wait_for_telemetry():
        print("[Error] Sin telemetría UDP.")
        return 1

    controller = DS4Controller(mode=args.gamepad)
    start_lap = session.last_timings.current_lap if session.last_timings else 0
    laps_done = 0
    frame = 0

    safety.reset(
        lap_distance=session.last_timings.lap_distance if session.last_timings else 0.0,
        current_lap=start_lap,
    )

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

            if universal_model is not None:
                obs_record = build_obs_universal(telem, timings, ref, teacher.speed_target_ms)
                if mode == "autonomous":
                    bc_action, rid = universal_model.predict(
                        obs_record, use_predicted_reason=True,
                    )
                else:
                    bc_action, rid = universal_model.predict(obs_record, reason=reason)
                bc_tuple = decode_action(bc_action)
                schema = OBS_SCHEMA
            else:
                obs_record = build_obs(telem, timings, ref)
                bc_action, _ = ppo_policy.predict(obs_record, deterministic=True)
                bc_tuple = decode_action(bc_action)
                schema = "legacy_19"
                rid = None

            used_teacher = False
            mix_alpha_used = None
            override = teacher_decision.safety_override

            if mode == "hybrid":
                cur_alpha = 0.0 if override else alpha
                final = blend_actions(bc_tuple, teacher_tuple, cur_alpha)
                mix_alpha_used = cur_alpha
                if override:
                    used_teacher = True
                    override_count += 1
                    lap_overrides += 1
            else:
                final = bc_tuple
                if override:
                    final = teacher_tuple
                    used_teacher = True
                    override_count += 1
                    lap_overrides += 1

            controller.apply_action(*final)
            if args.auto_shift:
                auto_shift(controller, telem, final[0], final[1])

            if recorder is not None:
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

            if timings.current_lap > start_lap + laps_done:
                laps_done = timings.current_lap - start_lap
                if lap_overrides == 0:
                    clean_laps += 1
                print(
                    f"[Imitation] Vuelta {laps_done} | overrides={lap_overrides} | "
                    f"clean_streak={clean_laps}"
                )
                lap_overrides = 0
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

    print(f"[Imitation] Total overrides del teacher: {override_count}")
    return 0


def main() -> None:
    sys.exit(run(parse_args()))


if __name__ == "__main__":
    main()
