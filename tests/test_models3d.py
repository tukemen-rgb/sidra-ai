"""The 3D generator must produce files that open, deterministically.

"Opens in a viewer" cannot be tested here, but its preconditions can: a
well-formed OBJ whose face indices exist, a material file with diffuse
colours, and a preview page whose script parses and references nothing
outside the file. Determinism is pinned because seeded generation is the
promise that lets an operator regenerate the same asset tomorrow.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.intent import CreationKind, detect_creation_intent
from sidra_ai.creation.models3d import (
    choose_shape,
    generate_model3d,
    save_model3d,
    validate_model3d,
)
from sidra_ai.creation.router import build_default_router


@pytest.mark.parametrize("shape", ["fish", "boat", "terrain"])
def test_every_shape_generates_a_valid_model(shape: str) -> None:
    model = generate_model3d("3Dモデルを作って", shape=shape)
    verdict = validate_model3d(model)
    assert verdict["valid"], verdict["failures"]
    assert verdict["vertices"] > 0 and verdict["faces"] > 0


def test_generation_is_deterministic_for_the_same_request() -> None:
    a = generate_model3d("魚の3Dモデルを作って")
    b = generate_model3d("魚の3Dモデルを作って")
    assert a.obj_text == b.obj_text
    assert a.seed == b.seed


def test_different_requests_vary_the_geometry() -> None:
    a = generate_model3d("魚の3Dモデルを作って")
    b = generate_model3d("大きな魚の3Dモデルを作って")
    assert a.obj_text != b.obj_text


def test_shape_is_chosen_from_the_request() -> None:
    assert choose_shape("舟の3Dモデル") == "boat"
    assert choose_shape("島の地形モデル") == "terrain"
    assert choose_shape("なにか立体を") == "fish"


def test_materials_stay_on_the_gameyard_palette() -> None:
    model = generate_model3d("3Dモデルを作って")
    assert "newmtl gy_cyan" in model.mtl_text
    assert "newmtl gy_dark" in model.mtl_text
    # The preview background is the DESIGN.md dark foundation.
    assert "#05070f" in model.preview_html


def test_preview_is_self_contained_and_motion_aware() -> None:
    model = generate_model3d("3Dモデルを作って")
    assert "http://" not in model.preview_html
    assert "https://" not in model.preview_html
    assert "prefers-reduced-motion" in model.preview_html


def test_save_writes_the_three_files_and_links_the_mtl(tmp_path) -> None:
    model = generate_model3d("魚の3Dモデルを作って")
    paths = save_model3d(model, tmp_path)
    for key in ("obj", "mtl", "preview"):
        assert paths[key].exists(), key
    obj_text = paths["obj"].read_text(encoding="utf-8")
    assert f"mtllib {paths['mtl'].name}" in obj_text


def test_intent_routes_model_requests_but_not_questions() -> None:
    assert detect_creation_intent("魚の3Dモデルを作って").kind is CreationKind.MODEL3D
    assert not detect_creation_intent("3Dモデルの作り方を教えて").is_creation
    # The game path must not have been stolen by the new vocabulary.
    assert detect_creation_intent("釣りゲームを作って").kind is CreationKind.GAME


def test_router_builds_a_model_end_to_end(tmp_path) -> None:
    router = build_default_router(data_dir=str(tmp_path))
    intent = detect_creation_intent("舟の3Dモデルを作って")
    outcome = router.route("舟の3Dモデルを作って", intent)
    assert outcome.handled
    assert outcome.details["valid"] is True
    assert outcome.artifact_path.endswith("-preview.html")
