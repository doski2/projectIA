"""
learning_curriculum.py
Currículo de aprendizaje online: línea → velocidad → frenada → combinado → rápido → autonomía.

Cada etapa sube velocidad y exige vueltas limpias antes de avanzar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from lap_tracker import lap_time_stats
from validation_phases import compute_lap_metrics


@dataclass
class LearnObjective:
    id: str
    label: str
    metric: str
    target: float
    unit: str = ""
    compare: str = "le"  # le | ge | eq


@dataclass
class LearnStage:
    id: str
    label: str
    description: str
    speed_target_kmh: float
    clean_laps_required: int
    max_lap_cte: float
    max_lap_override_pct: float
    min_brake_pct: Optional[float] = None
    min_avg_speed_kmh: Optional[float] = None
    next_stage: Optional[str] = None
    autonomous_ready: bool = False
    objectives: List[LearnObjective] = field(default_factory=list)


def _objs(*items: LearnObjective) -> List[LearnObjective]:
    return list(items)


LEARN_STAGES: Dict[str, LearnStage] = {
    "l1_linea": LearnStage(
        id="l1_linea",
        label="L1 — Línea y lógica",
        description="Aprender trazado y conceptos básicos (CTE, heading) a baja velocidad.",
        speed_target_kmh=15.0,
        clean_laps_required=2,
        max_lap_cte=4.5,
        max_lap_override_pct=12.0,
        next_stage="l2_velocidad",
        objectives=_objs(
            LearnObjective("linea", "Trazado (CTE medio)", "avg_cte", 4.5, "m", "le"),
            LearnObjective("seguridad", "Intervenciones teacher", "pct_override", 12.0, "%", "le"),
            LearnObjective("concepto", "Vueltas limpias seguidas", "clean_streak", 2, "", "ge"),
        ),
    ),
    "l2_velocidad": LearnStage(
        id="l2_velocidad",
        label="L2 — Velocidad objetivo",
        description="Mantener 20 km/h con aceleración progresiva y línea estable.",
        speed_target_kmh=20.0,
        clean_laps_required=2,
        max_lap_cte=4.0,
        max_lap_override_pct=10.0,
        min_avg_speed_kmh=18.0,
        next_stage="l3_frenar",
        objectives=_objs(
            LearnObjective("velocidad", "Velocidad media objetivo", "avg_speed_kmh", 18.0, "km/h", "ge"),
            LearnObjective("linea", "CTE medio", "avg_cte", 4.0, "m", "le"),
            LearnObjective("concepto", "Vueltas limpias seguidas", "clean_streak", 2, "", "ge"),
        ),
    ),
    "l3_frenar": LearnStage(
        id="l3_frenar",
        label="L3 — Frenada técnica",
        description="Anticipar curvas: frenar antes de overspeed manteniendo el trazado.",
        speed_target_kmh=20.0,
        clean_laps_required=2,
        max_lap_cte=4.0,
        max_lap_override_pct=8.0,
        min_brake_pct=3.0,
        next_stage="l4_combinado",
        objectives=_objs(
            LearnObjective("frenada", "Uso de freno en curva", "pct_brake", 3.0, "%", "ge"),
            LearnObjective("linea", "CTE medio", "avg_cte", 4.0, "m", "le"),
            LearnObjective("concepto", "Vueltas limpias seguidas", "clean_streak", 2, "", "ge"),
        ),
    ),
    "l4_combinado": LearnStage(
        id="l4_combinado",
        label="L4 — Vuelta combinada",
        description="Girar + acelerar + frenar en la misma vuelta a mayor ritmo.",
        speed_target_kmh=25.0,
        clean_laps_required=2,
        max_lap_cte=3.8,
        max_lap_override_pct=6.0,
        min_brake_pct=3.0,
        next_stage="l5_rapido",
        objectives=_objs(
            LearnObjective("combinado", "Acelerar y frenar", "pct_brake", 3.0, "%", "ge"),
            LearnObjective("linea", "CTE medio", "avg_cte", 3.8, "m", "le"),
            LearnObjective("ritmo", "Registrar tiempo de vuelta", "lap_count", 1, "", "ge"),
        ),
    ),
    "l5_rapido": LearnStage(
        id="l5_rapido",
        label="L5 — Vueltas rápidas",
        description="Subir ritmo sin límites artificiales; preparar autonomía total.",
        speed_target_kmh=35.0,
        clean_laps_required=3,
        max_lap_cte=3.5,
        max_lap_override_pct=5.0,
        min_brake_pct=2.0,
        next_stage="l6_sostenido",
        autonomous_ready=False,
        objectives=_objs(
            LearnObjective("linea", "CTE medio", "avg_cte", 3.5, "m", "le"),
            LearnObjective("ritmo", "Mejorar tiempo vs 1ª vuelta", "lap_delta_first_s", 0.0, "s", "le"),
            LearnObjective("concepto", "Vueltas limpias seguidas", "clean_streak", 3, "", "ge"),
        ),
    ),
    "l6_sostenido": LearnStage(
        id="l6_sostenido",
        label="L6 — Ritmo sostenido",
        description="Mantener línea y frenada de forma estable a lo largo de varias vueltas.",
        speed_target_kmh=35.0,
        clean_laps_required=2,
        max_lap_cte=3.3,
        max_lap_override_pct=5.0,
        min_brake_pct=2.0,
        next_stage="l7_banda",
        objectives=_objs(
            LearnObjective("linea", "CTE medio", "avg_cte", 3.3, "m", "le"),
            LearnObjective("frenada", "Uso de freno", "pct_brake", 2.0, "%", "ge"),
            LearnObjective("concepto", "Vueltas limpias seguidas", "clean_streak", 2, "", "ge"),
        ),
    ),
    "l7_banda": LearnStage(
        id="l7_banda",
        label="L7 — Banda dominada",
        description="Validar la banda de velocidad actual antes de subir al siguiente escalón.",
        speed_target_kmh=35.0,
        clean_laps_required=3,
        max_lap_cte=3.2,
        max_lap_override_pct=4.0,
        min_brake_pct=2.0,
        next_stage=None,
        autonomous_ready=True,
        objectives=_objs(
            LearnObjective("linea", "CTE medio", "avg_cte", 3.2, "m", "le"),
            LearnObjective("autonomia", "Vueltas limpias para graduar banda", "clean_streak", 3, "", "ge"),
        ),
    ),
}

DEFAULT_LEARN_STAGE = "l1_linea"
DEFAULT_SPEED_BAND_KMH = 20.0
SPEED_BANDS_KMH = [20.0, 30.0, 40.0, 50.0, 55.0, 60.0, 70.0, 80.0]
MAX_SPEED_BAND_KMH = 80.0


def get_learn_stage(stage_id: str) -> LearnStage:
    return LEARN_STAGES.get(stage_id, LEARN_STAGES[DEFAULT_LEARN_STAGE])


def resolve_stage_speed(stage_id: str, speed_override_kmh: float = 0.0) -> float:
    """Compat: usar resolve_learn_speed con banda 0."""
    return resolve_learn_speed(stage_id, 0.0, speed_override_kmh)


def resolve_learn_speed(
    stage_id: str,
    speed_band_kmh: float = 0.0,
    speed_override_kmh: float = 0.0,
) -> float:
    """Prioridad: override fino > banda fija > velocidad nominal de etapa."""
    if speed_override_kmh > 0:
        return speed_override_kmh
    if speed_band_kmh > 0:
        return speed_band_kmh
    return get_learn_stage(stage_id).speed_target_kmh


def effective_min_avg_speed(stage: LearnStage, speed_band_kmh: float) -> Optional[float]:
    """Escala el mínimo de velocidad media de la etapa a la banda actual."""
    if stage.min_avg_speed_kmh is None:
        return None
    if speed_band_kmh <= 0 or stage.speed_target_kmh <= 0:
        return stage.min_avg_speed_kmh
    ratio = stage.min_avg_speed_kmh / stage.speed_target_kmh
    return round(speed_band_kmh * ratio, 1)


def next_speed_band(current_band_kmh: float) -> Optional[float]:
    bands = sorted(SPEED_BANDS_KMH)
    for b in bands:
        if b > current_band_kmh:
            return b
    return None


def stage_blurb(stage_id: str, speed_band_kmh: float = DEFAULT_SPEED_BAND_KMH) -> str:
    """Texto breve para GUI: qué dominar antes de pasar de etapa o banda."""
    s = get_learn_stage(stage_id)
    min_avg = effective_min_avg_speed(s, speed_band_kmh)
    lines = [
        s.description,
        f"Banda de velocidad actual: {speed_band_kmh:.0f} km/h (teacher a ese objetivo).",
        (
            f"Para avanzar de etapa: {s.clean_laps_required} vueltas limpias seguidas "
            f"(CTE ≤ {s.max_lap_cte} m, teacher ≤ {s.max_lap_override_pct:.0f}%)."
        ),
    ]
    if min_avg is not None:
        lines.append(f"Velocidad media de la vuelta ≥ {min_avg:.0f} km/h.")
    if s.min_brake_pct is not None:
        lines.append(f"Uso de freno en la vuelta ≥ {s.min_brake_pct:.0f}%.")
    if stage_id == "l7_banda":
        nxt = next_speed_band(speed_band_kmh)
        if nxt:
            lines.append(
                f"Al dominar L7 en {speed_band_kmh:.0f} km/h, la banda sube automáticamente "
                f"a {nxt:.0f} km/h y reinicia en L1."
            )
        else:
            lines.append("Banda máxima del currículo — prueba Hybrid y Autónomo.")
    elif s.autonomous_ready:
        lines.append("Al dominar esta etapa, prueba Hybrid en la misma banda.")
    lines.append(
        "Completa L1→L7 en cada banda antes de subir velocidad; el buffer guarda etapa + banda."
    )
    return " ".join(lines)


def _check_objective(value: float, target: float, compare: str) -> bool:
    if compare == "le":
        return value <= target
    if compare == "ge":
        return value >= target
    return abs(value - target) < 1e-6


def evaluate_objectives(
    stage_id: str,
    session_metrics: dict,
    lap_events: List[dict],
    clean_streak: int = 0,
    speed_band_kmh: float = 0.0,
) -> List[dict]:
    """Estado de objetivos pedagógicos (seguimiento; BC no optimiza tiempo directamente)."""
    stage = get_learn_stage(stage_id)
    scaled_min_speed = effective_min_avg_speed(stage, speed_band_kmh)
    lt = lap_time_stats(lap_events)
    values = {
        "avg_cte": float(session_metrics.get("avg_cte", 99)),
        "pct_override": float(session_metrics.get("pct_safety_override", 100)),
        "avg_speed_kmh": float(session_metrics.get("avg_speed_kmh", 0)),
        "pct_brake": float(session_metrics.get("pct_brake_reason", 0)),
        "clean_streak": float(clean_streak),
        "lap_count": float(lt["count"]),
        "lap_delta_first_s": float(lt["delta_last_vs_first_s"] or 99),
    }

    rows: List[dict] = []
    for obj in stage.objectives:
        val = values.get(obj.metric, 0.0)
        target = obj.target
        if obj.metric == "avg_speed_kmh" and scaled_min_speed is not None:
            target = scaled_min_speed
        ok = _check_objective(val, target, obj.compare)
        display = val
        if obj.metric == "lap_delta_first_s" and lt["delta_last_vs_first_s"] is not None:
            display = lt["delta_last_vs_first_s"]
            ok = display <= obj.target
        if obj.unit == "s" and isinstance(display, (int, float)):
            display_str = f"{display:+.3f}s"
        elif obj.unit:
            display_str = f"{display}{obj.unit}"
        else:
            display_str = str(int(display)) if obj.metric in ("clean_streak", "lap_count") else str(display)

        thresh = target
        if obj.unit == "s":
            thresh_str = f"≤ {thresh}s vs 1ª vuelta"
        elif obj.unit:
            thresh_str = f"{'≤' if obj.compare == 'le' else '≥'} {thresh}{obj.unit}"
        else:
            thresh_str = f"≥ {int(thresh)}"

        rows.append({
            "id": obj.id,
            "label": obj.label,
            "value": display_str,
            "threshold": thresh_str,
            "ok": ok,
        })
    return rows


def evaluate_lap(
    ticks: List[dict],
    stage_id: str,
    speed_band_kmh: float = 0.0,
) -> dict:
    """Evalúa una vuelta para graduación de etapa (opcionalmente en una banda de velocidad)."""
    stage = get_learn_stage(stage_id)
    min_avg = effective_min_avg_speed(stage, speed_band_kmh)
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
    off_track = m["pct_off_track"]
    pct_brake = m["pct_brake"]
    pct_accel = m["pct_accel"]
    stuck = m["pct_stuck"]

    clean = (
        avg_cte <= stage.max_lap_cte
        and pct_override <= stage.max_lap_override_pct
        and stuck <= 5.0
        and off_track <= 8.0
    )
    if stage.min_brake_pct is not None:
        clean = clean and pct_brake >= stage.min_brake_pct
    if min_avg is not None:
        clean = clean and avg_speed >= min_avg

    issues = []
    if avg_cte > stage.max_lap_cte:
        issues.append(f"CTE {avg_cte}m")
    if pct_override > stage.max_lap_override_pct:
        issues.append(f"overrides {pct_override}%")
    if stage.min_brake_pct and pct_brake < stage.min_brake_pct:
        issues.append(f"freno {pct_brake}%")
    if min_avg is not None and avg_speed < min_avg:
        issues.append(f"vel {avg_speed} km/h")
    if off_track > 8.0:
        issues.append(f"off-track {off_track}%")
    if stuck > 5.0:
        issues.append(f"stuck {stuck}%")

    return {
        "clean": clean,
        "avg_cte": avg_cte,
        "avg_speed_kmh": avg_speed,
        "cte_p95": p95_cte,
        "pct_override": pct_override,
        "pct_off_track": off_track,
        "pct_brake": pct_brake,
        "pct_accel": pct_accel,
        "pct_stuck": stuck,
        "summary": "vuelta limpia" if clean else f"revisar: {', '.join(issues)}",
    }


def evaluate_learn_session(
    ticks: List[dict],
    laps_completed: int,
    stage_id: str,
    lap_events: Optional[List[dict]] = None,
    clean_streak: int = 0,
    speed_band_kmh: float = 0.0,
) -> dict:
    """Evaluación HTML de sesión de aprendizaje (similar a teaching)."""
    from lap_session import driving_ticks_for_session_eval

    stage = get_learn_stage(stage_id)
    ticks = driving_ticks_for_session_eval(ticks)
    n = len(ticks)
    checks: List[dict] = []

    def add(name: str, ok: bool, value, threshold, unit: str = "") -> None:
        checks.append({
            "name": name, "ok": ok, "value": value, "threshold": threshold, "unit": unit,
        })

    if n == 0:
        return {
            "phase_id": stage_id,
            "phase_label": stage.label,
            "passed": False,
            "checks": checks,
            "summary": "Sin datos",
            "metrics": {},
        }

    duration = ticks[-1].get("t_s", 0.0) - ticks[0].get("t_s", 0.0)
    sm = compute_lap_metrics(ticks)
    avg_cte = sm["avg_cte"]
    avg_speed = sm["avg_speed_kmh"]
    pct_override = sm["pct_override"]
    off_track = sm["pct_off_track"]
    stuck = sm["pct_stuck"]
    pct_brake = sm["pct_brake"]
    pct_accel = sm["pct_accel"]

    laps = lap_events or []
    lt = lap_time_stats(laps)
    objectives = evaluate_objectives(stage_id, {
        "avg_cte": avg_cte,
        "pct_safety_override": pct_override,
        "avg_speed_kmh": avg_speed,
        "pct_brake_reason": pct_brake,
    }, laps, clean_streak=clean_streak, speed_band_kmh=speed_band_kmh)

    for obj in objectives:
        add(obj["id"], obj["ok"], obj["value"], obj["threshold"])

    passed = (
        n >= 100
        and laps_completed >= 1
        and all(o["ok"] for o in objectives)
    )
    return {
        "phase_id": stage_id,
        "phase_label": stage.label,
        "passed": passed,
        "checks": checks,
        "metrics": {
            "n_ticks": n,
            "duration_s": round(duration, 1),
            "laps_completed": laps_completed,
            "avg_cte": avg_cte,
            "avg_speed_kmh": avg_speed,
            "pct_safety_override": pct_override,
            "pct_off_track": off_track,
            "pct_stuck": stuck,
            "pct_accel_reason": pct_accel,
            "pct_brake_reason": pct_brake,
            "learn_stage": stage_id,
            "speed_target_kmh": stage.speed_target_kmh,
            "speed_band_kmh": speed_band_kmh if speed_band_kmh > 0 else None,
            "autonomous_ready": stage.autonomous_ready,
            "best_lap_s": lt["best_s"],
            "best_lap_fmt": lt["best_fmt"],
            "avg_lap_s": lt["avg_s"],
            "avg_lap_fmt": lt["avg_fmt"],
            "last_lap_s": lt["last_s"],
            "last_lap_fmt": lt["last_fmt"],
            "lap_improving": lt["improving_vs_prev"],
        },
        "objectives": objectives,
        "next_phase": stage.next_stage if passed else stage_id,
        "summary": "APTO" if passed else "REVISAR — seguir practicando en esta etapa",
    }


def try_advance_stage(
    stage_id: str,
    clean_streak: int,
) -> tuple[str, bool, str]:
    """Devuelve (nuevo_stage_id, avanzó, mensaje)."""
    stage = get_learn_stage(stage_id)
    if clean_streak < stage.clean_laps_required:
        return stage_id, False, (
            f"Etapa {stage.id}: {clean_streak}/{stage.clean_laps_required} vueltas limpias"
        )
    if not stage.next_stage:
        if stage_id == "l7_banda":
            if clean_streak == stage.clean_laps_required:
                return stage_id, False, (
                    f"L7 completada — banda {stage.clean_laps_required} vueltas limpias "
                    f"(siguiente banda si aplica, o prueba Hybrid)."
                )
            return stage_id, False, (
                f"L7: {clean_streak}/{stage.clean_laps_required} vueltas limpias"
            )
        return stage_id, False, (
            f"Etapa {stage.id} completada "
            f"({stage.clean_laps_required} vueltas limpias)"
        )
    nxt = get_learn_stage(stage.next_stage)
    return stage.next_stage, True, (
        f"Graduado a {nxt.id} ({nxt.label})"
    )


def try_advance_speed_band(
    speed_band_kmh: float,
    stage_id: str,
    clean_streak: int,
) -> tuple[float, bool, str, str]:
    """
    Tras dominar L7 en una banda, sube al siguiente escalón y reinicia en L1.
    Devuelve (nueva_banda, avanzó, nuevo_stage_id, mensaje).
    """
    if stage_id != "l7_banda":
        return speed_band_kmh, False, stage_id, ""
    stage = get_learn_stage(stage_id)
    if clean_streak < stage.clean_laps_required:
        return speed_band_kmh, False, stage_id, ""
    if clean_streak > stage.clean_laps_required:
        return speed_band_kmh, False, stage_id, ""
    nxt = next_speed_band(speed_band_kmh)
    if nxt is None:
        return speed_band_kmh, False, stage_id, (
            f"Banda {speed_band_kmh:.0f} km/h dominada — máximo del currículo ({MAX_SPEED_BAND_KMH:.0f} km/h)"
        )
    return nxt, True, DEFAULT_LEARN_STAGE, (
        f"*** Banda {speed_band_kmh:.0f} → {nxt:.0f} km/h — reinicia en L1 ***"
    )
