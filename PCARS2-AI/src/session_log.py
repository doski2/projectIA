"""
session_log.py
Grabación JSONL de sesiones Teaching (estilo TSW6 session_log / trace).

Uso:
    recorder = TeachingSessionRecorder.open("logs/teaching/sugo_f1.jsonl", session_meta)
    recorder.record_tick(...)
    recorder.finish(laps_completed=1)  # → genera .html junto al .jsonl
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

MIN_HTML_TICKS = 15
MIN_HTML_DURATION_S = 5.0

# Versión del formato del log. 1 = sin campo (logs antiguos); 2 = bloque `vehicle` ampliado
# (ver `vehicle_extra`) y cabecera con `origin` / `experiment`.
LOG_SCHEMA = 2


def _git_hash() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return ""


def default_log_path(track: str, phase_id: str, category: str = "teaching") -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_track = (track or "track").replace(" ", "_").lower()
    return Path("logs") / category / f"{ts}_{safe_track}_{phase_id}.jsonl"


# (clave del log, atributo de TelemetryFrame, decimales; None = entero). Solo se escribe si el frame lo trae.
# Valores escalares o secuencias (se distinguen al escribir).
_VEHICLE_EXTRA = (
    ("local_velocity", "local_velocity", 3),
    ("local_accel", "local_acceleration", 3),
    ("ang_vel", "angular_velocity", 4),
    ("position", "position", 2),
    ("orientation", "orientation", 4),
    ("ride_height", "ride_height", 4),
    ("susp_travel", "suspension_travel", 4),
    ("tyre_temp", "tyre_temp", None),
    ("tyre_tread_temp", "tyre_tread_temp", None),
    ("tyre_wear", "tyre_wear", None),
    ("fuel_level", "fuel_level", 4),
    ("brake_bias", "brake_bias", None),
    ("aero_damage", "aero_damage", None),
    ("engine_damage", "engine_damage", None),
    ("raw_throttle", "raw_throttle", None),
    ("raw_brake", "raw_brake", None),
    ("clutch", "clutch", None),
    # tanda 2 (X4b): mantener al final y con "tyre_flags" el primero (VEHICLE_EXTRA_X4B_KEYS corta por ahí)
    ("tyre_flags", "tyre_flags", None),
    ("tyre_height", "tyre_height_above_ground", 3),
    ("brake_damage", "brake_damage", None),
    ("susp_damage", "suspension_damage", None),
    ("brake_temp", "brake_temp", None),
    ("susp_vel", "suspension_velocity", 3),
    ("air_pressure", "air_pressure", None),
    ("engine_torque", "engine_torque", 2),
    ("crash_state", "crash_state", None),
    ("tick_count", "tick_count", None),
    ("car_flags", "car_flags", None),  # bit 4 = ABS activo: señal directa de poco agarre al frenar
)
VEHICLE_EXTRA_KEYS = tuple(key for key, _, _ in _VEHICLE_EXTRA)
VEHICLE_EXTRA_X4B_KEYS = VEHICLE_EXTRA_KEYS[VEHICLE_EXTRA_KEYS.index("tyre_flags"):]  # logs anteriores a X4b no los traen


def _fmt(v, nd: Optional[int]):
    conv = int if nd is None else (lambda x: round(float(x), nd))
    return [conv(x) for x in v] if hasattr(v, "__iter__") else conv(v)


def vehicle_extra(telem) -> dict:
    """Campos para identificación del coche y simulador (planes A y B). Se añaden al final de `vehicle`."""
    out: dict = {}
    for key, attr, nd in _VEHICLE_EXTRA:
        v = getattr(telem, attr, None)
        if v is not None:
            out[key] = _fmt(v, nd)
    return out


def conditions_diag(game_state) -> Optional[dict]:
    """Tiempo atmosférico (paquete 4) para un evento `conditions`; None si aún no ha llegado."""
    if game_state is None:
        return None
    return {
        "ambient_c": int(game_state.ambient_temp),
        "track_c": int(game_state.track_temp),
        "rain": int(game_state.rain_density),
        "snow": int(game_state.snow_density),
        "wind_speed": int(game_state.wind_speed),
        "wind_dir": [int(game_state.wind_dir_x), int(game_state.wind_dir_y)],
        "raw_hex": bytes(game_state.raw).hex(),
    }


def timing_diag(timings) -> dict:
    """Reloj y sector del juego: permite medir el Δt real, detectar pausas y analizar por sector."""
    return {
        "sector": int(timings.sector),
        "sector_time_s": round(float(timings.current_sector_time), 3),
        "game_time_s": round(float(timings.current_time), 3),
    }


def vehicle_diag(telem) -> dict:
    """Respuesta real del coche (UDP) para comparar con el volante enviado."""
    diag = {
        "game_steer": round(telem.steering / 127.0, 3),
        "raw_steer": round(telem.raw_steering / 127.0, 3),
        "game_throttle": round(telem.throttle / 255.0, 3),
        "game_brake": round(telem.brake / 255.0, 3),
        "yaw_rate": round(telem.angular_velocity[1], 4),
        "lat_accel": round(telem.local_acceleration[2], 3),
        "terrain": list(telem.terrain),
        "tyre_rps": [round(v, 1) for v in telem.tyre_rps],
    }
    diag.update(vehicle_extra(telem))
    return diag


class TeachingSessionRecorder:
    """Escribe ticks JSONL y genera HTML al cerrar."""

    def __init__(self, path: Path):
        self.path = path
        self._file = None
        self._tick = 0
        self._t0: Optional[float] = None
        self._session: Optional[dict] = None

    @classmethod
    def open(cls, path: str | Path, session_meta: dict) -> TeachingSessionRecorder:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        rec = cls(p)
        rec._file = open(p, "w", encoding="utf-8")
        rec._session = {
            "type": "session",
            "ts": datetime.now(timezone.utc).isoformat(),
            "git": _git_hash(),
            "log_schema": LOG_SCHEMA,
            "origin": "main",
            **session_meta,
        }
        rec._file.write(json.dumps(rec._session, ensure_ascii=False) + "\n")
        rec._file.flush()
        return rec

    def record_event(self, event: dict) -> None:
        if self._file is None:
            return
        now = time.monotonic()
        if self._t0 is None:
            self._t0 = now
        row = {"t_s": round(now - self._t0, 3), **event}
        if "type" not in row:
            row["type"] = "event"
        self._file.write(json.dumps(row, ensure_ascii=False) + "\n")

    def record_tick(
        self,
        telem_speed_kmh: float,
        lap: int,
        lap_distance: float,
        cte: float,
        signed_cte: float,
        heading_err: float,
        throttle: float,
        brake: float,
        steering: float,
        teacher_reason: str,
        rule: Optional[dict] = None,
        drive_source: Optional[str] = None,
        learn_stage: Optional[str] = None,
        safety_override: bool = False,
        safety_event: Optional[str] = None,
        off_track: bool = False,
        off_surface: bool = False,
        off_track_cte: bool = False,
        stuck: bool = False,
        gear: Optional[int] = None,
        num_gears: Optional[int] = None,
        rpm: Optional[int] = None,
        rpm_pct: Optional[float] = None,
        shift_event: Optional[str] = None,
        stuck_steps: Optional[int] = None,
        track_diag: Optional[dict] = None,
        vehicle: Optional[dict] = None,
        timing: Optional[dict] = None,
    ) -> None:
        if self._file is None:
            return
        now = time.monotonic()
        if self._t0 is None:
            self._t0 = now
        self._tick += 1
        row = {
            "type": "tick",
            "tick": self._tick,
            "t_s": round(now - self._t0, 3),
            "lap": lap,
            "lap_distance": round(lap_distance, 1),
            "speed_kmh": round(telem_speed_kmh, 2),
            "cte": round(cte, 3),
            "signed_cte": round(signed_cte, 3),
            "heading_err": round(heading_err, 4),
            "throttle": round(throttle, 3),
            "brake": round(brake, 3),
            "steering": round(steering, 3),
            "teacher_reason": teacher_reason,
            "drive_source": drive_source,
            "learn_stage": learn_stage,
            "safety_override": safety_override,
            "off_track": off_track,
            "off_surface": off_surface,
            "off_track_cte": off_track_cte,
            "stuck": stuck,
        }
        if rule:
            row["rule"] = rule
        if safety_event:
            row["safety_event"] = safety_event
        if gear is not None:
            row["gear"] = gear
        if num_gears is not None:
            row["num_gears"] = num_gears
        if rpm is not None:
            row["rpm"] = rpm
        if rpm_pct is not None:
            row["rpm_pct"] = round(rpm_pct, 1)
        if shift_event:
            row["shift_event"] = shift_event
        if stuck_steps is not None:
            row["stuck_steps"] = stuck_steps
        if track_diag:
            row["track_diag"] = track_diag
        if vehicle:
            row["vehicle"] = vehicle
        if timing:
            row["timing"] = timing
        self._file.write(json.dumps(row, ensure_ascii=False) + "\n")

    def finish(self, laps_completed: int = 0, open_browser: bool = False) -> dict:
        """Cierra JSONL, evalúa fase y genera HTML."""
        if self._file is None:
            return {}
        self._file.flush()
        self._file.close()
        self._file = None

        _, _, existing, _, _ = load_session_ticks(self.path)
        if existing is None:
            from session_report import finalize_session_report
            return finalize_session_report(
                self.path,
                laps_completed=laps_completed,
                open_browser=open_browser,
            )
        from session_report import write_html_replay
        html = write_html_replay(self.path, laps_completed=laps_completed)
        result = {"jsonl": str(self.path), "html": str(html) if html else None, "evaluation": existing.get("evaluation", {})}
        if html and open_browser:
            _open_html(html)
        return result

    @property
    def tick_count(self) -> int:
        return self._tick

    def elapsed_s(self) -> float:
        if self._t0 is None:
            return 0.0
        return round(time.monotonic() - self._t0, 3)


def _open_html(html: Path) -> None:
    """Abre el informe. En Windows startfile es más fiable que el navegador por URI."""
    path = html.resolve()
    print(f"[Report] Abriendo {path}")
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606 — informe local que acaba de generar la sesión
        else:
            import webbrowser
            webbrowser.open(path.as_uri())
    except OSError as exc:
        print(f"[Report] No se pudo abrir el HTML ({exc}). Ábrelo a mano: {path}")


def load_session_ticks(
    path: Path,
) -> tuple[Optional[dict], List[dict], Optional[dict], List[dict], Optional[dict]]:
    """Carga session, ticks, summary, eventos de vuelta y session_stats desde JSONL."""
    session: Optional[dict] = None
    ticks: List[dict] = []
    summary: Optional[dict] = None
    lap_events: List[dict] = []
    session_stats: Optional[dict] = None
    if not path.is_file():
        return session, ticks, summary, lap_events, session_stats
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        t = row.get("type")
        if t == "session":
            session = row
        elif t == "tick":
            ticks.append(row)
        elif t == "lap":
            lap_events.append(row)
        elif t == "summary":
            summary = row
        elif t == "session_stats":
            session_stats = row
    return session, ticks, summary, lap_events, session_stats
