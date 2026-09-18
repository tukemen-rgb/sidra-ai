"""C-1480: English words for the abstract art SIDRA makes reach the ART kind.

ART carried only "generative art"/"artwork" in English, so 「make a wallpaper」
「make abstract art」「make digital art」 fell to UNKNOWN though Japanese 「壁紙」
「アート」 route to ART. The cues now include wallpaper/abstract art/digital art.
C-1948 corrected the rest: a depiction (illustration, drawing, picture) is NOT
declined. 「絵」 and 「イラスト」 have routed to ART since C-1804, and the product
makes the abstract art and says 「依頼にあった題材は描いていません」 - measured
through the real router. So the depiction cases below are parity checks: the
two languages must read the same request the same way.
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


@pytest.mark.parametrize(
    ("english", "japanese"),
    [("make an illustration", "イラストを作って"), ("make a drawing", "絵を作って")],
)
def test_a_depiction_reads_the_same_in_both_languages(english, japanese):
    assert _kind(english) == _kind(japanese)


def test_an_unrelated_word_containing_art_does_not_route_to_art():
    # The reason bare "art" stays out of the cue list (C-1480), kept.
    assert _kind("make a chart") != "art"
    assert _kind("make a smart report") == "document"


def test_japanese_art_unchanged():
    assert _kind("壁紙を作って") == "art"
    assert _kind("アートを作って") == "art"
