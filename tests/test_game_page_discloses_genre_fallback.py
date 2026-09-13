"""C-1788: game.html discloses a substituted genre, not just the chat summary.

A request for a genre SIDRA cannot build (「格闘」) or a subject with no template
(「猫」) gets the default template; game.html now carries the page-shaped
genre_fallback_note (already used by the project flow), while a buildable genre
adds no such note.
"""

from __future__ import annotations

from sidra_ai.creation.games import generate_game
from sidra_ai.evals.game_page_discloses_genre_fallback import (
    evaluate_game_page_discloses_genre_fallback,
)

_NOTE = "代わりに既定"


def test_game_fallback_page_eval_passes():
    result = evaluate_game_page_discloses_genre_fallback()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


def test_declined_genre_is_disclosed_on_the_page():
    html = generate_game("格闘ゲームを作って").html
    assert _NOTE in html
    assert "<canvas" in html and "<script" in html  # still playable


def test_subject_without_a_template_is_disclosed():
    assert _NOTE in generate_game("猫のゲームを作って").html


def test_a_buildable_genre_adds_no_fallback_note():
    assert _NOTE not in generate_game("パズルゲームを作って").html
