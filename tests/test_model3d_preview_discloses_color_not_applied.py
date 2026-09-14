"""C-1818: the 3D preview page discloses that a requested colour was not applied.

A request that names a colour (「赤い魚の3Dモデル」) is titled with it over a
fixed-palette mesh; the chat summary said the colour was not applied but the
forwarded preview page did not. The preview now carries the colour caveat, the
sibling of the shape-default note (C-1805). A colourless request gets no note.
"""

from __future__ import annotations

from sidra_ai.creation.models3d import generate_model3d
from sidra_ai.evals.model3d_preview_discloses_color_not_applied import (
    evaluate_model3d_preview_discloses_color_not_applied,
)

_MARK = "反映していません"


def test_model3d_color_note_eval_passes():
    result = evaluate_model3d_preview_discloses_color_not_applied()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_colour_request_discloses_it_was_not_applied():
    html = generate_model3d("赤い魚の3Dモデルを作って").preview_html
    assert _MARK in html
    assert "<h1>赤い魚</h1>" in html  # the subject stays in the title


def test_colourless_request_has_no_colour_note():
    assert _MARK not in generate_model3d("魚の3Dモデルを作って").preview_html


def test_colour_and_shape_default_both_disclosed():
    html = generate_model3d("青い猫の3Dモデルを作って").preview_html
    assert _MARK in html  # colour caveat
    assert "既定の「魚」" in html  # C-1805 shape-default note preserved
