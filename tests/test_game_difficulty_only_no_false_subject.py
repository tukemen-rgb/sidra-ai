"""C-1235: a difficulty-only game request names no undrawn subject.

「むずかしいゲームを作って」 read the difficulty (hard) correctly, then turned
the same word into a subject - the page was titled 「むずかしい」 and the summary
claimed 「『むずかしい』の題材を描く型はまだ無い」. A word consumed as the
difficulty is not an undrawn subject; the request named none, like the bare
「ゲームを作って」. A real subject and a named genre stay untouched.
"""

from __future__ import annotations

import tempfile

from sidra_ai.creation.game_job import build_game_generator
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.game_difficulty_only_no_false_subject import (
    evaluate_game_difficulty_only_no_false_subject,
)


def _summary(request: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        return build_game_generator(tmp)(request, detect_creation_intent(request)).summary


def test_difficulty_only_eval_passes():
    result = evaluate_game_difficulty_only_no_false_subject()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 12


def test_difficulty_only_request_has_no_false_subject():
    for request, word, difficulty in (
        ("むずかしいゲームを作って", "むずかしい", "hard"),
        ("簡単なゲームを作って", "簡単", "easy"),
        ("初心者向けのゲームを作って", "初心者", "easy"),
    ):
        s = _summary(request)
        assert "題材を描く型はまだ無い" not in s
        assert f"難易度 {difficulty}" in s
        assert generate_game(request).title == "タイミング釣り"
        assert word not in generate_game(request).title


def test_real_subject_and_difficulty_kept():
    # A real subject still earns its caveat, and difficulty+subject keeps both.
    assert "題材を描く型はまだ無い" in _summary("猫のゲームを作って")
    both = _summary("むずかしい猫のゲームを作って")
    assert "猫" in both and "難易度 hard" in both
