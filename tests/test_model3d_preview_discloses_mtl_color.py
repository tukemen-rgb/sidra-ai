"""C-1784: the 3D preview page warns that colour comes from the .mtl.

C-1617 added the .mtl colour caveat only to the chat summary, but the preview
HTML is the primary artifact and told the user to open the .obj (which opens grey
without its sibling .mtl). The preview note now carries the caveat too, the
self-disclosure C-1283 requires.
"""

from __future__ import annotations

from sidra_ai.creation.models3d import generate_model3d
from sidra_ai.evals.model3d_preview_discloses_mtl_color import (
    evaluate_model3d_preview_discloses_mtl_color,
)


def test_model3d_preview_mtl_eval_passes():
    result = evaluate_model3d_preview_discloses_mtl_color()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_preview_note_names_the_mtl_and_keeps_the_obj_guidance():
    html = generate_model3d("3Dモデルを作って").preview_html
    assert ".mtl" in html
    assert "色" in html and ("隣" in html or "一緒" in html)
    assert "開けます" in html  # the open-the-.obj guidance stays


def test_named_shape_preview_still_carries_the_mtl_note():
    html = generate_model3d("魚の3Dモデルを作って", shape="fish").preview_html
    assert ".mtl" in html
    assert "既定" not in html  # a named shape shows no default-shape note
