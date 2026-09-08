"""C-1480: English words for the abstract art SIDRA makes reach the ART kind.

ART carried only "generative art"/"artwork" in English, so 「make a wallpaper」
「make abstract art」「make digital art」 fell to UNKNOWN though Japanese 「壁紙」
「アート」 route to ART. The cues now include wallpaper/abstract art/digital art.
A depiction (illustration, drawing, picture) is still declined in both languages
because the generator makes abstract art, not a likeness.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.creation_english_art_parity import (
    evaluate_creation_english_art_parity,
)


def _kind(message: str) -> str:
    return detect_creation_intent(message).kind.value


def test_english_art_parity_eval_passes():
    result = evaluate_creation_english_art_parity()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 10


@pytest.mark.parametrize("message", [
    "make a wallpaper",
    "make abstract art",
    "make digital art",
])
def test_english_abstract_art_routes_to_art(message):
    assert _kind(message) == "art"


@pytest.mark.parametrize("message", ["make an illustration", "make a drawing", "make a chart"])
def test_a_depiction_or_unrelated_word_does_not_route_to_art(message):
    assert _kind(message) != "art"


def test_japanese_art_unchanged():
    assert _kind("壁紙を作って") == "art"
    assert _kind("アートを作って") == "art"
