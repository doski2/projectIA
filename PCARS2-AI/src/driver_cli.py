"""
driver_cli.py
Flags CLI compartidos entre teaching / imitation / learn drivers.
"""

from __future__ import annotations

import argparse


def ns_str(args: argparse.Namespace, key: str) -> str:
    """Lee un campo del Namespace como str (evita reportArgumentType en basedpyright)."""
    value = getattr(args, key)
    if isinstance(value, str):
        return value
    return str(value)


def add_safety_profile_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--safety-profile",
        choices=["strict", "l1_margin"],
        default="l1_margin",
        help="strict: 1 rueda en hierba frena. l1_margin: volante/gas con 1–2 ruedas; freno con 3",
    )


def add_diag_track_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--diag-track",
        action="store_true",
        help="JSONL: posición, terreno por rueda, match espacial (ver track_deviation.py)",
    )
