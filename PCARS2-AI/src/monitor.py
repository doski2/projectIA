"""
monitor.py
Dashboard en tiempo real para el entrenamiento PCARS2-AI.

Lee el CSV de métricas y muestra un panel actualizado cada N segundos
con indicadores de tendencia (▲ mejora / ▼ empeora / ─ estable).

Uso:
    python src/monitor.py                              # Auto-detecta el CSV más reciente
    python src/monitor.py logs/formula/metricas.csv   # CSV explícito
    python src/monitor.py --refresh 10                # Actualiza cada 10 s (defecto: 20)
"""

import argparse
import csv
import glob
import os
import sys
import time
from typing import List, Optional, Tuple

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ---------------------------------------------------------------------------
# Constantes de indicadores
# ---------------------------------------------------------------------------

ARROW_UP   = "▲"
ARROW_DOWN = "▼"
ARROW_SAME = "─"

BLOCKS = " ▁▂▃▄▅▆▇█"


# ---------------------------------------------------------------------------
# Búsqueda del CSV más reciente
# ---------------------------------------------------------------------------

def find_latest_csv(logs_dir: str = "logs") -> Optional[str]:
    pattern = os.path.join(logs_dir, "**", "metricas.csv")
    files   = glob.glob(pattern, recursive=True)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


# ---------------------------------------------------------------------------
# Lectura del CSV
# ---------------------------------------------------------------------------

def read_rows(csv_path: str) -> List[dict]:
    rows = []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    except (FileNotFoundError, PermissionError):
        pass
    return rows


# ---------------------------------------------------------------------------
# Utilidades numéricas
# ---------------------------------------------------------------------------

def sfloat(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def sint(val, default: int = 0) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def trend(
    cur: float,
    prev: Optional[float],
    higher_better: bool = True,
    threshold: float = 0.005,
) -> Tuple[str, str]:
    """Devuelve (flecha, color) comparando cur con prev."""
    if prev is None:
        return ARROW_SAME, "dim white"
    diff = cur - prev
    rel  = abs(diff) / (abs(prev) + 1e-9)
    if rel < threshold:
        return ARROW_SAME, "yellow"
    if higher_better:
        return (ARROW_UP, "green") if diff > 0 else (ARROW_DOWN, "red")
    else:
        return (ARROW_DOWN, "green") if diff < 0 else (ARROW_UP, "red")


def sparkline(values: List[float], width: int = 40) -> Text:
    """Mini gráfico ASCII con bloques Unicode."""
    txt = Text()
    if len(values) < 2:
        txt.append("─" * width, style="dim")
        return txt
    mn, mx = min(values), max(values)
    span   = mx - mn if mx != mn else 1.0
    vals   = values[-width:]
    for v in vals:
        idx   = int((v - mn) / span * (len(BLOCKS) - 1))
        block = BLOCKS[idx]
        # color según posición: rojo = peor, verde = mejor
        norm  = (v - mn) / span
        if norm > 0.75:
            style = "bright_green"
        elif norm > 0.4:
            style = "yellow"
        else:
            style = "red"
        txt.append(block, style=style)
    return txt


def health_tag(value: float, lo: float, hi: float) -> Text:
    """Etiqueta de salud: verde si dentro del rango, rojo si fuera."""
    if lo <= value <= hi:
        return Text(" ✓", style="green")
    return Text(" ✗", style="red")


# ---------------------------------------------------------------------------
# Construcción del panel rich
# ---------------------------------------------------------------------------

def build_panel(rows: List[dict], csv_path: str, refresh_sec: int, elapsed: int) -> Panel:
    if not rows:
        # Mostrar info de espera con estado del archivo
        try:
            mtime = os.path.getmtime(csv_path)
            age   = int(time.time() - mtime)
            file_info = f"CSV encontrado · modificado hace {age}s"
        except Exception:
            file_info = "CSV no encontrado aún"
        msg = Text()
        msg.append("Esperando primer rollout (2048 steps)...\n", style="yellow")
        msg.append("  El CSV se escribe cada 2048 pasos, no por episodio.\n", style="dim")
        msg.append(f"  {file_info}", style="dim cyan")
        return Panel(
            msg,
            title="[bold]PCARS2-AI · Monitor[/bold]",
        )

    cur  = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else None

    # ── Métricas actuales ──────────────────────────────────────────────────
    ep_rew   = sfloat(cur.get("ep_rew_mean"))
    ep_len   = sfloat(cur.get("ep_len_mean"))
    fps      = sfloat(cur.get("fps"))
    steps    = sint(cur.get("total_timesteps"))
    iters    = sint(cur.get("iterations"))
    exp_var  = sfloat(cur.get("explained_variance"))
    val_loss = sfloat(cur.get("value_loss"))
    pg_loss  = sfloat(cur.get("policy_gradient_loss"))
    ent_loss = sfloat(cur.get("entropy_loss"))
    std_val  = sfloat(cur.get("std"))
    kl       = sfloat(cur.get("approx_kl"))
    clip_fr  = sfloat(cur.get("clip_fraction"))
    ts       = cur.get("timestamp", "??:??:??")
    n_upd    = sint(cur.get("n_updates"))
    avg_spd  = sfloat(cur.get("avg_speed_kmh"))
    avg_str  = sfloat(cur.get("avg_steering"))
    dist_km  = sfloat(cur.get("dist_km"))
    steps_rollout = sint(cur.get("total_timesteps")) - sint(prev.get("total_timesteps")) if prev else 2048
    n_eps_approx  = max(1.0, steps_rollout / max(1.0, ep_len))
    avg_dist_m    = dist_km * 1000.0 / n_eps_approx

    # ── Métricas anteriores ────────────────────────────────────────────────
    def p(key: str) -> Optional[float]:
        return sfloat(prev.get(key)) if prev else None

    # ── Tendencias ────────────────────────────────────────────────────────
    arr_rew,  col_rew  = trend(ep_rew,   p("ep_rew_mean"),        higher_better=True)
    arr_len,  col_len  = trend(ep_len,   p("ep_len_mean"),        higher_better=True)
    arr_spd,  col_spd  = trend(avg_spd,  p("avg_speed_kmh"),      higher_better=True)
    arr_str,  col_str  = trend(avg_str,  p("avg_steering"),       higher_better=False)
    arr_dist, col_dist = trend(dist_km,  p("dist_km"),            higher_better=True)
    arr_ev,   col_ev   = trend(exp_var,  p("explained_variance"), higher_better=True)
    arr_vl,   col_vl   = trend(val_loss, p("value_loss"),         higher_better=False)
    arr_std,  col_std  = trend(std_val,  p("std"),                higher_better=False)
    arr_kl,   col_kl   = trend(kl,       p("approx_kl"),          higher_better=False)
    arr_clip, col_clip = trend(clip_fr,  p("clip_fraction"),      higher_better=False)

    # ── Tabla: resumen superior ────────────────────────────────────────────
    header = Table(box=None, show_header=False, padding=(0, 1))
    header.add_column(style="dim")
    header.add_column(style="bold cyan")
    header.add_column(style="dim")
    header.add_column(style="bold cyan")
    header.add_column(style="dim")
    header.add_column(style="bold cyan")
    header.add_row(
        "Pasos:", f"{steps:,}",
        "Iteración:", str(iters),
        "FPS:", f"{fps:.0f}",
    )
    header.add_row(
        "Última actualización:", ts,
        "Actualizaciones red:", str(n_upd),
        "Próximo refresco:", f"{refresh_sec - (elapsed % refresh_sec)}s",
    )

    # ── Tabla izquierda: episodio ──────────────────────────────────────────
    t_ep = Table(title="[bold]EPISODIO[/bold]", box=box.SIMPLE, expand=True)
    t_ep.add_column("Métrica",    style="dim",   no_wrap=True)
    t_ep.add_column("Valor",      style="white", justify="right")
    t_ep.add_column("Tendencia",  justify="center", no_wrap=True)
    t_ep.add_column("Objetivo",   style="dim",   justify="center")

    t_ep.add_row(
        "Recompensa media",
        f"{ep_rew:+.1f}",
        Text(arr_rew, style=col_rew),
        "↑ hacia 0",
    )
    t_ep.add_row(
        "Duración media (pasos)",
        f"{ep_len:.0f}",
        Text(arr_len, style=col_len),
        "↑ hacia 6000",
    )
    t_ep.add_row(
        "Velocidad media",
        f"{avg_spd:.1f} km/h" if avg_spd > 0 else "─",
        Text(arr_spd, style=col_spd) if avg_spd > 0 else Text("─", style="dim"),
        "↑ máx posible",
    )
    # avg_steering: <0 = izquierda, >0 = derecha, ~0 = recto
    _str_lbl = f"{avg_str:+.3f} ({'der' if avg_str > 0.02 else 'izq' if avg_str < -0.02 else 'recto'})"
    t_ep.add_row(
        "Dirección media",
        _str_lbl,
        Text(arr_str, style=col_str),
        "→ cerca de 0",
    )
    t_ep.add_row(
        "Dist. media/episodio",
        f"{avg_dist_m:.0f} m" if dist_km > 0 else "─",
        Text(arr_dist, style=col_dist) if dist_km > 0 else Text("─", style="dim"),
        "↑ más distancia",
    )

    # ── Tabla derecha: red neuronal ────────────────────────────────────────
    t_nn = Table(title="[bold]RED NEURONAL[/bold]", box=box.SIMPLE, expand=True)
    t_nn.add_column("Métrica",    style="dim",   no_wrap=True)
    t_nn.add_column("Valor",      style="white", justify="right")
    t_nn.add_column("Tendencia",  justify="center", no_wrap=True)
    t_nn.add_column("Salud",      justify="center")

    t_nn.add_row(
        "Explained Variance",
        f"{exp_var:.4f}",
        Text(arr_ev, style=col_ev),
        health_tag(exp_var, 0.5, 1.0),
    )
    t_nn.add_row(
        "Value Loss",
        f"{val_loss:.4f}",
        Text(arr_vl, style=col_vl),
        health_tag(-val_loss, -500, 0),  # siempre verde (no hay umbral absoluto)
    )
    t_nn.add_row(
        "Policy Gradient Loss",
        f"{pg_loss:+.6f}",
        Text("─", style="dim"),
        Text(" ─", style="dim"),
    )
    t_nn.add_row(
        "Entropía",
        f"{ent_loss:.3f}",
        Text("─", style="dim"),
        health_tag(ent_loss, -7.0, -2.0),
    )
    t_nn.add_row(
        "Std (exploración)",
        f"{std_val:.3f}",
        Text(arr_std, style=col_std),
        Text(" ─", style="dim"),
    )
    t_nn.add_row(
        "Approx KL",
        f"{kl:.6f}",
        Text(arr_kl, style=col_kl),
        health_tag(kl, 0.0, 0.02),
    )
    t_nn.add_row(
        "Clip Fraction",
        f"{clip_fr*100:.1f}%",
        Text(arr_clip, style=col_clip),
        health_tag(clip_fr, 0.05, 0.20),
    )

    # ── Sparkline de ep_rew_mean ──────────────────────────────────────────
    history   = [sfloat(r.get("ep_rew_mean")) for r in rows]
    spark     = sparkline(history, width=min(len(history), 50))
    first_val = f"{history[0]:+.0f}" if history else "?"
    last_val  = f"{history[-1]:+.0f}" if history else "?"

    spark_text = Text()
    spark_text.append(f" {first_val} ", style="dim")
    spark_text.append_text(spark)
    spark_text.append(f" {last_val}", style="bold green" if history[-1] > history[0] else "bold red")

    # ── Barra de progreso hacia 0 ──────────────────────────────────────────
    if history:
        best  = max(history)
        worst = min(history)
        span  = abs(worst) if worst < 0 else 1.0
        pct   = min(100, int((1.0 - abs(best) / span) * 100)) if span > 0 else 0
        pct   = max(0, pct)
        bar_w = 40
        filled = int(bar_w * pct / 100)
        bar_text = Text()
        bar_text.append("[", style="dim")
        bar_text.append("█" * filled, style="green")
        bar_text.append("░" * (bar_w - filled), style="dim")
        bar_text.append(f"] {pct}%", style="dim")
    else:
        bar_text = Text("Sin datos", style="dim")

    # ── Composición final ─────────────────────────────────────────────────
    layout = Layout()
    layout.split_column(
        Layout(name="header",  size=3),
        Layout(name="tables",  size=16),
        Layout(name="spark",   size=4),
    )
    layout["tables"].split_row(
        Layout(name="ep"),
        Layout(name="nn"),
    )
    layout["header"].update(header)
    layout["ep"].update(t_ep)
    layout["nn"].update(t_nn)

    spark_panel = Table(box=None, show_header=False, padding=(0, 0))
    spark_panel.add_column()
    spark_panel.add_row(
        Text(" Historial recompensa (ep_rew_mean):", style="dim")
    )
    spark_panel.add_row(spark_text)
    spark_panel.add_row(bar_text)

    layout["spark"].update(spark_panel)

    csv_name = os.path.relpath(csv_path) if csv_path else "?"
    return Panel(
        layout,
        title=f"[bold cyan]PCARS2-AI · Monitor[/bold cyan]  [dim]│  {csv_name}[/dim]",
        subtitle="[dim]▲ mejor  ▼ peor  ─ estable   ✓ rango saludable  │  Ctrl+C para salir[/dim]",
        border_style="cyan",
    )


# ---------------------------------------------------------------------------
# Bucle principal
# ---------------------------------------------------------------------------

def run(csv_path: str, refresh_sec: int) -> None:
    console   = Console()
    start     = time.time()
    rows      = read_rows(csv_path)
    last_read = time.time()

    with Live(console=console, refresh_per_second=2, screen=True) as live:
        while True:
            now = time.time()
            if now - last_read >= refresh_sec:
                rows      = read_rows(csv_path)
                last_read = now
            elapsed = int(now - start)
            panel   = build_panel(rows, csv_path, refresh_sec, elapsed)
            live.update(panel)
            time.sleep(1)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="PCARS2-AI — Dashboard de entrenamiento en tiempo real",
    )
    parser.add_argument(
        "csv",
        nargs="?",
        default=None,
        help="Ruta al CSV de métricas (por defecto: auto-detecta el más reciente en logs/)",
    )
    parser.add_argument(
        "--refresh", "-r",
        type=int,
        default=20,
        metavar="SEGUNDOS",
        help="Intervalo de actualización en segundos (defecto: 20)",
    )
    args = parser.parse_args()

    # Determinar ruta del CSV
    csv_path = args.csv
    if csv_path is None:
        # Buscar relativo a la carpeta del proyecto (un nivel arriba de src/)
        script_dir  = os.path.dirname(os.path.abspath(__file__))
        project_dir = os.path.dirname(script_dir)
        logs_dir    = os.path.join(project_dir, "logs")
        csv_path    = find_latest_csv(logs_dir)
        if csv_path is None:
            print("[monitor] No se encontró ningún metricas.csv en logs/")
            print("          Usa: python src/monitor.py <ruta/metricas.csv>")
            sys.exit(1)
        print(f"[monitor] CSV detectado: {csv_path}")

    if not os.path.isfile(csv_path):
        print(f"[monitor] Archivo no encontrado: {csv_path}")
        sys.exit(1)

    print(f"[monitor] Iniciando dashboard (refresco cada {args.refresh}s) — Ctrl+C para salir")
    time.sleep(0.5)

    try:
        run(csv_path, args.refresh)
    except KeyboardInterrupt:
        print("\n[monitor] Saliendo.")


if __name__ == "__main__":
    main()
