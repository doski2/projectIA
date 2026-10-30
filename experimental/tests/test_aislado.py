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
