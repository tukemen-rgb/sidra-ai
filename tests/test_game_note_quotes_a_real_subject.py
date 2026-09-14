"""C-1825: the game's 「その題材は描けない」 note must quote an actual subject.

Measured across twenty requests naming no genre, it fired nineteen times and
was true three. The sixteen others quoted an adjective, the device the game
runs on, or a count of levels or seconds - and the device case denied
something the product does, since the games are playable on a phone.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.games import (
    TEMPLATES,
    choose_difficulty,
    generate_game,
    genre_fallback_note,
    names_no_subject,
)
from sidra_ai.evals.game_note_quotes_a_real_subject import (
    NOT_A_SUBJECT,
    REAL_SUBJECT,
    evaluate_game_note_quotes_a_real_subject,
)

_CAVEAT = "の題材を描く型はまだ無い"


def _note(request: str) -> str:
    game = generate_game(request)
    return genre_fallback_note(request, game.template, game.title)


def test_game_subject_note_eval_passes():
    result = evaluate_game_note_quotes_a_real_subject()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


@pytest.mark.parametrize("request_text", NOT_A_SUBJECT)
def test_a_word_that_names_no_subject_draws_no_caveat(request_text):
    assert _note(request_text) == ""


@pytest.mark.parametrize("request_text", REAL_SUBJECT)
def test_a_real_subject_still_draws_the_caveat(request_text):
    assert _CAVEAT in _note(request_text)


def test_such_a_request_takes_the_templates_own_title():
    game = generate_game("スマホで遊べるゲームを作って")
    assert game.title == TEMPLATES[game.template].default_title


def test_the_difficulty_case_is_unchanged():
    game = generate_game("難しいゲームを作って")
    assert game.title == TEMPLATES[game.template].default_title
    assert choose_difficulty("難しいゲームを作って") == "hard"
    assert _note("難しいゲームを作って") == ""


def test_an_adjective_in_front_of_a_subject_is_still_a_subject():
    assert _CAVEAT in _note("かわいい猫のゲームを作って")


def test_the_guard_reads_the_word_not_the_grammar():
    assert names_no_subject("スマホで遊べる")
    assert names_no_subject("3面")
    assert names_no_subject("面白い")
    assert not names_no_subject("猫")
    assert not names_no_subject("かわいい猫")
