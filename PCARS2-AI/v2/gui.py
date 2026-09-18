"""
PCARS2-AI v2 — GUI de entrenamiento.

Uso:
    python -m v2.gui
    o gui.bat desde la raíz de PCARS2-AI
"""

from __future__ import annotations

from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .config import (
    TEACHING_MODES,
    TRAINING_MODES,
    TeachingSettings,
    TrainingSettings,
    apply_mode_defaults,
    get_mode,
    get_teaching_mode,
)
from .launcher import (
    find_latest_checkpoint,
    format_command,
    format_teaching_command,
    launch_monitor,
    launch_teaching,
    launch_tensorboard,
    launch_training,
    list_references,
    load_settings,
    project_root,
    venv_python,
)


class TrainingGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PCARS2-AI v2 — Entrenamiento")
        self.minsize(720, 620)
        self.settings = load_settings() or TrainingSettings()
        self.teaching_settings = TeachingSettings()

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
        self._on_teaching_mode_change()

    def _build_ui(self) -> None:
        px, py = 10, 4

        header = ttk.Label(
            self,
            text="PCARS2-AI v2",
            font=("Segoe UI", 16, "bold"),
        )
        header.pack(anchor="w", padx=12, pady=(12, 0))

        subtitle = ttk.Label(
            self,
            text="Elige modo y velocidad objetivo. Más ajustes se irán añadiendo aquí.",
            font=("Segoe UI", 9),
        )
        subtitle.pack(anchor="w", padx=12, pady=(0, 8))

        # --- Modo ---
        mode_frame = ttk.LabelFrame(self, text="Modo de entrenamiento")
        mode_frame.pack(fill="x", padx=12, pady=6)

        self.mode_var = tk.StringVar(value=self.settings.mode_id)
        for mode in TRAINING_MODES:
            rb = ttk.Radiobutton(
                mode_frame,
                text=mode.label,
                value=mode.id,
                variable=self.mode_var,
                command=self._on_mode_change,
            )
            rb.pack(anchor="w", padx=8, pady=2)

        self.mode_desc = ttk.Label(mode_frame, text="", wraplength=680, foreground="#444")
        self.mode_desc.pack(anchor="w", padx=8, pady=(4, 8))

        # --- Velocidad (destacado) ---
        speed_frame = ttk.LabelFrame(self, text="Velocidad objetivo (km/h)")
        speed_frame.pack(fill="x", padx=12, pady=6)

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

        # --- Ajustes principales ---
        opts = ttk.LabelFrame(self, text="Ajustes")
        opts.pack(fill="x", padx=12, pady=6)

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

        # --- Teaching Driver ---
        teach_frame = ttk.LabelFrame(self, text="Teaching Driver")
        teach_frame.pack(fill="x", padx=12, pady=6)

        self.teach_mode_var = tk.StringVar(value=self.teaching_settings.mode_id)
        for mode in TEACHING_MODES:
            ttk.Radiobutton(
                teach_frame,
                text=mode.label,
                value=mode.id,
                variable=self.teach_mode_var,
                command=self._on_teaching_mode_change,
            ).pack(anchor="w", padx=8, pady=2)

        self.teach_desc = ttk.Label(teach_frame, text="", wraplength=680, foreground="#444")
        self.teach_desc.pack(anchor="w", padx=8, pady=(2, 4))

        teach_opts = ttk.Frame(teach_frame)
        teach_opts.pack(fill="x", padx=8, pady=4)

        ttk.Label(teach_opts, text="Dataset / BC:").pack(side="left")
        self.teach_dataset_var = tk.StringVar(value=self.teaching_settings.dataset_output)
        ttk.Entry(teach_opts, textvariable=self.teach_dataset_var, width=36).pack(
            side="left", padx=4
        )
        self.teach_model_var = tk.StringVar(value=self.teaching_settings.bc_model_path)
        ttk.Entry(teach_opts, textvariable=self.teach_model_var, width=24).pack(side="left", padx=4)

        teach_btn = ttk.Frame(teach_frame)
        teach_btn.pack(fill="x", padx=8, pady=(4, 8))
        ttk.Button(
            teach_btn, text="▶ Iniciar Teaching Driver", command=self._start_teaching
        ).pack(side="left")

        self.teach_cmd_text = tk.Text(teach_frame, height=2, wrap="word", font=("Consolas", 9))
        self.teach_cmd_text.pack(fill="x", padx=8, pady=(0, 8))

        # --- Comando ---
        cmd_frame = ttk.LabelFrame(self, text="Comando generado (RL)")
        cmd_frame.pack(fill="both", expand=True, padx=12, pady=6)

        self.cmd_text = tk.Text(cmd_frame, height=4, wrap="word", font=("Consolas", 9))
        self.cmd_text.pack(fill="both", expand=True, padx=8, pady=8)

        # --- Botones ---
        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", padx=12, pady=10)

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

    def _populate_refs(self) -> None:
        refs = list_references()
        if refs:
            self.ref_combo["values"] = refs
            if self.settings.reference not in refs:
                self.ref_var.set(refs[0])

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

    def _collect_teaching_settings(self) -> TeachingSettings:
        return TeachingSettings(
            reference=self.ref_var.get().strip(),
            speed_target_kmh=float(self.speed_var.get()),
            gamepad="xbox",
            mode_id=self.teach_mode_var.get(),
            dataset_output=self.teach_dataset_var.get().strip(),
            bc_model_path=self.teach_model_var.get().strip(),
        )

    def _on_teaching_mode_change(self) -> None:
        mode = get_teaching_mode(self.teach_mode_var.get())
        self.teach_desc.config(text=mode.description)
        self._update_teaching_command()

    def _update_teaching_command(self) -> None:
        cmd = format_teaching_command(self._collect_teaching_settings())
        self.teach_cmd_text.delete("1.0", "end")
        self.teach_cmd_text.insert("1.0", cmd)

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
        self._update_teaching_command()

    def _on_speed_scale(self, _value: str) -> None:
        self._update_command_preview()
        self._update_teaching_command()

    def _on_fresh_toggle(self) -> None:
        if self.fresh_var.get():
            self.model_var.set("")
        self._update_command_preview()

    def _update_command_preview(self) -> None:
        settings = self._collect_settings()
        cmd = format_command(settings)
        self.cmd_text.delete("1.0", "end")
        self.cmd_text.insert("1.0", cmd)
        self._update_teaching_command()

    def _browse_reference(self) -> None:
        root = project_root()
        path = filedialog.askopenfilename(
            title="Archivo de referencia",
            initialdir=str(root / "src" / "refs"),
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
        )
        if path:
            try:
                rel = Path(path).resolve().relative_to(root.resolve())
                self.ref_var.set(str(rel).replace("\\", "/"))
            except ValueError:
                self.ref_var.set(path)
            self._update_command_preview()

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

    def _start_teaching(self) -> None:
        settings = self._collect_teaching_settings()
        ref_path = project_root() / settings.reference
        if not ref_path.is_file():
            messagebox.showerror("Error", f"Referencia no encontrada:\n{ref_path}")
            return
        if settings.mode_id in ("bc_drive", "hybrid", "autonomous"):
            model_path = project_root() / f"{settings.bc_model_path}.zip"
            if not model_path.is_file():
                messagebox.showerror("Error", f"Modelo BC no encontrado:\n{model_path}")
                return
        if not venv_python().is_file():
            messagebox.showerror("Error", f"Python del venv no encontrado:\n{venv_python()}")
            return
        launch_teaching(settings)
        messagebox.showinfo(
            "Teaching Driver",
            "Se abrió una ventana de consola.\n"
            "Asegúrate de que Project CARS 2 está EN PISTA.",
        )

    def _start_training(self) -> None:
        settings = self._collect_settings()
        ref_path = project_root() / settings.reference
        if not ref_path.is_file():
            messagebox.showerror("Error", f"Referencia no encontrada:\n{ref_path}")
            return
        if not venv_python().is_file():
            messagebox.showerror("Error", f"Python del venv no encontrado:\n{venv_python()}")
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
    app._update_teaching_command()
    app.mainloop()


if __name__ == "__main__":
    main()
