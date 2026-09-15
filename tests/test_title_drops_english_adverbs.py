"""C-1842: 「right now」 is not what the artifact is called.

English puts these at the end, and all 30 titles across five adverbs and six
generators kept them; the Japanese equivalents have come off since C-1829.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.documents import generate_document
from sidra_ai.creation.games import generate_game
from sidra_ai.creation.vocabulary import drop_english_frame
from sidra_ai.evals.title_drops_english_adverbs import (
    ADVERBS,
    SHAPES,
    _title,
    evaluate_title_drops_english_adverbs,
)


def test_english_adverb_eval_passes():
    result = evaluate_title_drops_english_adverbs()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 9


@pytest.mark.parametrize(("kind", "shape", "subject"), SHAPES)
@pytest.mark.parametrize("adverb", ADVERBS)
def test_the_title_is_the_subject_not_the_adverb(kind, shape, subject, adverb):
    assert _title(kind, shape.format(adverb)) == subject


def test_a_subject_that_is_one_of_those_words_survives():
    # 「write a report about today」 is a report about today.
    assert generate_document("write a report about today").title == "today"
    assert (
        generate_document("write a report about today's sales").title == "today's sales"
    )


def test_two_stacked_adverbs_both_come_off():
    assert generate_game("make a racing game quickly right now").title == "racing"


def test_a_request_with_no_adverb_is_unchanged():
    assert generate_game("make a racing game").title == "racing"
    assert generate_game("please make a puzzle game").title == "puzzle"
    assert drop_english_frame("make a gif of a fish") == "fish"


def test_japanese_is_unchanged():
    assert generate_game("猫のゲームを作って").title == "猫"
    assert generate_document("収益化のレポートを作って").title == "収益化"
