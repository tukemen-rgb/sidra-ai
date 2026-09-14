"""C-1606: 「描いて」 (draw) is a make request, like 「書いて」 (write).

Without it a bare 「絵を描いて」 was not read as a creation ask and fell to the
no-evidence answer that sends a maker to repo ingestion (C-1261); 「アートを描いて」
was missed too. A question about drawing stays a question.
"""

from __future__ import annotations

from sidra_ai.creation.intent import CreationKind, detect_creation_intent
from sidra_ai.evals.draw_verb_is_a_make_request import (
    evaluate_draw_verb_is_a_make_request,
)


def test_draw_verb_eval_passes():
    result = evaluate_draw_verb_is_a_make_request()
    assert result.failures == ()
    # Derived rather than pinned to a literal (C-1804): a hard-coded count has
    # to be edited by hand every time a case is added, and a stale one lets a
    # failing check report a full score.
    assert result.checks_passed == result.checks_total
    assert result.checks_total >= 12


def test_bare_draw_request_is_a_creation_ask():
    """A draw request naming no buildable kind is still a creation ask.

    C-1804 took 「絵を描いて」「イラストを描いて」 out of this list: they name a kind
    after all - 絵 and イラスト are the ordinary Japanese for the generative art
    this product makes - and they are asserted at ART in
    tests/test_draw_request_makes_art.py. 画-words carry no such cue and are
    what this check was really about.
    """

    for req in ("風景画を描いて", "肖像画を描いて"):
        it = detect_creation_intent(req)
        assert it.is_creation and it.kind is CreationKind.UNKNOWN, req


def test_draw_request_naming_art_routes_to_art():
    assert detect_creation_intent("アートを描いて").kind is CreationKind.ART
    assert detect_creation_intent("壁紙を描いて").kind is CreationKind.ART


def test_question_about_drawing_is_not_creation():
    assert detect_creation_intent("絵はどう描かれますか").is_creation is False
