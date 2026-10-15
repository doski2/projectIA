"""
validation_phases.py
Fases de validación Teaching en Sugo (pasos pequeños y firmes).

Cada fase define objetivo, velocidad y criterios de pass/fail medibles en el log.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from safety_monitor import off_track_pct_breakdown


@dataclass
class PhaseCriteria:
    min_ticks: int = 50
    min_duration_s: float = 30.0
    min_laps: int = 0
    avg_cte_max: Optional[float] = None
    cte_p95_max: Optional[float] = None
    pct_off_track_max: Optional[float] = None
    pct_stuck_max: Optional[float] = None
    avg_speed_min_kmh: Optional[float] = None
    avg_speed_max_kmh: Optional[float] = None
    min_accel_reason_pct: Optional[float] = None
    min_brake_reason_pct: Optional[float] = None
    max_safety_override_pct: Optional[float] = None


@dataclass
class ValidationPhase:
    id: str
    label: str
    description: str
    speed_target_kmh: float
    criteria: PhaseCriteria
    next_phase: Optional[str] = None


PHASES: Dict[str, ValidationPhase] = {
    "f1_linea": ValidationPhase(
        id="f1_linea",
        label="F1 — Girar en línea",
        description=(
            "Prioridad: mantener el trazado. Teacher a baja velocidad; "
            "validar CTE y vueltas sin salirse."
        ),
        speed_target_kmh=15.0,
        criteria=PhaseCriteria(
            min_ticks=100,
            min_duration_s=45.0,
            min_laps=1,
            avg_cte_max=6.0,
            cte_p95_max=10.0,
            pct_off_track_max=8.0,
            pct_stuck_max=25.0,
            max_safety_override_pct=30.0,
        ),
        next_phase="f2_acelerar",
    ),
    "f2_acelerar": ValidationPhase(
        id="f2_acelerar",
        label="F2 — Acelerar",
        description=(
            "Prioridad: gas progresivo en recta hasta velocidad objetivo. "
            "CTE sigue controlado."
        ),
        speed_target_kmh=20.0,
        criteria=PhaseCriteria(
            min_ticks=150,
            min_duration_s=60.0,
            min_laps=1,
            avg_cte_max=6.0,
            avg_speed_min_kmh=14.0,
            avg_speed_max_kmh=26.0,
            min_accel_reason_pct=8.0,
            pct_stuck_max=20.0,
        ),
        next_phase="f3_frenar",
    ),
    "f3_frenar": ValidationPhase(
        id="f3_frenar",
        label="F3 — Frenar",
        description=(
            "Prioridad: anticipar curvas y overspeed. "
            "Debe aparecer frenada en el log sin atascarse."
        ),
        speed_target_kmh=20.0,
        criteria=PhaseCriteria(
            min_ticks=150,
            min_duration_s=60.0,
            min_laps=1,
            avg_cte_max=6.5,
            min_brake_reason_pct=5.0,
            pct_stuck_max=15.0,
            max_safety_override_pct=25.0,
        ),
        next_phase="f4_combinado",
    ),
    "f4_combinado": ValidationPhase(
        id="f4_combinado",
        label="F4 — Combinado (vuelta limpia)",
        description=(
            "Girar + acelerar + frenar en la misma vuelta a 20 km/h. "
            "Listo para grabar dataset universal."
        ),
        speed_target_kmh=20.0,
        criteria=PhaseCriteria(
            min_ticks=200,
            min_duration_s=90.0,
            min_laps=1,
            avg_cte_max=5.0,
            cte_p95_max=8.0,
            pct_off_track_max=5.0,
            pct_stuck_max=10.0,
            avg_speed_min_kmh=15.0,
            avg_speed_max_kmh=25.0,
            min_accel_reason_pct=5.0,
            min_brake_reason_pct=3.0,
            max_safety_override_pct=15.0,
        ),
        next_phase=None,
    ),
}

DEFAULT_PHASE = "f1_linea"
ACCEL_REASONS = {"accel_straight", "accel_curve_limited", "maintain_speed"}
BRAKE_REASONS = {"brake_overspeed", "recover_line"}


def get_phase(phase_id: str) -> ValidationPhase:
    return PHASES.get(phase_id, PHASES[DEFAULT_PHASE])


def _pct(n: int, total: int) -> float:
    return round(100.0 * n / total, 1) if total > 0 else 0.0


def _p95(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, int(len(s) * 0.95))
    return round(s[idx], 2)


def compute_lap_metrics(ticks: List[dict]) -> dict:
    """Métricas agregadas de una vuelta (compartido teaching / learn / imitation)."""
    n = len(ticks)
    if n == 0:
        return {
            "n": 0,
            "avg_cte": 0.0,
            "avg_speed_kmh": 0.0,
            "cte_p95": 0.0,
            "pct_override": 0.0,
            "pct_off_track": 0.0,
            "pct_off_surface": 0.0,
            "pct_off_track_cte": 0.0,
            "pct_stuck": 0.0,
            "pct_brake": 0.0,
            "pct_accel": 0.0,
            "override_count": 0,
        }

    ctes = [abs(float(t.get("cte", 0.0))) for t in ticks]
    speeds = [float(t.get("speed_kmh", 0.0)) for t in ticks]
    reasons = [t.get("teacher_reason", "") for t in ticks]
    off_pct = off_track_pct_breakdown(ticks)
    return {
        "n": n,
        "avg_cte": round(sum(ctes) / n, 2),
        "avg_speed_kmh": round(sum(speeds) / n, 1) if speeds else 0.0,
        "cte_p95": _p95(ctes),
        "pct_override": _pct(sum(1 for t in ticks if t.get("safety_override")), n),
        "pct_off_track": off_pct["pct_off_track"],
        "pct_off_surface": off_pct["pct_off_surface"],
        "pct_off_track_cte": off_pct["pct_off_track_cte"],
        "pct_stuck": _pct(sum(1 for t in ticks if t.get("stuck")), n),
        "pct_brake": _pct(sum(1 for r in reasons if r in BRAKE_REASONS), n),
        "pct_accel": _pct(sum(1 for r in reasons if r in ACCEL_REASONS), n),
        "override_count": sum(1 for t in ticks if t.get("safety_override")),
    }


IMIT_LAP_MAX_CTE = 5.5
IMIT_LAP_MAX_CTE_P95 = 9.0
IMIT_LAP_MAX_OVERRIDE_PCT = 18.0
IMIT_LAP_MAX_OFF_TRACK_PCT = 8.0
IMIT_LAP_MAX_STUCK_PCT = 12.0


def evaluate_imitation_lap(ticks: List[dict]) -> dict:
    """Criterios para graduación hybrid → autonomous (sin exigir % freno/acel)."""
    m = compute_lap_metrics(ticks)
    if m["n"] == 0:
        return {
            "clean": False,
            "avg_cte": 0.0,
            "pct_override": 0.0,
            "pct_brake": 0.0,
            "summary": "Sin ticks",
        }

    avg_cte = m["avg_cte"]
    p95_cte = m["cte_p95"]
    pct_override = m["pct_override"]
    pct_off = m["pct_off_track"]
    pct_stuck = m["pct_stuck"]

    clean = (
        avg_cte <= IMIT_LAP_MAX_CTE
        and p95_cte <= IMIT_LAP_MAX_CTE_P95
        and pct_override <= IMIT_LAP_MAX_OVERRIDE_PCT
        and pct_off <= IMIT_LAP_MAX_OFF_TRACK_PCT
        and pct_stuck <= IMIT_LAP_MAX_STUCK_PCT
    )

    issues: List[str] = []
    if avg_cte > IMIT_LAP_MAX_CTE:
        issues.append(f"CTE {avg_cte}m")
    if p95_cte > IMIT_LAP_MAX_CTE_P95:
        issues.append(f"CTE p95 {p95_cte}m")
    if pct_override > IMIT_LAP_MAX_OVERRIDE_PCT:
        issues.append(f"overrides {pct_override}%")
    if pct_off > IMIT_LAP_MAX_OFF_TRACK_PCT:
        issues.append(f"off-track {pct_off}%")
    if pct_stuck > IMIT_LAP_MAX_STUCK_PCT:
        issues.append(f"stuck {pct_stuck}%")

    return {
        "clean": clean,
        "avg_cte": avg_cte,
        "avg_speed_kmh": m["avg_speed_kmh"],
        "cte_p95": p95_cte,
        "pct_override": pct_override,
        "pct_off_track": pct_off,
        "pct_brake": m["pct_brake"],
        "pct_accel": m["pct_accel"],
        "pct_stuck": pct_stuck,
        "summary": "vuelta limpia" if clean else f"revisar: {', '.join(issues)}",
    }


def evaluate_imitation_session(
    ticks: List[dict],
    laps_completed: int,
    phase_id: str = "imit_hybrid",
) -> dict:
    """Evaluación HTML de sesión Hybrid/Autónomo (sin límite fijo de 25 km/h de F4)."""
    from lap_session import driving_ticks_for_eval

    mode = phase_id.replace("imit_", "")
    ticks = driving_ticks_for_eval(ticks)
    lap_ev = evaluate_imitation_lap(ticks)
    n = len(ticks)

    def add(checks: List[dict], name: str, ok: bool, value, threshold, unit: str = "") -> None:
        checks.append({
            "name": name, "ok": ok, "value": value, "threshold": threshold, "unit": unit,
        })

    checks: List[dict] = []
    if n == 0:
        return {
            "phase_id": phase_id,
            "phase_label": f"Imitation — {mode}",
            "passed": False,
            "checks": checks,
            "summary": "Sin ticks en la sesión.",
            "metrics": {},
        }

    duration = ticks[-1].get("t_s", 0.0) - ticks[0].get("t_s", 0.0)
    add(checks, "laps", laps_completed >= 1, laps_completed, 1)
    add(checks, "avg_cte", lap_ev["avg_cte"] <= IMIT_LAP_MAX_CTE, lap_ev["avg_cte"], IMIT_LAP_MAX_CTE, "m")
    add(checks, "cte_p95", lap_ev["cte_p95"] <= IMIT_LAP_MAX_CTE_P95, lap_ev["cte_p95"], IMIT_LAP_MAX_CTE_P95, "m")
    add(checks, "pct_safety_override", lap_ev["pct_override"] <= IMIT_LAP_MAX_OVERRIDE_PCT, lap_ev["pct_override"], IMIT_LAP_MAX_OVERRIDE_PCT, "%")
    add(checks, "pct_off_track", lap_ev["pct_off_track"] <= IMIT_LAP_MAX_OFF_TRACK_PCT, lap_ev["pct_off_track"], IMIT_LAP_MAX_OFF_TRACK_PCT, "%")
    add(checks, "pct_stuck", lap_ev["pct_stuck"] <= IMIT_LAP_MAX_STUCK_PCT, lap_ev["pct_stuck"], IMIT_LAP_MAX_STUCK_PCT, "%")

    passed = lap_ev["clean"] and laps_completed >= 1
    failed = [c["name"] for c in checks if not c["ok"]]

    return {
        "phase_id": phase_id,
        "phase_label": f"Imitation — {mode}",
        "passed": passed,
        "checks": checks,
        "metrics": {
            "n_ticks": n,
            "duration_s": round(duration, 1),
            "laps_completed": laps_completed,
            "avg_cte": lap_ev["avg_cte"],
            "cte_p95": lap_ev["cte_p95"],
            "avg_speed_kmh": lap_ev["avg_speed_kmh"],
            "pct_off_track": lap_ev["pct_off_track"],
            "pct_off_surface": lap_ev.get("pct_off_surface", 0.0),
            "pct_off_track_cte": lap_ev.get("pct_off_track_cte", 0.0),
            "pct_stuck": lap_ev["pct_stuck"],
            "pct_safety_override": lap_ev["pct_override"],
            "pct_accel_reason": lap_ev["pct_accel"],
            "pct_brake_reason": lap_ev["pct_brake"],
        },
        "summary": "APTO" if passed else f"Revisar: {', '.join(failed)}",
    }


def evaluate_teaching_lap(ticks: List[dict], phase_id: str) -> dict:
    """Evalúa una sola vuelta contra criterios de fase Teaching (F1–F4)."""
    phase = get_phase(phase_id)
    crit = phase.criteria
    m = compute_lap_metrics(ticks)
    if m["n"] == 0:
        return {
            "clean": False,
            "avg_cte": 0.0,
            "pct_override": 0.0,
            "pct_brake": 0.0,
            "summary": "Sin ticks",
        }

    avg_cte = m["avg_cte"]
    avg_speed = m["avg_speed_kmh"]
    p95_cte = m["cte_p95"]
    pct_override = m["pct_override"]
    pct_off = m["pct_off_track"]
    pct_stuck = m["pct_stuck"]
    pct_brake = m["pct_brake"]
    pct_accel = m["pct_accel"]

    clean = True
    issues: List[str] = []
    if crit.avg_cte_max is not None and avg_cte > crit.avg_cte_max:
        clean = False
        issues.append(f"CTE {avg_cte}m")
    if crit.cte_p95_max is not None and p95_cte > crit.cte_p95_max:
        clean = False
        issues.append(f"CTE p95 {p95_cte}m")
    if crit.pct_off_track_max is not None and pct_off > crit.pct_off_track_max:
        clean = False
        issues.append(f"off-track {pct_off}%")
    if crit.pct_stuck_max is not None and pct_stuck > crit.pct_stuck_max:
        clean = False
        issues.append(f"stuck {pct_stuck}%")
    if crit.max_safety_override_pct is not None and pct_override > crit.max_safety_override_pct:
        clean = False
        issues.append(f"overrides {pct_override}%")
    if crit.avg_speed_min_kmh is not None and avg_speed < crit.avg_speed_min_kmh:
        clean = False
        issues.append(f"vel {avg_speed} km/h")
    if crit.avg_speed_max_kmh is not None and avg_speed > crit.avg_speed_max_kmh:
        clean = False
        issues.append(f"vel {avg_speed} km/h")
    if crit.min_brake_reason_pct is not None and pct_brake < crit.min_brake_reason_pct:
        clean = False
        issues.append(f"freno {pct_brake}%")
    if crit.min_accel_reason_pct is not None and pct_accel < crit.min_accel_reason_pct:
        clean = False
        issues.append(f"acel {pct_accel}%")

    return {
        "clean": clean,
        "avg_cte": avg_cte,
        "avg_speed_kmh": avg_speed,
        "cte_p95": p95_cte,
        "pct_override": pct_override,
        "pct_off_track": pct_off,
        "pct_brake": pct_brake,
        "pct_accel": pct_accel,
        "pct_stuck": pct_stuck,
        "summary": "vuelta limpia" if clean else f"revisar: {', '.join(issues)}",
    }


def evaluate_phase(phase_id: str, ticks: List[dict], laps_completed: int) -> dict:
    """Evalúa criterios de una fase. Devuelve dict con passed y checks."""
    phase = get_phase(phase_id)
    crit = phase.criteria
    n = len(ticks)
    checks: List[dict] = []

    def add(name: str, ok: bool, value: Any, threshold: Any, unit: str = "") -> None:
        checks.append({
            "name": name,
            "ok": ok,
            "value": value,
            "threshold": threshold,
            "unit": unit,
        })

    if n == 0:
        return {
            "phase_id": phase_id,
            "phase_label": phase.label,
            "passed": False,
            "checks": [{"name": "ticks", "ok": False, "value": 0, "threshold": crit.min_ticks}],
            "summary": "Sin ticks en la sesión.",
        }

    duration = ticks[-1].get("t_s", 0.0) - ticks[0].get("t_s", 0.0)
    ctes = [abs(float(t.get("cte", 0.0))) for t in ticks]
    speeds = [float(t.get("speed_kmh", 0.0)) for t in ticks]
    avg_cte = round(sum(ctes) / n, 2)
    avg_speed = round(sum(speeds) / n, 1)
    p95_cte = _p95(ctes)

    stuck = sum(1 for t in ticks if t.get("stuck"))
    safety_ovr = sum(1 for t in ticks if t.get("safety_override"))

    reasons = [t.get("teacher_reason", "") for t in ticks]
    accel_n = sum(1 for r in reasons if r in ACCEL_REASONS)
    brake_n = sum(1 for r in reasons if r in BRAKE_REASONS)

    off_pct = off_track_pct_breakdown(ticks)
    pct_off = off_pct["pct_off_track"]
    pct_stuck = _pct(stuck, n)
    pct_safety = _pct(safety_ovr, n)
    pct_accel = _pct(accel_n, n)
    pct_brake = _pct(brake_n, n)

    add("ticks", n >= crit.min_ticks, n, crit.min_ticks)
    add("duration_s", duration >= crit.min_duration_s, round(duration, 1), crit.min_duration_s, "s")
    if crit.min_laps > 0:
        add("laps", laps_completed >= crit.min_laps, laps_completed, crit.min_laps)
    if crit.avg_cte_max is not None:
        add("avg_cte", avg_cte <= crit.avg_cte_max, avg_cte, crit.avg_cte_max, "m")
    if crit.cte_p95_max is not None:
        add("cte_p95", p95_cte <= crit.cte_p95_max, p95_cte, crit.cte_p95_max, "m")
    if crit.pct_off_track_max is not None:
        add("pct_off_track", pct_off <= crit.pct_off_track_max, pct_off, crit.pct_off_track_max, "%")
    if crit.pct_stuck_max is not None:
        add("pct_stuck", pct_stuck <= crit.pct_stuck_max, pct_stuck, crit.pct_stuck_max, "%")
    if crit.avg_speed_min_kmh is not None:
        add("avg_speed_min", avg_speed >= crit.avg_speed_min_kmh, avg_speed, crit.avg_speed_min_kmh, "km/h")
    if crit.avg_speed_max_kmh is not None:
        add("avg_speed_max", avg_speed <= crit.avg_speed_max_kmh, avg_speed, crit.avg_speed_max_kmh, "km/h")
    if crit.min_accel_reason_pct is not None:
        add("pct_accel_reason", pct_accel >= crit.min_accel_reason_pct, pct_accel, crit.min_accel_reason_pct, "%")
    if crit.min_brake_reason_pct is not None:
        add("pct_brake_reason", pct_brake >= crit.min_brake_reason_pct, pct_brake, crit.min_brake_reason_pct, "%")
    if crit.max_safety_override_pct is not None:
        add("pct_safety_override", pct_safety <= crit.max_safety_override_pct, pct_safety, crit.max_safety_override_pct, "%")

    passed = all(c["ok"] for c in checks)
    failed = [c["name"] for c in checks if not c["ok"]]

    return {
        "phase_id": phase_id,
        "phase_label": phase.label,
        "passed": passed,
        "checks": checks,
        "metrics": {
            "n_ticks": n,
            "duration_s": round(duration, 1),
            "laps_completed": laps_completed,
            "avg_cte": avg_cte,
            "cte_p95": p95_cte,
            "avg_speed_kmh": avg_speed,
            "pct_off_track": pct_off,
            "pct_off_surface": off_pct["pct_off_surface"],
            "pct_off_track_cte": off_pct["pct_off_track_cte"],
            "pct_stuck": pct_stuck,
            "pct_safety_override": pct_safety,
            "pct_accel_reason": pct_accel,
            "pct_brake_reason": pct_brake,
        },
        "next_phase": phase.next_phase if passed else phase_id,
        "summary": "APTO" if passed else f"Revisar: {', '.join(failed)}",
    }
