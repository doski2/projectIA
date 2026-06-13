"""
Configuración compartida de pytest para PCARS2-AI.

Añade el directorio `src/` al `sys.path` para que los tests puedan importar
los módulos del proyecto (`reference_recorder`, `controller`, `monitor`, `main`)
exactamente como hacen entre sí (imports planos, sin paquete).
"""

import os
import sys

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
