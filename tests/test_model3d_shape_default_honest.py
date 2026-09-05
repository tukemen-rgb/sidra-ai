"""C-1267: a 3D model names its shape and says when it fell back to the default.

「猫の3Dモデルを作って」 built the fish mesh and the summary named no shape. Now
every summary names the shape, an unnamed request says the default was used and
lists the shapes, and a named shape (魚/船/地形) stays silent. The mesh is
unchanged.
"""

from __future__ import annotations

from sidra_ai.creation.models3d import (
    DEFAULT_SHAPE,
    generate_model3d,
    named_shape,
    validate_model3d,
)
from sidra_ai.evals.model3d_shape_default_honest import (
    evaluate_model3d_shape_default_honest,
)


def test_model3d_shape_default_honest_eval_passes():
    result = evaluate_model3d_shape_default_honest()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 13


def test_named_shape_distinguishes_default_from_explicit():
    assert named_shape("魚の3Dモデルを作って") == "fish"
    assert named_shape("船の3Dモデルを作って") == "boat"
    assert named_shape("地形の3Dモデルを作って") == "terrain"
    assert named_shape("猫の3Dモデルを作って") is None
    assert named_shape("3Dモデルを作って") is None


def test_generated_model_records_whether_shape_was_named():
    assert generate_model3d("魚の3Dモデルを作って").shape_named is True
    assert generate_model3d("猫の3Dモデルを作って").shape_named is False
    # An explicit shape= is the caller naming it, even from a vague request.
    assert generate_model3d("猫の3Dモデルを作って", shape="boat").shape_named is True


def test_default_still_builds_a_valid_mesh():
    model = generate_model3d("ドラゴンの3Dモデルを作って")
    assert model.shape == DEFAULT_SHAPE
    assert model.shape_named is False
    assert validate_model3d(model)["valid"] is True
