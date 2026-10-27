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
