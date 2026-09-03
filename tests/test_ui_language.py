"""C-1207: the ask page must speak Japanese, not declare it and speak English.

The page carried ``<html lang="ja">`` while the intro, form labels, button,
statuses and error prefixes were English - the doorway equivalent of the
answer-language incident rule 6 was written against. The security shape of
the page (textContent-only rendering, no innerHTML) is asserted elsewhere
and must survive the wording change untouched.
"""

from __future__ import annotations

from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.ui_language import evaluate_ui_language


def test_no_english_boilerplate_faces_the_operator():
    for english in (
        "Ask a question", "API token", "Generated files", '"Sources"',
        '"Asking', "Listing failed", "Download failed",
    ):
        assert english not in ASK_PAGE, english


def test_japanese_labels_are_present():
    for japanese in ("質問", "アクセストークン", "送信", "生成ファイル", "出典", "問い合わせ中"):
        assert japanese in ASK_PAGE, japanese


def test_render_stays_text_only():
    """The translation must not loosen the DOM-injection posture."""

    assert "innerHTML" not in ASK_PAGE
    assert "textContent" in ASK_PAGE


def test_ui_language_eval_passes():
    result = evaluate_ui_language()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total
