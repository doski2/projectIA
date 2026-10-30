from pathlib import Path

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
