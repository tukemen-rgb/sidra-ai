"""C-1479: an English "3D model" request routes to the 3D generator, not a game.

GAME_WORDS carries "3d" and MODEL3D's cue "3d model" matched at the same index,
so the same-position tie-break (dict order, GAME first) built a game for
「make a 3D model」. The tie-break now prefers the longer, more specific cue, so
"3d model" beats "3d"; a 3D *game* still routes to GAME because a later game word
wins by position, not by a tie.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.creation_english_3d_model_not_game import (
    evaluate_creation_english_3d_model_not_game,
)


def _kind(message: str) -> str:
    return detect_creation_intent(message).kind.value


def test_english_3d_model_eval_passes():
    result = evaluate_creation_english_3d_model_not_game()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


@pytest.mark.parametrize("message", [
    "make a 3D model",
    "build a 3D model of a house",
    "create a 3d model of a car",
])
def test_english_3d_model_routes_to_model3d(message):
    assert _kind(message) == "model3d"


@pytest.mark.parametrize("message", ["3Dゲームを作って", "make a 3d game"])
def test_a_3d_game_is_still_a_game(message):
    assert _kind(message) == "game"


def test_japanese_3d_model_unchanged():
    assert _kind("3Dモデルを作って") == "model3d"
