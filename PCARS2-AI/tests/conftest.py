"""
Configuración compartida de pytest para PCARS2-AI.

Añade el directorio `src/` al `sys.path` para que los tests puedan importar
los módulos del proyecto (`reference_recorder`, `controller`, `monitor`, `main`)
exactamente como hacen entre sí (imports planos, sin paquete).
"""

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_ROOT, "src")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

_VENV_PYTHON = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".venv", "Scripts", "python.exe")
)
_REQUIRED_PACKAGES = (
    "numpy",
    "gymnasium",
    "stable_baselines3",
    "torch",
    "rich",
    "vgamepad",
    "pytest",
)


def pytest_configure(config):
    """Falla pronto con un mensaje claro si se usa Python sin dependencias."""
    import pytest

    missing = []
    for name in _REQUIRED_PACKAGES:
        try:
            __import__(name)
        except ImportError:
            missing.append(name)
    if not missing:
        return

    exe = os.path.normcase(os.path.abspath(sys.executable))
    in_venv = "venv" in exe or ".venv" in exe
    lines = [
        "",
        "=" * 60,
        "PCARS2-AI: faltan dependencias para ejecutar los tests",
        "=" * 60,
        f"  Paquetes no encontrados: {', '.join(missing)}",
        f"  Python en uso: {sys.executable}",
        "",
    ]
    if not in_venv:
        lines.extend([
            "  Estás usando el Python del sistema, no el venv del proyecto.",
            "",
            "  Solución (desde PCARS2-AI):",
            f"    {_VENV_PYTHON} -m pytest tests",
            "  O bien:",
            "    tests.bat",
            "",
            "  Si el venv no existe aún:",
            "    python -m venv ..\\.venv",
            "    ..\\.venv\\Scripts\\pip install -r requirements.txt",
        ])
    else:
        lines.extend([
            "  Instala las dependencias en el venv activo:",
            "    pip install -r requirements.txt",
        ])
    lines.append("=" * 60)
    pytest.exit("\n".join(lines), returncode=1)
