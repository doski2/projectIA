"""
PCARS2-AI v2 — GUI de entrenamiento.

Uso:
    python -m v2.gui
    o gui.bat desde la raíz de PCARS2-AI
"""

from __future__ import annotations

import sys
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from learning_curriculum import resolve_learn_speed, stage_blurb  # noqa: E402

from .config import (
    LEARN_STAGE_IDS,
    SPEED_BANDS_KMH,
    TRAINING_MODES,
    LearnSettings,
    TeachingSettings,
    TrainingSettings,
    apply_mode_defaults,
    get_mode,
)
from .launcher import (
    find_latest_checkpoint,
    format_command,
    format_learn_command,
    launch_eval_bc,
    launch_learn,
    launch_monitor,
    launch_pretrain_bc,
    launch_teaching,
    launch_tensorboard,
    launch_training,
    list_references,
    load_learn_settings,
    load_settings,
    project_root,
    save_learn_settings,
    venv_python,
)


class TrainingGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PCARS2-AI v2 — Entrenamiento y Aprendizaje")
        self.minsize(760, 680)
        self.settings = load_settings() or TrainingSettings()
        self.teaching_settings = TeachingSettings()
        self.learn_settings = load_learn_settings() or LearnSettings()
        self._normalize_learn_settings()

        if not venv_python().is_file():
            messagebox.showwarning(
                "Venv no encontrado",
                f"No existe: {venv_python()}\n\n"
                "Crea el entorno:\n"
                "  python -m venv ..\\.venv\n"
                "  ..\\.venv\\Scripts\\pip install -r requirements.txt",
            )

        self._build_ui()
        self._populate_refs()
        self._apply_settings_to_ui()
        self._on_mode_change()
        self._on_learn_settings_change()

    def _build_ui(self) -> None:
        header = ttk.Label(
            self,
            text="PCARS2-AI v2",
            font=("Segoe UI", 16, "bold"),
        )
        header.pack(anchor="w", padx=12, pady=(12, 0))

        subtitle = ttk.Label(
            self,
            text="RL (PPO) o Aprendizaje BC (Teaching → dataset → BC → online).",
            font=("Segoe UI", 9),
        )
        subtitle.pack(anchor="w", padx=12, pady=(0, 8))

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=12, pady=6)

        self.rl_tab = ttk.Frame(notebook)
        self.learn_tab = ttk.Frame(notebook)
        notebook.add(self.rl_tab, text="RL (PPO)")
        notebook.add(self.learn_tab, text="Aprendizaje (BC)")

        self._build_rl_tab()
        self._build_learn_tab()

    def _build_rl_tab(self) -> None:
        px, py = 10, 4
        parent = self.rl_tab

        mode_frame = ttk.LabelFrame(parent, text="Modo de entrenamiento")
        mode_frame.pack(fill="x", padx=4, pady=6)

        self.mode_var = tk.StringVar(value=self.settings.mode_id)
        for mode in TRAINING_MODES:
            ttk.Radiobutton(
                mode_frame,
                text=mode.label,
                value=mode.id,
                variable=self.mode_var,
                command=self._on_mode_change,
            ).pack(anchor="w", padx=8, pady=2)

        self.mode_desc = ttk.Label(mode_frame, text="", wraplength=700, foreground="#444")
        self.mode_desc.pack(anchor="w", padx=8, pady=(4, 8))

        speed_frame = ttk.LabelFrame(parent, text="Velocidad objetivo (km/h)")
        speed_frame.pack(fill="x", padx=4, pady=6)

        row = ttk.Frame(speed_frame)
        row.pack(fill="x", padx=8, pady=8)

        self.speed_var = tk.DoubleVar(value=self.settings.speed_target_kmh)
        self.speed_scale = ttk.Scale(
            row,
            from_=10,
            to=80,
            orient="horizontal",
            variable=self.speed_var,
            command=self._on_speed_scale,
        )
        self.speed_scale.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.speed_spin = ttk.Spinbox(
            row,
            from_=0,
            to=150,
            increment=5,
            width=6,
            textvariable=self.speed_var,
            command=self._update_command_preview,
        )
        self.speed_spin.pack(side="left")
        self.speed_spin.bind("<KeyRelease>", lambda _e: self._update_command_preview())

        ttk.Label(
            speed_frame,
            text="0 = sin objetivo de velocidad. En modo Básicos empieza en 20 km/h.",
            foreground="#666",
        ).pack(anchor="w", padx=8, pady=(0, 6))

        opts = ttk.LabelFrame(parent, text="Ajustes")
        opts.pack(fill="x", padx=4, pady=6)

        grid = ttk.Frame(opts)
        grid.pack(fill="x", padx=8, pady=8)
        grid.grid_columnconfigure(index=1, weight=1)

        ttk.Label(grid, text="Referencia:").grid(row=0, column=0, sticky="w", padx=px, pady=py)
        self.ref_var = tk.StringVar(value=self.settings.reference)
        ref_row = ttk.Frame(grid)
        ref_row.grid(row=0, column=1, sticky="ew", padx=px, pady=py)
        ref_row.grid_columnconfigure(index=0, weight=1)
        self.ref_combo = ttk.Combobox(ref_row, textvariable=self.ref_var)
        self.ref_combo.grid(row=0, column=0, sticky="ew")
        ttk.Button(ref_row, text="…", width=3, command=self._browse_reference).grid(
            row=0, column=1, padx=(4, 0)
        )

        ttk.Label(grid, text="Pasos (timesteps):").grid(row=1, column=0, sticky="w", padx=px, pady=py)
        self.steps_var = tk.IntVar(value=self.settings.timesteps)
        ttk.Spinbox(
            grid, from_=50_000, to=2_000_000, increment=50_000, width=12,
            textvariable=self.steps_var,
        ).grid(row=1, column=1, sticky="w", padx=px, pady=py)

        ttk.Label(grid, text="Frame skip:").grid(row=2, column=0, sticky="w", padx=px, pady=py)
        self.frame_skip_var = tk.IntVar(value=self.settings.frame_skip)
        ttk.Spinbox(
            grid, from_=1, to=8, width=6, textvariable=self.frame_skip_var,
        ).grid(row=2, column=1, sticky="w", padx=px, pady=py)

        ttk.Label(grid, text="Warm-up (frames):").grid(row=3, column=0, sticky="w", padx=px, pady=py)
        self.warmup_var = tk.IntVar(value=self.settings.warmup_steps)
        ttk.Spinbox(
            grid, from_=0, to=120, width=6, textvariable=self.warmup_var,
        ).grid(row=3, column=1, sticky="w", padx=px, pady=py)

        ttk.Label(grid, text="Combo (coche / pista):").grid(row=4, column=0, sticky="w", padx=px, pady=py)
        combo_row = ttk.Frame(grid)
        combo_row.grid(row=4, column=1, sticky="w", padx=px, pady=py)
        self.car_var = tk.StringVar(value=self.settings.car)
        self.track_var = tk.StringVar(value=self.settings.track)
        ttk.Entry(combo_row, textvariable=self.car_var, width=18).pack(side="left")
        ttk.Label(combo_row, text="__").pack(side="left", padx=4)
        ttk.Entry(combo_row, textvariable=self.track_var, width=12).pack(side="left")

        ttk.Label(grid, text="Checkpoint (--model):").grid(row=5, column=0, sticky="w", padx=px, pady=py)
        model_row = ttk.Frame(grid)
        model_row.grid(row=5, column=1, sticky="ew", padx=px, pady=py)
        model_row.grid_columnconfigure(index=0, weight=1)
        self.model_var = tk.StringVar(value=self.settings.model_path)
        ttk.Entry(model_row, textvariable=self.model_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(model_row, text="Último", command=self._pick_latest_model).grid(
            row=0, column=1, padx=4
        )
        ttk.Button(model_row, text="…", width=3, command=self._browse_model).grid(
            row=0, column=2
        )

        self.fresh_var = tk.BooleanVar(value=self.settings.fresh_start)
        fresh_row = ttk.Frame(grid)
        fresh_row.grid(row=6, column=1, sticky="w", padx=px, pady=py)
        ttk.Checkbutton(
            fresh_row,
            text="Desde cero (--fresh): nueva política, sin cargar checkpoints",
            variable=self.fresh_var,
            command=self._on_fresh_toggle,
        ).pack(anchor="w")

        cmd_frame = ttk.LabelFrame(parent, text="Comando generado (RL)")
        cmd_frame.pack(fill="both", expand=True, padx=4, pady=6)

        self.cmd_text = tk.Text(cmd_frame, height=4, wrap="word", font=("Consolas", 9))
        self.cmd_text.pack(fill="both", expand=True, padx=8, pady=8)

        btn_row = ttk.Frame(parent)
        btn_row.pack(fill="x", padx=4, pady=8)

        ttk.Button(
            btn_row, text="▶ Iniciar entrenamiento", command=self._start_training
        ).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="Monitor", command=self._open_monitor).pack(side="left", padx=4)
        ttk.Button(btn_row, text="TensorBoard", command=self._open_tb).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Actualizar comando", command=self._update_command_preview).pack(
            side="left", padx=8
        )

        for var in (
            self.ref_var, self.steps_var, self.frame_skip_var, self.warmup_var,
            self.car_var, self.track_var, self.model_var,
        ):
            if hasattr(var, "trace_add"):
                var.trace_add("write", lambda *_a: self._update_command_preview())

    def _build_learn_tab(self) -> None:
        px, py = 10, 4
        parent = self.learn_tab

        guide = ttk.LabelFrame(parent, text="Aprendizaje BC — pasos (solo la 1ª vez hace falta preparar)")
        guide.pack(fill="x", padx=4, pady=6)

        ttk.Label(
            guide,
            text=(
                "1) Graba al teacher conduciendo bien  ·  "
                "2) Entrena el modelo BC  ·  "
                "3) Aprende en pista (L1→L7 por banda 20→80 km/h)  ·  "
                "4) Prueba Hybrid/Autónomo al dominar L7 (panel de abajo, velocidad propia)"
            ),
            wraplength=700,
            justify="left",
        ).pack(anchor="w", padx=8, pady=(8, 4))

        setup_row = ttk.Frame(guide)
        setup_row.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(setup_row, text="Grabar teacher", command=self._start_record).pack(side="left", padx=2)
        ttk.Button(setup_row, text="Entrenar BC", command=self._start_pretrain_bc).pack(side="left", padx=2)

        session = ttk.LabelFrame(parent, text="Sesión en pista — banda de velocidad y etapa")
        session.pack(fill="x", padx=4, pady=6)

        grid = ttk.Frame(session)
        grid.pack(fill="x", padx=8, pady=8)
        grid.grid_columnconfigure(index=1, weight=1)

        ttk.Label(grid, text="Referencia:").grid(row=0, column=0, sticky="w", padx=px, pady=py)
        self.learn_ref_var = tk.StringVar(value=self.learn_settings.reference)
        learn_ref_row = ttk.Frame(grid)
        learn_ref_row.grid(row=0, column=1, sticky="ew", padx=px, pady=py)
        learn_ref_row.grid_columnconfigure(index=0, weight=1)
        self.learn_ref_combo = ttk.Combobox(learn_ref_row, textvariable=self.learn_ref_var)
        self.learn_ref_combo.grid(row=0, column=0, sticky="ew")
        ttk.Button(
            learn_ref_row, text="…", width=3, command=self._browse_learn_reference,
        ).grid(row=0, column=1, padx=(4, 0))

        ttk.Label(grid, text="Banda (km/h):").grid(row=1, column=0, sticky="w", padx=px, pady=py)
        band_row = ttk.Frame(grid)
        band_row.grid(row=1, column=1, sticky="w", padx=px, pady=py)
        self.learn_band_var = tk.DoubleVar(value=self.learn_settings.speed_band_kmh)
        band_combo = ttk.Combobox(
            band_row,
            textvariable=self.learn_band_var,
            values=[str(int(b)) for b in SPEED_BANDS_KMH],
            state="readonly",
            width=6,
        )
        band_combo.pack(side="left")
        band_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_learn_band_change())
        ttk.Label(
            band_row,
            text="Teacher a esta velocidad en L1–L7",
            foreground="#666",
        ).pack(side="left", padx=8)

        ttk.Label(grid, text="Etapa (L1→L7):").grid(row=2, column=0, sticky="w", padx=px, pady=py)
        self.learn_stage_var = tk.StringVar(value=self.learn_settings.stage_id)
        stage_combo = ttk.Combobox(
            grid,
            textvariable=self.learn_stage_var,
            values=LEARN_STAGE_IDS,
            state="readonly",
            width=22,
        )
        stage_combo.grid(row=2, column=1, sticky="w", padx=px, pady=py)
        stage_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_learn_settings_change())

        self.learn_speed_hint = ttk.Label(grid, text="", foreground="#666")
        self.learn_speed_hint.grid(row=3, column=1, sticky="w", padx=px, pady=py)

        self.learn_steer_comp_var = tk.BooleanVar(value=self.learn_settings.steer_comp)
        ttk.Checkbutton(
            grid,
            text="Compensar curva del volante (experimental)",
            variable=self.learn_steer_comp_var,
            command=self._on_learn_settings_change,
        ).grid(row=4, column=1, sticky="w", padx=px, pady=py)

        self.learn_stage_desc = ttk.Label(
            session, text="", wraplength=700, foreground="#444", justify="left",
        )
        self.learn_stage_desc.pack(anchor="w", padx=8, pady=(0, 8))

        action_row = ttk.Frame(session)
        action_row.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(
            action_row,
            text="▶ Aprender en pista",
            command=self._start_learn,
        ).pack(side="left", padx=(0, 8))

        ttk.Label(
            session,
            text="Avanza solo con vueltas limpias. Al cruzar meta el coche frena mientras el BC se actualiza.",
            foreground="#666",
            wraplength=700,
        ).pack(anchor="w", padx=8, pady=(0, 8))

        hybrid = ttk.LabelFrame(parent, text="Hybrid / Autónomo — valida sin entrenar")
        hybrid.pack(fill="x", padx=4, pady=6)
        hgrid = ttk.Frame(hybrid)
        hgrid.pack(fill="x", padx=8, pady=8)

        ttk.Label(hgrid, text="Velocidad (km/h):").grid(row=0, column=0, sticky="w", padx=px, pady=py)
        self.hybrid_speed_var = tk.StringVar(value="20")
        ttk.Combobox(
            hgrid,
            textvariable=self.hybrid_speed_var,
            values=[str(int(b)) for b in SPEED_BANDS_KMH],
            state="readonly",
            width=6,
        ).grid(row=0, column=1, sticky="w", padx=px, pady=py)
        ttk.Label(
            hgrid,
            text="Independiente de la banda de aprendizaje (tras L7 la banda sube sola)",
            foreground="#666",
        ).grid(row=0, column=2, sticky="w", padx=px, pady=py)

        ttk.Label(hgrid, text="Mezcla BC (alpha):").grid(row=1, column=0, sticky="w", padx=px, pady=py)
        self.hybrid_alpha_var = tk.DoubleVar(value=0.7)
        ttk.Spinbox(
            hgrid, from_=0.0, to=1.0, increment=0.1, width=6,
            textvariable=self.hybrid_alpha_var,
        ).grid(row=1, column=1, sticky="w", padx=px, pady=py)

        ttk.Label(hgrid, text="Vueltas limpias p/ graduar:").grid(row=2, column=0, sticky="w", padx=px, pady=py)
        self.hybrid_grad_var = tk.IntVar(value=5)
        ttk.Spinbox(
            hgrid, from_=1, to=20, width=6, textvariable=self.hybrid_grad_var,
        ).grid(row=2, column=1, sticky="w", padx=px, pady=py)

        ttk.Label(hgrid, text="Máx. vueltas (0 = sin límite):").grid(row=3, column=0, sticky="w", padx=px, pady=py)
        self.hybrid_laps_var = tk.IntVar(value=0)
        ttk.Spinbox(
            hgrid, from_=0, to=100, width=6, textvariable=self.hybrid_laps_var,
        ).grid(row=3, column=1, sticky="w", padx=px, pady=py)

        hrow = ttk.Frame(hybrid)
        hrow.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(
            hrow, text="▶ Probar Hybrid", command=self._start_hybrid,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            hrow, text="▶ Autónomo (BC sin teacher)", command=self._start_autonomous,
        ).pack(side="left", padx=2)
        ttk.Label(
            hybrid,
            text="Hybrid gradúa solo a Autónomo tras N vueltas limpias seguidas. No entrena ni modifica el modelo.",
            foreground="#666",
            wraplength=700,
        ).pack(anchor="w", padx=8, pady=(0, 8))

        advanced = ttk.LabelFrame(parent, text="Avanzado (rutas; normalmente no hace falta tocar)")
        advanced.pack(fill="both", expand=True, padx=4, pady=6)

        adv = ttk.Frame(advanced)
        adv.pack(fill="x", padx=8, pady=8)
        adv.grid_columnconfigure(index=1, weight=1)

        ttk.Label(adv, text="Modelo BC (.pt):").grid(row=0, column=0, sticky="w", padx=px, pady=py)
        self.learn_model_var = tk.StringVar(value=self.learn_settings.model_path)
        ttk.Entry(adv, textvariable=self.learn_model_var).grid(
            row=0, column=1, sticky="ew", padx=px, pady=py,
        )

        ttk.Label(adv, text="Dataset teacher:").grid(row=1, column=0, sticky="w", padx=px, pady=py)
        self.learn_dataset_var = tk.StringVar(value=self.learn_settings.dataset_path)
        ttk.Entry(adv, textvariable=self.learn_dataset_var).grid(
            row=1, column=1, sticky="ew", padx=px, pady=py,
        )

        ttk.Label(adv, text="Override velocidad (km/h):").grid(
            row=2, column=0, sticky="w", padx=px, pady=py,
        )
        override_row = ttk.Frame(adv)
        override_row.grid(row=2, column=1, sticky="w", padx=px, pady=py)
        self.learn_speed_var = tk.DoubleVar(value=self.learn_settings.speed_target_kmh)
        ttk.Spinbox(
            override_row,
            from_=0,
            to=60,
            increment=5,
            width=6,
            textvariable=self.learn_speed_var,
            command=self._on_learn_settings_change,
        ).pack(side="left")
        ttk.Label(override_row, text="0 = usa banda (normalmente no tocar)").pack(side="left", padx=8)

        adv_btn = ttk.Frame(advanced)
        adv_btn.pack(fill="x", padx=8, pady=(0, 4))
        ttk.Button(adv_btn, text="Eval BC (offline)", command=self._start_eval_bc).pack(side="left")

        self.learn_cmd_text = tk.Text(advanced, height=2, wrap="word", font=("Consolas", 9))
        self.learn_cmd_text.pack(fill="x", padx=8, pady=(4, 8))

        for var in (
            self.learn_ref_var,
            self.learn_band_var,
            self.learn_stage_var,
            self.learn_model_var,
            self.learn_dataset_var,
            self.learn_speed_var,
        ):
            if hasattr(var, "trace_add"):
                var.trace_add("write", lambda *_a: self._on_learn_settings_change())

    def _normalize_learn_settings(self) -> None:
        """Migrar ajustes antiguos: velocidad principal → banda; override solo si difiere."""
        s = self.learn_settings
        if s.speed_band_kmh <= 0:
            s.speed_band_kmh = 20.0
        if s.speed_target_kmh > 0 and abs(s.speed_target_kmh - s.speed_band_kmh) < 0.5:
            s.speed_target_kmh = 0.0

    def _populate_refs(self) -> None:
        refs = list_references()
        if refs:
            self.ref_combo["values"] = refs
            self.learn_ref_combo["values"] = refs
            if self.settings.reference not in refs:
                self.ref_var.set(refs[0])
            if self.learn_settings.reference not in refs:
                self.learn_ref_var.set(refs[0])

    def _apply_settings_to_ui(self) -> None:
        self.mode_var.set(self.settings.mode_id)
        self.speed_var.set(self.settings.speed_target_kmh)
        self.ref_var.set(self.settings.reference)
        self.steps_var.set(self.settings.timesteps)
        self.frame_skip_var.set(self.settings.frame_skip)
        self.warmup_var.set(self.settings.warmup_steps)
        self.car_var.set(self.settings.car)
        self.track_var.set(self.settings.track)
        self.model_var.set(self.settings.model_path)
        self.fresh_var.set(self.settings.fresh_start)
        if hasattr(self, "learn_ref_var"):
            self.learn_ref_var.set(self.learn_settings.reference)
            self.learn_band_var.set(self.learn_settings.speed_band_kmh)
            self.learn_stage_var.set(self.learn_settings.stage_id)
            self.learn_speed_var.set(self.learn_settings.speed_target_kmh)
            self.learn_model_var.set(self.learn_settings.model_path)
            self.learn_dataset_var.set(self.learn_settings.dataset_path)

    def _collect_settings(self) -> TrainingSettings:
        return TrainingSettings(
            reference=self.ref_var.get().strip(),
            timesteps=int(self.steps_var.get()),
            speed_target_kmh=float(self.speed_var.get()),
            frame_skip=int(self.frame_skip_var.get()),
            warmup_steps=int(self.warmup_var.get()),
            car=self.car_var.get().strip() or "formula_rookie",
            track=self.track_var.get().strip() or "sugo",
            model_path=self.model_var.get().strip(),
            fresh_start=bool(self.fresh_var.get()),
            mode_id=self.mode_var.get(),
        )

    def _effective_learn_speed(self) -> float:
        stage_id = self.learn_stage_var.get().strip()
        band = float(self.learn_band_var.get())
        override = float(self.learn_speed_var.get())
        return resolve_learn_speed(stage_id, band, override)

    def _collect_learn_settings(self) -> LearnSettings:
        return LearnSettings(
            reference=self.learn_ref_var.get().strip(),
            stage_id=self.learn_stage_var.get().strip(),
            model_path=self.learn_model_var.get().strip(),
            dataset_path=self.learn_dataset_var.get().strip(),
            gamepad="xbox",
            open_report=True,
            speed_band_kmh=float(self.learn_band_var.get()),
            speed_target_kmh=float(self.learn_speed_var.get()),
            steer_comp=bool(self.learn_steer_comp_var.get()),
        )

    def _persist_learn_settings(self) -> None:
        save_learn_settings(self._collect_learn_settings())

    def _current_learn_band(self) -> float:
        try:
            return float(self.learn_band_var.get())
        except (tk.TclError, ValueError):
            return 20.0

    def _update_learn_speed_hint(self) -> None:
        stage_id = self.learn_stage_var.get().strip()
        band = self._current_learn_band()
        override = float(self.learn_speed_var.get())
        effective = resolve_learn_speed(stage_id, band, override)
        if override > 0:
            self.learn_speed_hint.config(
                text=f"Teacher a {effective:.0f} km/h (override; banda {band:.0f})",
            )
        else:
            self.learn_speed_hint.config(text=f"Teacher a {effective:.0f} km/h (banda fija)")

    def _on_learn_band_change(self) -> None:
        band = self._current_learn_band()
        stage_id = self.learn_stage_var.get().strip()
        self.learn_stage_desc.config(text=stage_blurb(stage_id, band))
        self._update_learn_speed_hint()
        self._persist_learn_settings()
        self._update_learn_command()

    def _on_learn_settings_change(self) -> None:
        stage_id = self.learn_stage_var.get().strip()
        band = self._current_learn_band()
        self.learn_stage_desc.config(text=stage_blurb(stage_id, band))
        self._update_learn_speed_hint()
        self._persist_learn_settings()
        self._update_learn_command()

    def _update_learn_command(self) -> None:
        cmd = format_learn_command(self._collect_learn_settings())
        self.learn_cmd_text.delete("1.0", "end")
        self.learn_cmd_text.insert("1.0", cmd)

    def _on_mode_change(self) -> None:
        mode = get_mode(self.mode_var.get())
        self.mode_desc.config(text=mode.description)

        if mode.id != "personalizado":
            s = TrainingSettings(mode_id=mode.id)
            apply_mode_defaults(s)
            self.speed_var.set(s.speed_target_kmh)
            self.steps_var.set(s.timesteps)
            self.frame_skip_var.set(s.frame_skip)
            self.warmup_var.set(s.warmup_steps)

        self._update_command_preview()
        self._update_learn_command()

    def _on_speed_scale(self, _value: str) -> None:
        self._update_command_preview()

    def _on_fresh_toggle(self) -> None:
        if self.fresh_var.get():
            self.model_var.set("")
        self._update_command_preview()

    def _update_command_preview(self) -> None:
        settings = self._collect_settings()
        cmd = format_command(settings)
        self.cmd_text.delete("1.0", "end")
        self.cmd_text.insert("1.0", cmd)
        self._update_learn_command()

    def _browse_reference(self) -> None:
        self._pick_reference_file(self.ref_var, self._update_command_preview)

    def _browse_learn_reference(self) -> None:
        self._pick_reference_file(self.learn_ref_var, self._on_learn_settings_change)

    def _pick_reference_file(self, var: tk.StringVar, on_set) -> None:
        root = project_root()
        path = filedialog.askopenfilename(
            title="Archivo de referencia",
            initialdir=str(root / "src" / "refs"),
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
        )
        if path:
            try:
                rel = Path(path).resolve().relative_to(root.resolve())
                var.set(str(rel).replace("\\", "/"))
            except ValueError:
                var.set(path)
            on_set()

    def _browse_model(self) -> None:
        root = project_root()
        self.fresh_var.set(False)
        path = filedialog.askopenfilename(
            title="Checkpoint del modelo",
            initialdir=str(root / "models"),
            filetypes=[("ZIP", "*.zip"), ("Todos", "*.*")],
        )
        if path:
            if path.lower().endswith(".zip"):
                path = path[:-4]
            try:
                rel = Path(path).resolve().relative_to(root.resolve())
                self.model_var.set(str(rel).replace("\\", "/"))
            except ValueError:
                self.model_var.set(path)
            self._update_command_preview()

    def _pick_latest_model(self) -> None:
        settings = self._collect_settings()
        latest = find_latest_checkpoint(settings.combo())
        if latest:
            self.fresh_var.set(False)
            root = project_root()
            try:
                rel = Path(latest).resolve().relative_to(root.resolve())
                self.model_var.set(str(rel).replace("\\", "/"))
            except ValueError:
                self.model_var.set(latest)
            self._update_command_preview()
        else:
            messagebox.showinfo(
                "Sin checkpoint",
                f"No hay checkpoints en models/{settings.combo()}/",
            )

    def _check_venv(self) -> bool:
        if not venv_python().is_file():
            messagebox.showerror("Error", f"Python del venv no encontrado:\n{venv_python()}")
            return False
        return True

    def _check_reference(self, reference: str) -> bool:
        ref_path = project_root() / reference
        if not ref_path.is_file():
            messagebox.showerror("Error", f"Referencia no encontrada:\n{ref_path}")
            return False
        return True

    def _check_bc_model(self, model_path: str) -> bool:
        path = project_root() / model_path
        if model_path.endswith(".pt"):
            if not path.is_file():
                messagebox.showerror("Error", f"Modelo BC no encontrado:\n{path}")
                return False
            return True
        zip_path = project_root() / f"{model_path}.zip"
        if not zip_path.is_file():
            messagebox.showerror("Error", f"Modelo BC no encontrado:\n{zip_path}")
            return False
        return True

    def _start_record(self) -> None:
        self._persist_learn_settings()
        settings = TeachingSettings(
            reference=self.learn_ref_var.get().strip(),
            speed_target_kmh=self._effective_learn_speed(),
            mode_id="record",
            dataset_output=self.learn_dataset_var.get().strip(),
        )
        if not self._check_reference(settings.reference) or not self._check_venv():
            return
        launch_teaching(settings)
        messagebox.showinfo("Record", "Consola abierta. Graba demostraciones del teacher.")

    def _start_pretrain_bc(self) -> None:
        if not self._check_venv():
            return
        dataset = self.learn_dataset_var.get().strip()
        model = self.learn_model_var.get().strip()
        ds_path = project_root() / dataset
        if not ds_path.is_file():
            messagebox.showerror("Error", f"Dataset no encontrado:\n{ds_path}")
            return
        launch_pretrain_bc(dataset=dataset, output=model)
        messagebox.showinfo("Entrenar BC", "Entrenamiento offline en consola.")

    def _start_eval_bc(self) -> None:
        if not self._check_venv():
            return
        dataset = self.learn_dataset_var.get().strip()
        model = self.learn_model_var.get().strip()
        if not self._check_bc_model(model):
            return
        launch_eval_bc(dataset=dataset, model=model)
        messagebox.showinfo("Eval BC", "Evaluación offline en consola.")

    def _start_learn(self) -> None:
        settings = self._collect_learn_settings()
        if not self._check_reference(settings.reference) or not self._check_venv():
            return
        launch_learn(settings)
        messagebox.showinfo(
            "Aprendizaje online",
            "Consola abierta.\nAl cruzar meta el coche frena hasta que el BC termine de actualizar.",
        )

    def _start_imitation(self, mode_id: str, title: str, info: str) -> None:
        model = self.learn_model_var.get().strip()
        settings = TeachingSettings(
            reference=self.learn_ref_var.get().strip(),
            speed_target_kmh=float(self.hybrid_speed_var.get()),
            gamepad=self.learn_settings.gamepad,
            mode_id=mode_id,
            bc_model_path=model,
            hybrid_alpha=float(self.hybrid_alpha_var.get()),
            graduation_laps=int(self.hybrid_grad_var.get()),
            max_laps=int(self.hybrid_laps_var.get()),
        )
        if not self._check_reference(settings.reference) or not self._check_venv():
            return
        if not self._check_bc_model(model):
            return
        launch_teaching(settings)
        messagebox.showinfo(title, info)

    def _start_hybrid(self) -> None:
        self._start_imitation(
            "hybrid",
            "Hybrid",
            "BC + teacher en consola.\nGradúa a autónomo tras vueltas limpias.",
        )

    def _start_autonomous(self) -> None:
        self._start_imitation(
            "autonomous",
            "Autónomo",
            "BC sin teacher en consola. Ctrl+C para parar.",
        )

    def _start_training(self) -> None:
        settings = self._collect_settings()
        if not self._check_reference(settings.reference) or not self._check_venv():
            return
        launch_training(settings)
        messagebox.showinfo(
            "Entrenamiento",
            "Se abrió una ventana de consola.\n"
            "Asegúrate de que Project CARS 2 está EN PISTA.",
        )

    def _open_monitor(self) -> None:
        settings = self._collect_settings()
        launch_monitor(settings)

    def _open_tb(self) -> None:
        settings = self._collect_settings()
        launch_tensorboard(settings.combo())


def main() -> None:
    app = TrainingGui()
    app._update_command_preview()
    app._update_learn_command()
    app.mainloop()


if __name__ == "__main__":
    main()
