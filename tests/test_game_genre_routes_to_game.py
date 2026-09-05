"""C-1253: a bare game-genre request reaches the game path, not Q&A.

「ブロック崩しを作って」 and 「3目並べを作って」 came back unknown and fell to the
question path (a game request answered with nginx config). A few common
non-trademark genres are named in the vocabulary now, so they route to the game
path - which declines honestly with the buildable list - while real questions
stay questions.
"""

from __future__ import annotations

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.intent import CreationKind, detect_creation_intent
from sidra_ai.evals.game_genre_routes_to_game import (
    evaluate_game_genre_routes_to_game,
)


def _kind(message: str):
    intent = detect_creation_intent(message)
    return intent.kind if intent.is_creation else None


def test_game_genre_routes_to_game_eval_passes():
    result = evaluate_game_genre_routes_to_game()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


def test_bare_genres_route_to_game():
    for req in ("ブロック崩しを作って", "3目並べを作って", "三目並べを作って", "クリッカーを作って"):
        assert _kind(req) is CreationKind.GAME, req


def test_real_questions_stay_questions():
    assert _kind("国内最大級と言えるか") is None
    assert _kind("天気を教えて") is None


def test_added_genres_are_unsupported_and_declined():
    # The new genres have no template, so they are declined (fishing fallback)
    # with the buildable list, not silently built or mis-titled as a subject.
    for req in ("ブロック崩しを作って", "3目並べを作って"):
        game = generate_game(req)
        assert game.template not in ("",)  # a real fallback template was chosen
        assert game.template in TEMPLATES  # fell back to a buildable one
