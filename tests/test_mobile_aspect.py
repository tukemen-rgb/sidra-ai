"""C-1204: generated canvases must keep their intrinsic ratio when scaled.

The shared game shell used ``width:100%;height:320px``: exact at desktop's
720px content width, 2x horizontal squash at phone widths - every template,
every phone, invisible on every PC. ``height:auto`` preserves the ratio the
canvas gets from its width/height attributes at any width.
"""

from __future__ import annotations

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.models3d import generate_model3d
from sidra_ai.evals.mobile_aspect import evaluate_mobile_aspect, page_keeps_aspect


def test_game_shell_scales_without_pinned_height():
    html = generate_game("シューティングゲームを作って").html
    ok, reason = page_keeps_aspect(html)
    assert ok, reason
    assert "height:auto" in html
    assert "height:320px" not in html


def test_model3d_preview_scales_without_distortion():
    html = generate_model3d("魚の3Dモデルを作って").preview_html
    ok, reason = page_keeps_aspect(html)
    assert ok, reason


def test_pinned_pixel_height_is_flagged():
    page = '<canvas width="720" height="320"></canvas><style>canvas{width:100%;height:320px}</style>'
    ok, reason = page_keeps_aspect(page)
    assert not ok
    assert "distorts" in reason


def test_scaled_width_without_height_rule_is_flagged():
    page = '<canvas width="640" height="480"></canvas><style>canvas{max-width:100%}</style>'
    ok, _ = page_keeps_aspect(page)
    assert not ok


def test_unscaled_canvas_is_not_a_distortion():
    page = '<canvas width="640" height="480"></canvas><style>canvas{border:0}</style>'
    ok, _ = page_keeps_aspect(page)
    assert ok


def test_mobile_aspect_eval_passes():
    result = evaluate_mobile_aspect()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 3
