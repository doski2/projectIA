"""Tests para selección unificada de checkpoints."""

import os

from checkpoints import resolve_combo_checkpoint


def _touch(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("")


def test_resolve_prefers_max_steps_over_final(tmp_path):
    model_dir = tmp_path / "formula_rookie__sugo"
    prefix = "pcars2_formula_rookie__sugo"
    _touch(str(model_dir / f"{prefix}_final.zip"))
    _touch(str(model_dir / f"{prefix}_150000_steps.zip"))

    result = resolve_combo_checkpoint(str(model_dir), prefix)
    assert result is not None
    assert result.endswith(f"{prefix}_150000_steps")


def test_resolve_uses_final_when_no_steps(tmp_path):
    model_dir = tmp_path / "formula_rookie__sugo"
    prefix = "pcars2_formula_rookie__sugo"
    _touch(str(model_dir / f"{prefix}_final.zip"))

    result = resolve_combo_checkpoint(str(model_dir), prefix)
    assert result is not None
    assert result.endswith(f"{prefix}_final")
