from pathlib import Path
from typing import Any, Dict

import pytest

from experimental.common import aislado


def test_argv_isolates_model_and_buffer():
    argv = aislado.build_argv(Path("py"), "c0_log", 40, 2)
    assert argv[argv.index("--model") + 1].endswith("c0_log_model.pt")
    assert argv[argv.index("--buffer") + 1].endswith("c0_log_buffer.jsonl")
    assert argv[argv.index("--experiment") + 1] == "c0_log"
    assert argv[argv.index("--learn-every") + 1] == "99" and "--speed-band" in argv
    assert "--stop-on-damage" in argv
    assert "--teacher-only" not in argv
    assert "--teacher-only" in aislado.build_argv(Path("py"), "c0_log", 40, 2, teacher_only=True)
    assert "--hold-stage" not in argv
    assert "--hold-stage" in aislado.build_argv(Path("py"), "c0_log", 40, 4, teacher_only=True)  # V64: --laps 4 da 4 vueltas, no 2


def test_experiment_name_per_band_with_teacher():
    assert aislado.experiment_name(40, False) == "c0_log"
    assert aislado.experiment_name(40, True) == "teacher_40"
    assert aislado.experiment_name(55, True) == "teacher_55"
    assert aislado.experiment_name(40, True, "mio") == "mio"


def test_progress_restored_even_if_run_fails(tmp_path, monkeypatch):
    prog = tmp_path / "prog.json"
    prog.write_text("original")
    monkeypatch.setattr(aislado, "progress_file", lambda: prog)
    monkeypatch.setattr(aislado, "DATA", tmp_path / "data")
    monkeypatch.setattr(aislado, "APP", tmp_path / "app")
    (tmp_path / "app" / "models").mkdir(parents=True)
    (tmp_path / "app" / "models" / "universal_bc.pt").write_bytes(b"m")

    def boom(*a, **k):
        prog.write_text("modificado por learn_driver")
        raise RuntimeError("fallo")

    monkeypatch.setattr(aislado.subprocess, "run", boom)
    with pytest.raises(RuntimeError):
        aislado.run_isolated("t", 40, 2)
    assert prog.read_text() == "original"
    assert (tmp_path / "data" / "t_model.pt").read_bytes() == b"m"


def test_model_src_replaces_production_model(tmp_path, monkeypatch):
    monkeypatch.setattr(aislado, "progress_file", lambda: tmp_path / "prog.json")
    monkeypatch.setattr(aislado, "DATA", tmp_path / "data")
    monkeypatch.setattr(aislado, "APP", tmp_path / "app")
    (tmp_path / "app" / "models").mkdir(parents=True)
    (tmp_path / "app" / "models" / "universal_bc.pt").write_bytes(b"produccion")
    nuevo = tmp_path / "bc_7c.pt"
    nuevo.write_bytes(b"nuevo")
    monkeypatch.setattr(aislado.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})())
    aislado.run_isolated("t", 20, 2, model_src=nuevo)
    assert (tmp_path / "data" / "t_model.pt").read_bytes() == b"nuevo"
    assert (tmp_path / "app" / "models" / "universal_bc.pt").read_bytes() == b"produccion"


def test_base_sources_only_new_teacher_data(tmp_path):
    for n in ("c0_log_buffer.jsonl", "teacher_20_buffer.jsonl", "teacher_80_buffer.jsonl", "bc7c_20_buffer.jsonl",
              "universal_teacher_sinsolape.jsonl", "curated_buffer_sinsolape.npz"):
        (tmp_path / n).write_text("{}\n")
    nombres = [f.name for f in aislado.base_sources(tmp_path)]
    assert nombres == ["c0_log_buffer.jsonl", "teacher_20_buffer.jsonl", "teacher_80_buffer.jsonl",
                       "universal_teacher_sinsolape.jsonl"]


def test_build_base_dataset_concatenates_and_fixes_missing_newline(tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    a.write_text('{"x": 1}')  # sin salto de línea final
    b.write_text('{"x": 2}\n\n{"x": 3}\n')
    out = tmp_path / "base.jsonl"
    assert aislado.build_base_dataset(out, [a, b]) == 3
    assert out.read_text().splitlines() == ['{"x": 1}', '{"x": 2}', '{"x": 3}']
    with pytest.raises(FileNotFoundError):
        aislado.build_base_dataset(out, [])


def test_argv_finetune_uses_new_base_and_no_curated():
    argv = aislado.build_argv(Path("py"), "e", 20, 2, learn_every=1, base_dataset=Path("x/base.jsonl"))
    assert argv[argv.index("--learn-every") + 1] == "1"
    assert argv[argv.index("--base-dataset") + 1].endswith("base.jsonl")
    assert argv[argv.index("--curated") + 1] == ""
    sin = aislado.build_argv(Path("py"), "e", 20, 2)
    assert "--base-dataset" not in sin and "--curated" not in sin


def test_argv_perturb_every_only_when_positive():
    argv = aislado.build_argv(Path("py"), "e", 20, 2, perturb_every=250)
    assert argv[argv.index("--perturb-every") + 1] == "250"
    assert "--perturb-every" not in aislado.build_argv(Path("py"), "e", 20, 2)


def test_run_isolated_finetune_builds_base_and_passes_it(tmp_path, monkeypatch):
    monkeypatch.setattr(aislado, "progress_file", lambda: tmp_path / "prog.json")
    monkeypatch.setattr(aislado, "DATA", tmp_path / "data")
    monkeypatch.setattr(aislado, "APP", tmp_path / "app")
    (tmp_path / "app" / "models").mkdir(parents=True)
    (tmp_path / "app" / "models" / "universal_bc.pt").write_bytes(b"m")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "teacher_20_buffer.jsonl").write_text('{"x": 1}\n')
    vistos = []
    monkeypatch.setattr(aislado.subprocess, "run", lambda argv, **k: vistos.append(argv) or type("R", (), {"returncode": 0})())
    aislado.run_isolated("bc", 20, 2, finetune_every=1)
    argv = vistos[0]
    assert argv[argv.index("--learn-every") + 1] == "1"
    assert (tmp_path / "data" / "bc_base.jsonl").read_text() == '{"x": 1}\n'


def test_argv_ramp_flags_only_when_asked():
    argv = aislado.build_argv(Path("py"), "e", 60, 6, ramp=True, ramp_ceiling=80, ramp_step=5)
    assert "--ramp" in argv
    assert argv[argv.index("--ramp-ceiling") + 1] == "80" and argv[argv.index("--ramp-step") + 1] == "5"
    assert "--ramp" not in aislado.build_argv(Path("py"), "e", 60, 6)


def _fake_env(tmp_path, monkeypatch):
    monkeypatch.setattr(aislado, "progress_file", lambda: tmp_path / "prog.json")
    monkeypatch.setattr(aislado, "DATA", tmp_path / "data")
    monkeypatch.setattr(aislado, "APP", tmp_path / "app")
    (tmp_path / "app" / "models").mkdir(parents=True)
    (tmp_path / "app" / "models" / "universal_bc.pt").write_bytes(b"inicial")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "teacher_20_buffer.jsonl").write_text('{"x": 1}\n')
    vistos = []
    monkeypatch.setattr(aislado.subprocess, "run", lambda argv, **k: vistos.append(argv) or type("R", (), {"returncode": 0})())
    return vistos


def test_run_isolated_ramp_builds_base_for_the_fine_tune(tmp_path, monkeypatch):
    vistos = _fake_env(tmp_path, monkeypatch)
    aislado.run_isolated("r", 60, 6, ramp=True)
    argv = vistos[0]
    assert "--ramp" in argv and "--base-dataset" in argv
    assert (tmp_path / "data" / "r_base.jsonl").is_file()


def test_run_isolated_fresh_start_clears_buffer_and_ramp_state(tmp_path, monkeypatch):
    _fake_env(tmp_path, monkeypatch)
    data = tmp_path / "data"
    (data / "r_buffer.jsonl").write_text("viejo\n")
    (data / "r_buffer.jsonl.ramp.json").write_text("{}")
    (data / "r_model.pt").write_bytes(b"viejo")
    aislado.run_isolated("r", 60, 6, ramp=True)
    assert not (data / "r_buffer.jsonl").exists() and not (data / "r_buffer.jsonl.ramp.json").exists()
    assert (data / "r_model.pt").read_bytes() == b"inicial"


def test_run_isolated_resume_keeps_model_buffer_and_ramp_state(tmp_path, monkeypatch):
    _fake_env(tmp_path, monkeypatch)
    data = tmp_path / "data"
    (data / "r_buffer.jsonl").write_text("filas\n")
    (data / "r_buffer.jsonl.ramp.json").write_text("{}")
    (data / "r_model.pt").write_bytes(b"ajustado")
    aislado.run_isolated("r", 60, 6, ramp=True, resume=True)
    assert (data / "r_buffer.jsonl").read_text() == "filas\n"
    assert (data / "r_buffer.jsonl.ramp.json").exists()
    assert (data / "r_model.pt").read_bytes() == b"ajustado"


def test_run_isolated_resume_without_previous_model_starts_fresh(tmp_path, monkeypatch):
    _fake_env(tmp_path, monkeypatch)
    aislado.run_isolated("r", 60, 6, ramp=True, resume=True)
    assert (tmp_path / "data" / "r_model.pt").read_bytes() == b"inicial"


def test_argv_steer_damp_only_when_given():
    assert "--steer-damp-kmh" not in aislado.build_argv(Path("py"), "e", 55, 2)
    argv = aislado.build_argv(Path("py"), "e", 55, 2, steer_damp_kmh=0)
    assert argv[argv.index("--steer-damp-kmh") + 1] == "0"


def test_argv_ident_adds_maneuver_and_rain_limit():
    argv = aislado.build_argv(Path("py"), "a1_acel_30", 30, 2, ident="acel", ident_cap_kmh=60, teacher_only=True)
    assert argv[argv.index("--ident") + 1] == "acel"
    assert argv[argv.index("--ident-cap-kmh") + 1] == "60"
    assert argv[argv.index("--ident-end-margin-m") + 1] == "150"
    assert argv[argv.index("--rain-limit") + 1] == "1"  # cualquier lluvia cierra la sesión
    assert "--ident" not in aislado.build_argv(Path("py"), "e", 30, 2)
    assert "--rain-limit" not in aislado.build_argv(Path("py"), "e", 30, 2)


def test_ident_experiment_name_never_collides_with_training_buffers():
    assert aislado.experiment_name(30, True, "", "acel") == "a1_acel_30"
    assert aislado.experiment_name(80, True, "a1_rodar_prueba", "rodar") == "a1_rodar_prueba"
    with pytest.raises(ValueError):
        aislado.experiment_name(30, True, "teacher_30", "acel")  # run_isolated borraría ese buffer
    assert aislado.experiment_name(30, True) == "teacher_30"  # sin --ident todo igual que antes


def test_ctrl_c_returns_130_and_restores_progress(tmp_path, monkeypatch):
    prog = tmp_path / "prog.json"
    prog.write_text("original")
    monkeypatch.setattr(aislado, "progress_file", lambda: prog)
    monkeypatch.setattr(aislado, "DATA", tmp_path / "data")
    monkeypatch.setattr(aislado, "APP", tmp_path)

    def boom(*a, **k):
        prog.write_text("cambiado por la prueba")
        raise KeyboardInterrupt

    monkeypatch.setattr(aislado.subprocess, "run", boom)
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "universal_bc.pt").write_text("bc")
    assert aislado.run_isolated("e", 30, 1, python=Path("py")) == 130
    assert prog.read_text() == "original"


def test_ident_acelrodar_is_accepted_by_argv():
    argv = aislado.build_argv(Path("py"), "a1_acelrodar_60", 60, 2, ident="acelrodar", ident_cap_kmh=120, ident_floor_kmh=60)
    assert argv[argv.index("--ident") + 1] == "acelrodar"
    assert aislado.experiment_name(60, True, "", "acelrodar") == "a1_acelrodar_60"


def test_argv_ident_straights_only_when_given():
    argv = aislado.build_argv(Path("py"), "a1_acelrodar_60", 60, 2, ident="acelrodar", ident_cap_kmh=130, ident_floor_kmh=60,
                              ident_straights="1")
    assert argv[argv.index("--ident-straights") + 1] == "1"
    assert "--ident-straights" not in aislado.build_argv(Path("py"), "a1_acelrodar_60", 60, 2, ident="acelrodar", ident_cap_kmh=130)


def test_ident_cap_limit_is_shared_with_the_maneuver():
    from ident_maneuver import MAX_CAP_KMH

    assert aislado.IDENT_MAX_CAP_KMH == MAX_CAP_KMH


def test_argv_ident_frenar_carries_the_entry_speeds():
    argv = aislado.build_argv(Path("py"), "a1_frenar_60", 60, 2, ident="frenar", ident_floor_kmh=30, ident_straights="1",
                              ident_caps="60,80,100")
    assert argv[argv.index("--ident") + 1] == "frenar"
    assert argv[argv.index("--ident-caps") + 1] == "60,80,100"
    assert "--ident-caps" not in aislado.build_argv(Path("py"), "e", 60, 2, ident="acel", ident_cap_kmh=100)
    assert aislado.experiment_name(60, True, "", "frenar") == "a1_frenar_60"


def test_argv_ident_arco_carries_the_ramp():
    argv = aislado.build_argv(Path("py"), "a1_arco_60", 60, 4, ident="arco", ident_arc_speeds="80,85,90", ident_arc_cte=2.5)
    assert argv[argv.index("--ident") + 1] == "arco"
    assert argv[argv.index("--ident-arc-speeds") + 1] == "80,85,90"
    assert argv[argv.index("--ident-arc-window") + 1] == "3200,600"
    assert argv[argv.index("--ident-arc-cte") + 1] == "2.5"
    assert argv[argv.index("--rain-limit") + 1] == "1" and "--stop-on-damage" in argv
    assert "--ident-arc-speeds" not in aislado.build_argv(Path("py"), "e", 60, 2, ident="frenar", ident_caps="60,80")
    assert aislado.experiment_name(60, True, "", "arco") == "a1_arco_60"


def test_arc_speed_limit_is_shared_with_the_ramp():
    from ident_arc import MAX_ARC_KMH

    assert aislado.IDENT_MAX_ARC_KMH == MAX_ARC_KMH <= aislado.IDENT_MAX_CAP_KMH


def test_steer_ff_gain_goes_to_learn_driver_only_when_set():
    base = aislado.build_argv(Path("python"), "a1_arco_60", 60.0, 6, teacher_only=True)
    assert "--steer-ff-gain" not in base
    argv = aislado.build_argv(Path("python"), "a1_arco_ff_60", 60.0, 6, teacher_only=True, steer_ff_gain=0.003)
    assert argv[argv.index("--steer-ff-gain") + 1] == "0.003"


def test_max_gear_goes_to_learn_driver_only_when_not_production():
    assert "--max-gear" not in aislado.build_argv(Path("python"), "a1_acel_60", 60.0, 3, teacher_only=True, ident="acel")
    argv = aislado.build_argv(Path("python"), "a1_acel_g3_60", 60.0, 3, teacher_only=True, ident="acel", max_gear=3)
    assert argv[argv.index("--max-gear") + 1] == "3"


def test_aislado_passes_the_reference_to_learn_driver():
    from experimental.common import aislado

    assert aislado.build_argv(Path("python"), "a1_acel_60", 60.0, 3, teacher_only=True)[
        aislado.build_argv(Path("python"), "a1_acel_60", 60.0, 3, teacher_only=True).index("--reference") + 1] == "src/refs/sugo_ai.json"
    argv = aislado.build_argv(Path("python"), "a1_acel_60", 60.0, 3, teacher_only=True, reference="C:/x/sugo_smooth.json")
    assert argv[argv.index("--reference") + 1] == "C:/x/sugo_smooth.json"


def test_a2_vueltas_completas_llevan_el_limite_lateral_propio_a_learn_driver():
    base = aislado.build_argv(Path("python"), "a2_x", 100.0, 3, teacher_only=True, max_gear=3)
    assert base[base.index("--lat-accel-limit") + 1] == "6.5"  # sin pedirlo, el de siempre
    argv = aislado.build_argv(Path("python"), "a2_x", 100.0, 3, teacher_only=True, max_gear=3, lat_accel_limit=12.5)
    assert argv[argv.index("--lat-accel-limit") + 1] == "12.5" and argv[argv.index("--max-gear") + 1] == "3"
    assert "--ident" not in argv and "--teacher-only" in argv and "--stop-on-damage" in argv


def test_a2_error_exige_teacher_prefijo_a2_y_limites_validados():
    ok: Dict[str, Any] = dict(ident="", max_gear=3, lat_accel_limit=12.5, teacher_only=True, experiment="a2_suave_100", speed_band=100.0, cap_limit=150.0)
    assert aislado.a2_error(**ok) is None
    assert aislado.a2_error(**{**ok, "teacher_only": False})  # el BC no conduce con marchas sin validar
    sin_nombre = aislado.a2_error(**{**ok, "experiment": ""})  # el nombre por defecto borraría `teacher_<banda>`
    assert sin_nombre is not None and "a2_" in sin_nombre
    nombre_de_teacher = aislado.a2_error(**{**ok, "experiment": "teacher_100"})
    assert nombre_de_teacher is not None and "a2_" in nombre_de_teacher
    assert aislado.a2_error(**{**ok, "speed_band": 160.0})  # por encima del techo de la 3ª
    assert aislado.a2_error(**{**ok, "lat_accel_limit": 15.0})  # por encima de la cota de D21
    assert aislado.a2_error(**{**ok, "lat_accel_limit": 0.0})
    # lo de antes sigue igual: producción y A1 no piden nada
    assert aislado.a2_error("", 2, aislado.LAT_ACCEL_LIMIT, False, "", 40.0, 120.0) is None
    assert aislado.a2_error("acel", 3, aislado.LAT_ACCEL_LIMIT, True, "a1_acel_g3_60", 60.0, 150.0) is None


def test_steer_slip_gain_goes_to_learn_driver_only_when_set():
    assert "--steer-slip-gain" not in aislado.build_argv(Path("python"), "a2_x", 100.0, 3, teacher_only=True)
    argv = aislado.build_argv(Path("python"), "a2_x", 100.0, 3, teacher_only=True, steer_slip_gain=5.0)
    assert argv[argv.index("--steer-slip-gain") + 1] == "5"


def test_lat_gain_v0_goes_to_learn_driver_only_when_set():
    assert "--lat-gain-v0-kmh" not in aislado.build_argv(Path("python"), "a2_x", 100.0, 3, teacher_only=True)
    argv = aislado.build_argv(Path("python"), "a2_x", 100.0, 3, teacher_only=True, lat_gain_v0_kmh=60.0)
    assert argv[argv.index("--lat-gain-v0-kmh") + 1] == "60"


def test_las_opciones_propias_del_teacher_exigen_prefijo_a2_y_teacher_only():
    base: Dict[str, Any] = dict(ident="", max_gear=2, lat_accel_limit=aislado.LAT_ACCEL_LIMIT, teacher_only=True, experiment="a2_x", speed_band=100.0, cap_limit=115.0)
    assert aislado.a2_error(**base, extra_teacher_options=True) is None
    assert "a2_" in (aislado.a2_error(**{**base, "experiment": ""}, extra_teacher_options=True) or "")  # el nombre por defecto borraría `teacher_<banda>`
    assert aislado.a2_error(**{**base, "teacher_only": False}, extra_teacher_options=True)
    assert aislado.a2_error(**{**base, "experiment": ""}) is None  # sin opciones propias, producción


def test_steer_ff_v0_goes_to_learn_driver_only_when_set():
    assert "--steer-ff-v0-kmh" not in aislado.build_argv(Path("python"), "a2_x", 80.0, 3, teacher_only=True)
    argv = aislado.build_argv(Path("python"), "a2_x", 80.0, 3, teacher_only=True, steer_ff_gain=0.0035, steer_ff_v0_kmh=0.0)
    assert argv[argv.index("--steer-ff-v0-kmh") + 1] == "0" and argv[argv.index("--steer-ff-gain") + 1] == "0.0035"


def test_steer_preview_goes_to_learn_driver_only_when_set():
    assert "--steer-preview-s" not in aislado.build_argv(Path("python"), "a2_x", 80.0, 3, teacher_only=True)
    argv = aislado.build_argv(Path("python"), "a2_x", 80.0, 3, teacher_only=True, steer_preview_s=0.3)
    assert argv[argv.index("--steer-preview-s") + 1] == "0.3"


def test_steer_heading_gain_goes_to_learn_driver_only_when_set():
    assert "--steer-heading-gain" not in aislado.build_argv(Path("python"), "a2_x", 80.0, 3, teacher_only=True)
    argv = aislado.build_argv(Path("python"), "a2_x", 80.0, 3, teacher_only=True, steer_heading_gain=0.7)
    assert argv[argv.index("--steer-heading-gain") + 1] == "0.7"


def test_throttle_max_goes_to_learn_driver_only_when_not_production():
    assert "--throttle-max" not in aislado.build_argv(Path("python"), "a2_x", 90.0, 3, teacher_only=True)
    argv = aislado.build_argv(Path("python"), "a2_x", 90.0, 3, teacher_only=True, throttle_max=1.0)
    assert argv[argv.index("--throttle-max") + 1] == "1"


def test_straight_braking_options_go_to_learn_driver_only_when_set():
    argv0 = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True)
    assert "--brake-decel-straight" not in argv0 and "--brake-overspeed-straight-ms" not in argv0
    argv = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True, brake_decel_straight=8.0, brake_overspeed_straight_ms=2.5)
    assert argv[argv.index("--brake-decel-straight") + 1] == "8" and argv[argv.index("--brake-overspeed-straight-ms") + 1] == "2.5"


def test_brake_slip_limit_goes_to_learn_driver_only_when_set_and_also_with_ident_frenar():
    assert "--brake-slip-limit" not in aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True)
    argv = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True, brake_slip_limit=0.2)
    assert argv[argv.index("--brake-slip-limit") + 1] == "0.2"
    argv = aislado.build_argv(Path("python"), "a1_frenar", 60.0, 3, teacher_only=True, ident="frenar", ident_caps="130,140", max_gear=3, brake_slip_limit=0.2)
    assert argv[argv.index("--brake-slip-limit") + 1] == "0.2" and argv[argv.index("--ident") + 1] == "frenar"


def test_brake_slip_limit_counts_as_a_teacher_option_for_the_a2_name_rule():
    cap = aislado.ident_max_cap_kmh(3)
    # sin --ident, una opción propia del teacher exige el prefijo a2_ en el nombre del experimento
    assert aislado.a2_error("", 3, aislado.LAT_ACCEL_LIMIT, True, "teacher_125", 125.0, cap, True) is not None
    assert aislado.a2_error("", 3, aislado.LAT_ACCEL_LIMIT, True, "a2_frena_slip02", 125.0, cap, True) is None
    # con --ident la opción se acepta con cualquier nombre
    assert aislado.a2_error("frenar", 3, aislado.LAT_ACCEL_LIMIT, True, "a1_frenar_g3_slip02", 60.0, cap, True) is None


def test_steer_ff_cap_goes_to_learn_driver_only_when_set_and_counts_as_a_teacher_option():
    assert "--steer-ff-cap-kmh" not in aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True, steer_ff_gain=0.003)
    argv = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True, steer_ff_gain=0.003, steer_ff_cap_kmh=100.0)
    assert argv[argv.index("--steer-ff-cap-kmh") + 1] == "100" and argv[argv.index("--steer-ff-gain") + 1] == "0.003"


def test_pedal_technique_goes_to_learn_driver_only_when_set_and_counts_as_a_teacher_option():
    base = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True)
    assert "--pedal-technique" not in base and "--pedal-exit-slew" not in base
    argv = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True, pedal_technique=True)
    assert "--pedal-technique" in argv and "--pedal-exit-slew" not in argv  # la pendiente por defecto no se pasa
    argv = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True, pedal_technique=True, pedal_exit_slew=1.2)
    assert argv[argv.index("--pedal-exit-slew") + 1] == "1.2"
    cap = aislado.ident_max_cap_kmh(3)
    assert aislado.a2_error("", 3, aislado.LAT_ACCEL_LIMIT, True, "teacher_125", 125.0, cap, True) is not None


def test_brake_slip_hold_goes_to_learn_driver_only_when_set():
    assert "--brake-slip-hold" not in aislado.build_argv(Path("python"), "a1_frenar", 60.0, 3, teacher_only=True, ident="frenar", ident_caps="130", max_gear=3, brake_slip_limit=0.25)
    argv = aislado.build_argv(Path("python"), "a1_frenar", 60.0, 3, teacher_only=True, ident="frenar", ident_caps="130", max_gear=3, brake_slip_limit=0.25, brake_slip_hold=0.85)
    assert argv[argv.index("--brake-slip-hold") + 1] == "0.85" and argv[argv.index("--brake-slip-limit") + 1] == "0.25"


def test_brake_slip_hold_counts_as_a_teacher_option_for_the_a2_name_rule():
    cap = aislado.ident_max_cap_kmh(3)
    assert aislado.a2_error("", 3, aislado.LAT_ACCEL_LIMIT, True, "teacher_125", 125.0, cap, True) is not None


def test_brake_profile_goes_to_learn_driver_only_when_set_and_counts_as_a_teacher_option():
    base = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True, pedal_technique=True)
    assert "--brake-profile" not in base and "--brake-circle" not in base
    argv = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True, pedal_technique=True, brake_profile=True)
    assert "--brake-profile" in argv and "--brake-circle" not in argv  # el círculo por defecto (14,6) no se pasa
    argv = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True, pedal_technique=True, brake_profile=True, brake_circle=11.0)
    assert argv[argv.index("--brake-circle") + 1] == "11"
    cap = aislado.ident_max_cap_kmh(3)
    assert aislado.a2_error("", 3, aislado.LAT_ACCEL_LIMIT, True, "teacher_125", 125.0, cap, True) is not None


def test_exit_circle_goes_to_learn_driver_only_when_set_and_counts_as_a_teacher_option():
    base = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True, pedal_technique=True)
    assert "--exit-circle" not in base
    argv = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True, pedal_technique=True, exit_circle=14.6)
    assert argv[argv.index("--exit-circle") + 1] == "14.6"
    cap = aislado.ident_max_cap_kmh(3)
    assert aislado.a2_error("", 3, aislado.LAT_ACCEL_LIMIT, True, "teacher_125", 125.0, cap, True) is not None


def test_profile_peak_min_m_goes_to_learn_driver_only_when_set():
    base = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True, pedal_technique=True, brake_profile=True)
    assert "--profile-peak-min-m" not in base
    argv = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True, pedal_technique=True, brake_profile=True, profile_peak_min_m=60.0)
    assert argv[argv.index("--profile-peak-min-m") + 1] == "60"


def test_profile_peak_min_kmh_goes_to_learn_driver_only_when_set():
    base = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True, pedal_technique=True, brake_profile=True, profile_peak_min_m=60.0)
    assert "--profile-peak-min-kmh" not in base
    argv = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True, pedal_technique=True, brake_profile=True, profile_peak_min_m=60.0, profile_peak_min_kmh=8.0)
    assert argv[argv.index("--profile-peak-min-kmh") + 1] == "8"


def test_lat_adapt_goes_to_learn_driver_only_when_asked_and_its_values_only_when_not_default():
    base = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True)
    assert not any(a.startswith("--lat-adapt") for a in base)
    argv = aislado.build_argv(Path("python"), "a2_x", 125.0, 3, teacher_only=True, lat_adapt=True)
    assert "--lat-adapt" in argv and "--lat-adapt-max-scale" not in argv and "--lat-adapt-cap" not in argv
    argv = aislado.build_argv(Path("python"), "a2_x", 100.0, 2, teacher_only=True, lat_adapt=True, lat_adapt_max_scale=1.5, lat_adapt_cap=9.0)
    assert argv[argv.index("--lat-adapt-max-scale") + 1] == "1.5" and argv[argv.index("--lat-adapt-cap") + 1] == "9"


def test_lat_adapt_map_options_go_to_learn_driver_only_with_lat_adapt():
    base = aislado.build_argv(Path("python"), "a2_x", 140.0, 3, teacher_only=True, lat_adapt=True)
    assert not any(a in base for a in ("--lat-adapt-load", "--lat-adapt-save", "--lat-adapt-fixed"))
    argv = aislado.build_argv(Path("python"), "a2_x", 140.0, 3, teacher_only=True, lat_adapt=True, lat_adapt_load="C:/m/seco.json", lat_adapt_save="C:/m/nuevo.json")
    assert argv[argv.index("--lat-adapt-load") + 1] == "C:/m/seco.json" and argv[argv.index("--lat-adapt-save") + 1] == "C:/m/nuevo.json"
    assert "--lat-adapt-fixed" not in argv
    argv = aislado.build_argv(Path("python"), "a2_x", 140.0, 3, teacher_only=True, lat_adapt=True, lat_adapt_load="C:/m/seco.json", lat_adapt_fixed=True)
    assert "--lat-adapt-fixed" in argv and "--lat-adapt-save" not in argv
    sin = aislado.build_argv(Path("python"), "a2_x", 140.0, 3, teacher_only=True, lat_adapt_load="C:/m/seco.json")
    assert "--lat-adapt-load" not in sin


def test_exit_adapt_goes_to_learn_driver_only_when_asked_with_its_map_options():
    base = aislado.build_argv(Path("python"), "a2_x", 140.0, 3, teacher_only=True, pedal_technique=True, exit_circle=18.0)
    assert not any(a.startswith("--exit-adapt") for a in base)
    argv = aislado.build_argv(Path("python"), "a2_x", 140.0, 3, teacher_only=True, pedal_technique=True, exit_circle=18.0, exit_adapt=True)
    assert "--exit-adapt" in argv and not any(a in argv for a in ("--exit-adapt-max-scale", "--exit-adapt-load", "--exit-adapt-save", "--exit-adapt-fixed"))
    argv = aislado.build_argv(Path("python"), "a2_x", 140.0, 3, teacher_only=True, pedal_technique=True, exit_circle=18.0, exit_adapt=True, exit_adapt_max_scale=1.5,
                              exit_adapt_load="C:/m/sal.json", exit_adapt_save="C:/m/nuevo.json")
    assert argv[argv.index("--exit-adapt-max-scale") + 1] == "1.5" and argv[argv.index("--exit-adapt-load") + 1] == "C:/m/sal.json"
    assert argv[argv.index("--exit-adapt-save") + 1] == "C:/m/nuevo.json" and "--exit-adapt-fixed" not in argv
    argv = aislado.build_argv(Path("python"), "a2_x", 140.0, 3, teacher_only=True, pedal_technique=True, exit_circle=18.0, exit_adapt=True, exit_adapt_load="C:/m/sal.json", exit_adapt_fixed=True)
    assert "--exit-adapt-fixed" in argv and "--exit-adapt-save" not in argv
    sin = aislado.build_argv(Path("python"), "a2_x", 140.0, 3, teacher_only=True, pedal_technique=True, exit_circle=18.0, exit_adapt_load="C:/m/sal.json")
    assert "--exit-adapt-load" not in sin


def test_brake_adapt_goes_to_learn_driver_only_when_asked_with_its_map_options():
    kw = dict(teacher_only=True, pedal_technique=True, brake_profile=True, brake_decel_straight=11.0)
    base = aislado.build_argv(Path("python"), "a2_x", 140.0, 3, **kw)
    assert not any(a.startswith("--brake-adapt") for a in base)
    argv = aislado.build_argv(Path("python"), "a2_x", 140.0, 3, brake_adapt=True, **kw)
    assert "--brake-adapt" in argv and not any(a in argv for a in ("--brake-adapt-max-scale", "--brake-adapt-load", "--brake-adapt-save", "--brake-adapt-fixed"))
    argv = aislado.build_argv(Path("python"), "a2_x", 140.0, 3, brake_adapt=True, brake_adapt_max_scale=1.3, brake_adapt_load="C:/m/fr.json", brake_adapt_save="C:/m/nuevo.json", **kw)
    assert argv[argv.index("--brake-adapt-max-scale") + 1] == "1.3" and argv[argv.index("--brake-adapt-load") + 1] == "C:/m/fr.json"
    assert argv[argv.index("--brake-adapt-save") + 1] == "C:/m/nuevo.json" and "--brake-adapt-fixed" not in argv
    argv = aislado.build_argv(Path("python"), "a2_x", 140.0, 3, brake_adapt=True, brake_adapt_load="C:/m/fr.json", brake_adapt_fixed=True, **kw)
    assert "--brake-adapt-fixed" in argv and "--brake-adapt-save" not in argv
    sin = aislado.build_argv(Path("python"), "a2_x", 140.0, 3, brake_adapt_load="C:/m/fr.json", **kw)
    assert "--brake-adapt-load" not in sin


def test_upshift_rpm_goes_to_learn_driver_only_when_set():
    assert "--upshift-rpm" not in aislado.build_argv(Path("python"), "a2_x", 155.0, 3, teacher_only=True, max_gear=4)
    argv = aislado.build_argv(Path("python"), "a2_x", 155.0, 3, teacher_only=True, max_gear=4, upshift_rpm=7400.0)
    assert argv[argv.index("--upshift-rpm") + 1] == "7400"
