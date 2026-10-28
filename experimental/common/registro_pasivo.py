"""Registro pasivo: graba el log ampliado mientras conduces tú, sin enviar ningún pedal ni volante.

Sirve para ver los canales de daño con un golpe controlado (P15) y para rodajes largos (desgaste).
Escribe el mismo log que las demás pruebas, con `drive_source = manual`, e imprime cada evento de daño.

Uso:
    python experimental/common/registro_pasivo.py --name golpe --minutes 10 --after-damage 20
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "PCARS2-AI"
sys.path.insert(0, str(APP / "src"))

from drive_session import DriveSession  # noqa: E402
from obs_universal import signed_lateral_error  # noqa: E402
from reference_recorder import ReferenceLine  # noqa: E402
from session_log import (  # noqa: E402
    DamageWatch, TeachingSessionRecorder, conditions_diag, default_log_path, timing_diag, vehicle_diag,
)

MAX_TIMEOUTS = 30  # ticks seguidos sin telemetría antes de dar la sesión por terminada


def run(
    name: str,
    minutes: float,
    after_damage_s: float,
    reference: str = "src/refs/sugo_ai.json",
    session: Optional[DriveSession] = None,
    out_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Graba hasta `minutes` minutos (o `after_damage_s` segundos después del primer daño; 0 = sin límite)."""
    ref = ReferenceLine.load(str(APP / reference))
    session = session or DriveSession()
    log_path = (out_dir or APP) / default_log_path(ref.track_name or "sugo", "pasivo", category="learning")
    print("[Pasivo] Esperando telemetría UDP...")
    if not session.wait_for_telemetry():
        print("[Error] Sin telemetría UDP.")
        return None

    rec = TeachingSessionRecorder.open(log_path, {
        "mode": "passive",
        "phase": "pasivo",
        "phase_label": "Registro pasivo (conduce el usuario)",
        "track": ref.track_name or "sugo",
        "reference": reference,
        "speed_target_kmh": None,
        "origin": "experimental",
        "experiment": f"pasivo_{name}",
    })
    print(f"[Pasivo] Log: {log_path}\n[Pasivo] Conduce tú. Ctrl+C para terminar.")
    watch = DamageWatch(limit_pct=0)  # avisa de cualquier empeoramiento; este modo nunca para la sesión
    deadline = time.monotonic() + minutes * 60
    last_conditions: Optional[dict] = None
    timeouts = damages = 0
    try:
        while time.monotonic() < deadline:
            if not session.sync_physics_frame():
                timeouts += 1
                if timeouts >= MAX_TIMEOUTS:
                    print("[Pasivo] Sin telemetría; cierro.")
                    break
                continue
            timeouts = 0
            telem, timings = session.last_telem, session.last_timings
            if telem is None or timings is None:
                continue
            signed = signed_lateral_error(ref, telem.position, timings.lap_distance)
            rec.record_tick(
                telem_speed_kmh=telem.speed * 3.6, lap=timings.current_lap, lap_distance=timings.lap_distance,
                cte=abs(signed), signed_cte=signed,
                heading_err=ref.heading_error(telem.world_velocity, timings.lap_distance),
                throttle=telem.throttle / 255.0, brake=telem.brake / 255.0, steering=telem.steering / 127.0,
                teacher_reason="manual", drive_source="manual", gear=telem.gear, num_gears=telem.num_gears,
                rpm=telem.rpm, vehicle=vehicle_diag(telem), timing=timing_diag(timings),
            )
            conditions = conditions_diag(session.game_state)
            if conditions is not None and conditions != last_conditions:
                rec.record_event({"type": "conditions", **conditions})
                last_conditions = conditions
            damage = watch.update(telem, timings.lap_distance)
            if damage is not None:
                rec.record_event(damage)
                damages += 1
                print(f"[Pasivo] Daño {sorted(damage['changed'])}: niveles {damage['levels']} · "
                      f"crash_state {damage['context']['crash_state']} · {damage['context']['speed_kmh']} km/h")
                if damages == 1 and after_damage_s > 0:
                    deadline = min(deadline, time.monotonic() + after_damage_s)
                    print(f"[Pasivo] Primer daño: sigo grabando {after_damage_s:.0f} s más.")
    except KeyboardInterrupt:
        print("\n[Pasivo] Ctrl+C — cerrando el log...")
    finally:
        rec.record_event({"type": "session_stats", "laps_completed": 0, "damage_events": damages})
        try:
            rec.finish(laps_completed=0, open_browser=False)
        except Exception as exc:  # noqa: BLE001 - el informe de sesión no debe tapar el log
            print(f"[Pasivo] No se pudo generar el HTML de sesión: {exc!r}")
    return log_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", default="golpe", help="Se guarda como experiment=pasivo_<name>")
    ap.add_argument("--minutes", type=float, default=10.0)
    ap.add_argument("--after-damage", type=float, default=20.0, help="Segundos que sigue grabando tras el primer daño (0 = no cortar)")
    a = ap.parse_args()
    path = run(a.name, a.minutes, a.after_damage)
    if path is not None:
        try:
            sys.path.insert(0, str(REPO))
            from experimental.common.informe_c0 import build_report

            print(f"[Pasivo] Informe: {build_report(path, open_browser=True)['html']}")
        except Exception as exc:  # noqa: BLE001
            print(f"[Pasivo] No se pudo generar el informe: {exc!r}")
