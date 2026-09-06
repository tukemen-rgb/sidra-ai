"""C-1283: the 3D preview page discloses the fish default it fell back to.

A request that names no shape is built as the fish default. The chat summary
says so (C-1267), but the preview HTML - opened in a browser and forwarded -
was titled by the subject over a fish mesh with no word of it, the silent
artifact C-1281 fixed for the report. The preview now carries a disclosure note
under the title when the shape was a default, and stays clean when named.
"""

from __future__ import annotations

from sidra_ai.creation.models3d import generate_model3d, validate_model3d
from sidra_ai.evals.model3d_preview_discloses_default_shape import (
    evaluate_model3d_preview_discloses_default_shape,
)

_NOTE_MARK = '<p id="shape-note">'


def test_model3d_preview_discloses_default_shape_eval_passes():
    result = evaluate_model3d_preview_discloses_default_shape()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


def test_fallback_preview_discloses_the_fish_default():
    model = generate_model3d("ドラゴンの 3D モデルを作って")
    assert model.shape == "fish" and not model.shape_named
    assert _NOTE_MARK in model.preview_html
    assert "既定の「魚」" in model.preview_html
    assert all(s in model.preview_html for s in ("魚", "舟", "地形"))
    # the subject stays the title - both the user's word and the real shape show
    assert "<h1>ドラゴン</h1>" in model.preview_html


def test_named_shape_preview_carries_no_note():
    for req, shape in (("魚の 3D モデルを作って", "fish"),
                       ("舟の 3D モデルを作って", "boat"),
                       ("地形の 3D モデルを作って", "terrain")):
        model = generate_model3d(req)
        assert model.shape == shape and model.shape_named
        assert _NOTE_MARK not in model.preview_html


def test_disclosure_note_has_no_fabricated_number_and_preview_valid():
    model = generate_model3d("猫の 3D モデルを作って")
    note = model.preview_html.split(_NOTE_MARK, 1)[1].split("</p>", 1)[0]
    assert not any(ch.isdigit() for ch in note)
    assert validate_model3d(model)["valid"]
