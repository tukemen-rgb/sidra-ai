"""C-1805: the 3D preview fallback note drops its bracket quote of the request.

A bare 「3Dモデルを作って」 titled the model 「魚」 (the default shape's own name)
and the note read 「依頼「魚」に合う形状が無かったため…既定の「魚」」 - self-
contradictory. The note now uses the chat summary's subject-less framing; the
subject stays in the title, the default disclosure and shape list are unchanged,
and a named shape carries no note. Sibling of C-1801 (the art note).
"""

from __future__ import annotations

from sidra_ai.creation.models3d import generate_model3d
from sidra_ai.evals.model3d_note_matches_summary_framing import (
    evaluate_model3d_note_matches_summary_framing,
)

_NOTE_MARK = '<p id="shape-note">'


def _note(html: str) -> str:
    return html.split(_NOTE_MARK, 1)[1].split("</p>", 1)[0] if _NOTE_MARK in html else ""


def test_model3d_note_framing_eval_passes():
    result = evaluate_model3d_note_matches_summary_framing()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_bare_request_note_has_no_self_contradicting_quote():
    note = _note(generate_model3d("3Dモデルを作って").preview_html)
    assert "依頼「魚」" not in note
    assert "依頼に合う形状が無かった" in note
    assert "既定の「魚」" in note


def test_named_unavailable_subject_stays_in_title_not_the_note():
    model = generate_model3d("ドラゴンの3Dモデルを作って")
    assert "<h1>ドラゴン</h1>" in model.preview_html  # subject preserved
    assert "依頼「ドラゴン」" not in _note(model.preview_html)  # not bracket-quoted


def test_named_available_shape_has_no_note():
    assert _NOTE_MARK not in generate_model3d("舟の3Dモデルを作って").preview_html
