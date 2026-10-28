"""Pestaña Experimental de la GUI (v2.gui la carga de forma opcional)."""

from __future__ import annotations

import os
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

_ROOT = Path(__file__).resolve().parent
_REPO = _ROOT.parent
_PYTHON = _REPO / ".venv" / "Scripts" / "python.exe"

_INTRO = (
    "Zona de pruebas separada del código que ya funciona.\n"
    "Los logs de sesión van a PCARS2-AI/logs/ y se distinguen por la cabecera "
    "(origin, experiment, log_schema)."
)

_IDEAS = (
    ("C · Rampa continua del BC", "Sin empezar. Ver docs/PLAN_C_RAMPA_BC.md"),
    ("A · Límites del coche", "Sin empezar. Ver docs/PLAN_A_LIMITES_COCHE.md"),
    ("B · Simulador aprendido", "En espera. Ver docs/PLAN_B_SIMULADOR.md"),
)


def launch_c0(speed_band: float, laps: int, teacher_only: bool = False) -> None:
    """Abre una consola con la prueba C0 (aislada: modelo/buffer en copia, progreso restaurado)."""
    experiment = f"teacher_{speed_band:g}" if teacher_only else "c0_log"  # una por banda: no se pisan log ni buffer
    argv = [
        str(_PYTHON), str(_ROOT / "common" / "aislado.py"),
        "--experiment", experiment, "--speed-band", f"{speed_band:g}", "--laps", str(laps),
    ]
    if teacher_only:
        argv.append("--teacher-only")
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    subprocess.Popen(
        f'start "Experimental C0" cmd /k {subprocess.list2cmdline(argv)}', shell=True, cwd=str(_REPO), env=env,
    )


def launch_pasivo(name: str, minutes: float, after_damage: float) -> None:
    """Abre una consola con el registro pasivo: graba el log ampliado mientras conduces tú."""
    argv = [
        str(_PYTHON), str(_ROOT / "common" / "registro_pasivo.py"),
        "--name", name, "--minutes", f"{minutes:g}", "--after-damage", f"{after_damage:g}",
    ]
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    subprocess.Popen(
        f'start "Experimental registro pasivo" cmd /k {subprocess.list2cmdline(argv)}',
        shell=True, cwd=str(_REPO), env=env,
    )


def build_tab(notebook: ttk.Notebook) -> ttk.Frame:
    tab = ttk.Frame(notebook)

    ttk.Label(tab, text=_INTRO, wraplength=680, justify="left").pack(anchor="w", padx=14, pady=(14, 8))

    frame = ttk.LabelFrame(tab, text="Experimentos")
    frame.pack(fill="x", padx=14, pady=6)
    for name, status in _IDEAS:
        row = ttk.Frame(frame)
        row.pack(fill="x", padx=8, pady=3)
        ttk.Label(row, text=name, width=30).pack(side="left")
        ttk.Label(row, text=status).pack(side="left")

    c0 = ttk.LabelFrame(tab, text="C0 · Verificar el log ampliado")
    c0.pack(fill="x", padx=14, pady=6)
    ttk.Label(
        c0,
        text=(
            "Conduce unas vueltas con el BC en una copia del modelo y del buffer, sin fine-tune. "
            "El progreso de aprendizaje se restaura al terminar. Requiere el juego en parrilla."
        ),
        wraplength=660, justify="left",
    ).pack(anchor="w", padx=8, pady=(6, 2))
    form = ttk.Frame(c0)
    form.pack(anchor="w", padx=8, pady=6)
    band = tk.StringVar(value="40")
    laps = tk.StringVar(value="2")
    ttk.Label(form, text="Banda (km/h)").pack(side="left")
    ttk.Entry(form, textvariable=band, width=6).pack(side="left", padx=(4, 14))
    ttk.Label(form, text="Vueltas").pack(side="left")
    ttk.Entry(form, textvariable=laps, width=4).pack(side="left", padx=(4, 14))
    teacher_only = tk.BooleanVar(value=False)
    ttk.Checkbutton(form, text="Conduce el profesor (sin BC)", variable=teacher_only).pack(side="left", padx=(0, 14))

    def _go() -> None:
        try:
            launch_c0(float(band.get()), int(laps.get()), teacher_only.get())
        except ValueError:
            messagebox.showerror("C0", "Banda y vueltas deben ser números.")

    ttk.Button(form, text="Lanzar C0", command=_go).pack(side="left")

    pas = ttk.LabelFrame(tab, text="Registro pasivo · conduces tú")
    pas.pack(fill="x", padx=14, pady=6)
    ttk.Label(
        pas,
        text=(
            "Graba el log ampliado sin enviar ningún mando: sirve para un golpe controlado (ver los canales de daño) "
            "o un rodaje largo (desgaste). Tras el primer daño sigue grabando los segundos indicados."
        ),
        wraplength=660, justify="left",
    ).pack(anchor="w", padx=8, pady=(6, 2))
    pform = ttk.Frame(pas)
    pform.pack(anchor="w", padx=8, pady=6)
    pname = tk.StringVar(value="golpe")
    pmin = tk.StringVar(value="10")
    pafter = tk.StringVar(value="20")
    for label, var, width in (("Nombre", pname, 10), ("Minutos", pmin, 5), ("Seguir tras daño (s)", pafter, 5)):
        ttk.Label(pform, text=label).pack(side="left")
        ttk.Entry(pform, textvariable=var, width=width).pack(side="left", padx=(4, 14))

    def _go_pasivo() -> None:
        try:
            launch_pasivo(pname.get().strip() or "golpe", float(pmin.get()), float(pafter.get()))
        except ValueError:
            messagebox.showerror("Registro pasivo", "Minutos y segundos deben ser números.")

    ttk.Button(pform, text="Lanzar registro pasivo", command=_go_pasivo).pack(side="left")

    buttons = ttk.Frame(tab)
    buttons.pack(anchor="w", padx=14, pady=10)
    ttk.Button(
        buttons, text="Abrir documentos", command=lambda: os.startfile(_ROOT / "docs")  # type: ignore[attr-defined]
    ).pack(side="left")
    return tab
