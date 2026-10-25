"""Duplicado de la consola a consola.log."""

import io
import sys

from console_log import start_console_log


def test_tee_writes_to_both_streams_and_appends(tmp_path, monkeypatch):
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    path = tmp_path / "logs" / "consola.log"
    stop = start_console_log(str(path))
    print("[Env] hola → ñ")
    print("error de prueba", file=sys.stderr)
    stop()
    assert "hola" in out.getvalue() and "error de prueba" in err.getvalue()
    assert sys.stdout is out and sys.stderr is err           # se restauran
    text = path.read_text(encoding="utf-8")
    assert "[Env] hola → ñ" in text and "error de prueba" in text

    stop2 = start_console_log(str(path))                      # otra ejecución: añade
    print("segunda")
    stop2()
    text = path.read_text(encoding="utf-8")
    assert "hola" in text and "segunda" in text and text.count("=== Sesión") == 2


def test_tee_survives_an_unwritable_log(tmp_path, monkeypatch, capsys):
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    stop = start_console_log(str(tmp_path))                   # un directorio no se puede abrir como fichero
    print("sigue funcionando")
    stop()
    assert "sigue funcionando" in out.getvalue()
