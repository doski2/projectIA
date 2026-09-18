"""
session_report.py
Informe HTML de sesión Teaching (estilo TSW6 session_report).

Regenerar:
    python session_report.py logs/teaching/sesion.jsonl --open
"""

from __future__ import annotations

import argparse
import json
import math
import webbrowser
from collections import Counter
from pathlib import Path
from typing import Any, List, Optional

from session_log import load_session_ticks
from validation_phases import PHASES, evaluate_phase

MIN_HTML_TICKS = 15
MIN_HTML_DURATION_S = 5.0


def summarize_ticks(ticks: List[dict], laps_completed: int, phase_id: str) -> dict:
    evaluation = evaluate_phase(phase_id, ticks, laps_completed)
    reasons = Counter(t.get("teacher_reason", "?") for t in ticks)
    safety_events = Counter(
        t.get("safety_event") for t in ticks if t.get("safety_event")
    )
    return {
        "evaluation": evaluation,
        "reasons": dict(reasons.most_common()),
        "safety_events": dict(safety_events),
    }


def _downsample(series: List[dict], max_pts: int = 600) -> List[dict]:
    if len(series) <= max_pts:
        return series
    step = max(1, len(series) // max_pts)
    return series[::step]


def _svg_chart(series: List[dict], width: int = 900, height: int = 320) -> str:
    if not series:
        return "<p>Sin datos para gráfico.</p>"

    t_max = max(s["t"] for s in series) or 1.0
    panels = [
        ("speed_kmh", "Velocidad (km/h)", "#7eb6ff", 0, 80),
        ("cte", "CTE (m)", "#f59e0b", 0, 12),
        ("throttle", "Throttle", "#22c55e", 0, 1),
        ("brake", "Brake", "#ef4444", 0, 1),
        ("steering", "Steering", "#a78bfa", -1, 1),
    ]
    h_panel = height // len(panels)
    lines = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'style="background:#12151c;border-radius:8px;width:100%;max-width:{width}px">'
    ]

    for i, (key, label, color, vmin, vmax) in enumerate(panels):
        y0 = i * h_panel + 8
        h = h_panel - 16
        lines.append(
            f'<text x="8" y="{y0 + 12}" fill="#9aa3b2" font-size="11">{label}</text>'
        )

        pts = []
        for s in series:
            t = s["t"]
            v = float(s.get(key, 0.0))
            vr = (v - vmin) / max(vmax - vmin, 1e-6)
            vr = max(0.0, min(1.0, vr))
            x = 50 + (t / t_max) * (width - 60)
            y = y0 + h - vr * h
            pts.append(f"{x:.1f},{y:.1f}")

        if len(pts) >= 2:
            lines.append(
                f'<polyline fill="none" stroke="{color}" stroke-width="1.5" '
                f'points="{" ".join(pts)}"/>'
            )
        lines.append(
            f'<line x1="50" y1="{y0 + h}" x2="{width - 10}" y2="{y0 + h}" '
            f'stroke="#2a3140" stroke-width="1"/>'
        )

    lines.append("</svg>")
    return "\n".join(lines)


def write_html_replay(
    jsonl_path: Path,
    html_path: Optional[Path] = None,
    laps_completed: int = 0,
) -> Optional[Path]:
    session, ticks, existing_summary = load_session_ticks(jsonl_path)
    if len(ticks) < MIN_HTML_TICKS:
        return None
    duration = ticks[-1].get("t_s", 0) - ticks[0].get("t_s", 0)
    if duration < MIN_HTML_DURATION_S:
        return None

    phase_id = (session or {}).get("phase", "f1_linea")
    phase = PHASES.get(phase_id)
    phase_label = phase.label if phase else phase_id

    if existing_summary and "evaluation" in existing_summary:
        evaluation = existing_summary["evaluation"]
    else:
        evaluation = evaluate_phase(phase_id, ticks, laps_completed)

    summary = summarize_ticks(ticks, laps_completed, phase_id)
    series = _downsample([
        {
            "t": t.get("t_s", 0.0),
            "speed_kmh": t.get("speed_kmh", 0.0),
            "cte": abs(t.get("cte", 0.0)),
            "throttle": t.get("throttle", 0.0),
            "brake": t.get("brake", 0.0),
            "steering": t.get("steering", 0.0),
        }
        for t in ticks
    ])

    out = html_path or jsonl_path.with_suffix(".html")
    passed = evaluation.get("passed", False)
    status_cls = "pass" if passed else "fail"
    status_txt = "APTO" if passed else "REVISAR"
    metrics = evaluation.get("metrics", {})

    checks_rows = "".join(
        f"<tr><td>{c['name']}</td><td>{c['value']}{c.get('unit', '')}</td>"
        f"<td>{c['threshold']}</td>"
        f"<td class=\"{'ok' if c['ok'] else 'bad'}\">{'OK' if c['ok'] else 'FAIL'}</td></tr>"
        for c in evaluation.get("checks", [])
    )
    reason_rows = "".join(
        f"<tr><td>{k}</td><td>{v}</td></tr>"
        for k, v in summary.get("reasons", {}).items()
    )

    chart_svg = _svg_chart(series)
    data_json = json.dumps(
        {"session": session, "evaluation": evaluation, "series": series},
        ensure_ascii=False,
    )

    html = f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>PCARS2 Teaching — {session.get('track', jsonl_path.stem) if session else jsonl_path.stem}</title>
<style>
  body {{ font: 14px/1.45 system-ui, sans-serif; margin: 1rem 1.5rem 2rem; background: #0f1115; color: #e6e8ec; }}
  h1, h2 {{ color: #f0f2f5; }}
  a {{ color: #7eb6ff; }}
  .meta {{ color: #9aa3b2; margin-bottom: 1rem; }}
  .banner {{ padding: .75rem 1rem; border-radius: 8px; margin: 1rem 0; font-weight: 600; }}
  .banner.pass {{ background: #14532d; border: 1px solid #22c55e; color: #bbf7d0; }}
  .banner.fail {{ background: #422006; border: 1px solid #f59e0b; color: #fde68a; }}
  .stats {{ display: flex; flex-wrap: wrap; gap: .75rem; margin: 1rem 0; }}
  .stat {{ background: #1a1f28; padding: .6rem .85rem; border-radius: 8px; min-width: 7rem; border: 1px solid #2a3140; }}
  .stat b {{ display: block; font-size: 1.35rem; color: #7eb6ff; }}
  .stat span {{ font-size: 11px; color: #9aa3b2; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 960px; font-size: 12px; margin: .5rem 0 1rem; }}
  th, td {{ border: 1px solid #2a3140; padding: 6px 10px; text-align: left; }}
  th {{ background: #1a1f28; color: #c5cad3; }}
  td.ok {{ color: #4ade80; }}
  td.bad {{ color: #f87171; }}
  .chart-wrap {{ overflow-x: auto; margin: 1rem 0; }}
  .phase-desc {{ background: #1a1f28; padding: .75rem 1rem; border-radius: 8px; border-left: 3px solid #7eb6ff; max-width: 960px; }}
</style></head><body>
<h1>Teaching validation — {phase_label}</h1>
<p class="meta">
  Pista: <b>{session.get('track', '—') if session else '—'}</b> ·
  Fase: <b>{phase_id}</b> ·
  {metrics.get('n_ticks', len(ticks))} ticks ·
  {metrics.get('duration_s', round(duration, 1))} s ·
  {metrics.get('laps_completed', laps_completed)} vueltas
</p>
<div class="banner {status_cls}">{status_txt} — {evaluation.get('summary', '')}</div>
<div class="phase-desc">{phase.description if phase else ''}</div>
<div class="stats">
  <div class="stat"><b>{metrics.get('avg_cte', '—')}</b><span>CTE medio (m)</span></div>
  <div class="stat"><b>{metrics.get('avg_speed_kmh', '—')}</b><span>Vel. media (km/h)</span></div>
  <div class="stat"><b>{metrics.get('pct_off_track', 0)}%</b><span>Off-track</span></div>
  <div class="stat"><b>{metrics.get('pct_stuck', 0)}%</b><span>Stuck</span></div>
  <div class="stat"><b>{metrics.get('pct_accel_reason', 0)}%</b><span>Accel intents</span></div>
  <div class="stat"><b>{metrics.get('pct_brake_reason', 0)}%</b><span>Brake intents</span></div>
</div>
<h2>Gráfico de sesión</h2>
<div class="chart-wrap">{chart_svg}</div>
<h2>Criterios de fase</h2>
<table>
  <thead><tr><th>Check</th><th>Valor</th><th>Umbral</th><th>Estado</th></tr></thead>
  <tbody>{checks_rows}</tbody>
</table>
<h2>Intenciones del teacher</h2>
<table>
  <thead><tr><th>reason</th><th>ticks</th></tr></thead>
  <tbody>{reason_rows or '<tr><td colspan="2">—</td></tr>'}</tbody>
</table>
<p class="meta">Fuente: {jsonl_path.name} · Estilo replay inspirado en <a href="https://github.com/doski2/TSW6">TSW6 session_report</a></p>
<script>const DATA = {data_json};</script>
</body></html>"""

    part = out.with_suffix(out.suffix + ".part")
    part.write_text(html, encoding="utf-8")
    part.replace(out)
    return out


def finalize_session_report(
    jsonl_path: Path,
    laps_completed: int = 0,
    open_browser: bool = False,
) -> dict:
    session, ticks, _ = load_session_ticks(jsonl_path)
    phase_id = (session or {}).get("phase", "f1_linea")
    evaluation = evaluate_phase(phase_id, ticks, laps_completed)

    summary_row = {
        "type": "summary",
        "evaluation": evaluation,
        "laps_completed": laps_completed,
    }
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary_row, ensure_ascii=False) + "\n")

    html_path = write_html_replay(jsonl_path, laps_completed=laps_completed)
    result = {
        "jsonl": str(jsonl_path),
        "html": str(html_path) if html_path else None,
        "evaluation": evaluation,
    }

    if html_path:
        print(f"[Report] HTML: {html_path}")
        print(f"[Report] {evaluation.get('summary', '')}")
        if evaluation.get("passed") and evaluation.get("next_phase"):
            print(f"[Report] Siguiente fase sugerida: {evaluation['next_phase']}")
        if open_browser:
            webbrowser.open(html_path.resolve().as_uri())

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera HTML replay desde JSONL teaching")
    parser.add_argument("jsonl", help="Ruta al .jsonl")
    parser.add_argument("--laps", type=int, default=0)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    path = Path(args.jsonl)
    if not path.is_file():
        print(f"[Error] No existe: {path}")
        raise SystemExit(1)

    if args.force:
        session, ticks, summary = load_session_ticks(path)
        phase_id = (session or {}).get("phase", "f1_linea")
        laps = args.laps or (summary or {}).get("laps_completed", 0)
        out = write_html_replay(path, laps_completed=laps)
        if out and args.open:
            webbrowser.open(out.resolve().as_uri())
    else:
        finalize_session_report(path, laps_completed=args.laps, open_browser=args.open)


if __name__ == "__main__":
    main()
