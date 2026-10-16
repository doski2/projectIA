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


def vehicle_diag(telem) -> dict:
    """Respuesta real del coche (UDP) para comparar con el volante enviado."""
    return {
        "game_steer": round(telem.steering / 127.0, 3),
        "raw_steer": round(telem.raw_steering / 127.0, 3),
        "game_throttle": round(telem.throttle / 255.0, 3),
        "game_brake": round(telem.brake / 255.0, 3),
        "yaw_rate": round(telem.angular_velocity[1], 4),
        "lat_accel": round(telem.local_acceleration[2], 3),
        "terrain": list(telem.terrain),
        "tyre_rps": [round(v, 1) for v in telem.tyre_rps],
    }


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
