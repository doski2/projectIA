"""
drive_actions.py
Utilidades compartidas para mezclar y codificar acciones de conducción.
"""

from __future__ import annotations


def blend_actions(bc: tuple, teacher: tuple, alpha: float) -> tuple:
    """Mezcla acciones físicas (throttle, brake, steering) con peso alpha sobre BC."""
    a = max(0.0, min(1.0, alpha))
    return (
        a * bc[0] + (1.0 - a) * teacher[0],
        a * bc[1] + (1.0 - a) * teacher[1],
        a * bc[2] + (1.0 - a) * teacher[2],
    )
