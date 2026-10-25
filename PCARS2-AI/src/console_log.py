"""
console_log.py
Duplica stdout y stderr en un fichero (`consola.log`) sin perder la salida normal: las líneas
`[Env] ...` y `[Ep n] ... fin=...` explican por qué terminan los episodios y no estaban en ningún CSV.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Callable


class _Tee:
    def __init__(self, stream, file):
        self._stream = stream
        self._file = file

    def write(self, data: str) -> int:
        n = self._stream.write(data)
        try:
            self._file.write(data)
            self._file.flush()
        except (OSError, ValueError):
            pass            # el log nunca debe tirar el entrenamiento
        return n

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def start_console_log(path: str) -> Callable[[], None]:
    """Empieza a duplicar la consola en `path` (modo añadir). Devuelve la función que lo detiene."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        file = open(path, "a", encoding="utf-8")
    except OSError as exc:
        print(f"[main] No puedo escribir {path}: {exc}. Sigo sin log de consola.")
        return lambda: None
    file.write(f"\n=== Sesión {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = _Tee(old_out, file), _Tee(old_err, file)

    def stop() -> None:
        sys.stdout, sys.stderr = old_out, old_err
        file.close()

    return stop
