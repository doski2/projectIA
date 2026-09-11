"""
Tests de la selección automática de checkpoint (`main._find_best_model`).

Esta es la lógica que decide DESDE DÓNDE se continúa el entrenamiento:
  1. modelo final del combo            → continuar
  2. checkpoint más reciente del combo → continuar
  3. modelo base (otro combo)          → transfer learning
  4. nada                               → entrenar desde cero (None)

Un fallo aquí significa "continuar" entrenando desde el modelo equivocado
(o desde cero perdiendo el progreso), por eso conviene blindarlo.

Importar `main` arrastra torch; si no estuviera disponible se omite el módulo.
"""

import os

import pytest

pytest.importorskip("torch")

from main import _find_best_model


def _touch(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("")


def test_prefers_final_over_checkpoints(tmp_path):
    models_root = str(tmp_path)
    subdir = "formula_rookie__sugo"
    prefix = f"pcars2_{subdir}"
    model_dir = os.path.join(models_root, subdir)

    _touch(os.path.join(model_dir, f"{prefix}_final.zip"))
    _touch(os.path.join(model_dir, f"{prefix}_90000_steps.zip"))

    result = _find_best_model(model_dir, prefix, models_root, subdir)
    assert result is not None
    assert result["mode"] == "continue"
    assert result["path"].endswith(f"{prefix}_final")
    assert not result["path"].endswith(".zip")  # SB3 no quiere extensión


def test_picks_latest_checkpoint_when_no_final(tmp_path):
    models_root = str(tmp_path)
    subdir = "formula_rookie__sugo"
    prefix = f"pcars2_{subdir}"
    model_dir = os.path.join(models_root, subdir)

    # Mismo ancho de dígitos → orden alfabético == orden numérico
    _touch(os.path.join(model_dir, f"{prefix}_10000_steps.zip"))
    _touch(os.path.join(model_dir, f"{prefix}_50000_steps.zip"))
    _touch(os.path.join(model_dir, f"{prefix}_90000_steps.zip"))

    result = _find_best_model(model_dir, prefix, models_root, subdir)
    assert result is not None
    assert result["mode"] == "continue"
    assert result["path"].endswith(f"{prefix}_90000_steps")


def test_transfer_from_base_when_combo_empty(tmp_path):
    models_root = str(tmp_path)
    subdir = "nuevo_coche__nueva_pista"
    prefix = f"pcars2_{subdir}"
    model_dir = os.path.join(models_root, subdir)
    os.makedirs(model_dir, exist_ok=True)  # combo sin modelos

    # Pero sí existe un modelo base entrenado
    base_dir = os.path.join(models_root, "base")
    _touch(os.path.join(base_dir, "pcars2_base_final.zip"))

    result = _find_best_model(model_dir, prefix, models_root, subdir)
    assert result is not None
    assert result["mode"] == "transfer"
    assert result["path"].endswith("pcars2_base_final")


def test_none_when_nothing_available(tmp_path):
    models_root = str(tmp_path)
    subdir = "combo_vacio"
    prefix = f"pcars2_{subdir}"
    model_dir = os.path.join(models_root, subdir)
    os.makedirs(model_dir, exist_ok=True)

    result = _find_best_model(model_dir, prefix, models_root, subdir)
    assert result is None


def test_picks_highest_step_count_not_alphabetic(tmp_path):
    """90000 ordena después de 300000 alfabéticamente — debe ganar el mayor número."""
    models_root = str(tmp_path)
    subdir = "formula_rookie__sugo"
    prefix = f"pcars2_{subdir}"
    model_dir = os.path.join(models_root, subdir)

    _touch(os.path.join(model_dir, f"{prefix}_90000_steps.zip"))
    _touch(os.path.join(model_dir, f"{prefix}_300000_steps.zip"))

    result = _find_best_model(model_dir, prefix, models_root, subdir)
    assert result is not None
    assert result["path"].endswith(f"{prefix}_300000_steps")


def test_base_combo_does_not_self_transfer(tmp_path):
    # Si el combo ES "base" y no tiene modelos, no debe intentar transfer de sí mismo
    models_root = str(tmp_path)
    subdir = "base"
    prefix = "pcars2_base"
    model_dir = os.path.join(models_root, subdir)
    os.makedirs(model_dir, exist_ok=True)

    result = _find_best_model(model_dir, prefix, models_root, subdir)
    assert result is None
