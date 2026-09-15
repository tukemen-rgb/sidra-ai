"""C-1873: the advice, sent back verbatim, works.

The refusal printed 「難易度は easy / normal / hard の 3 段です」 and refused all
three. C-1868's own check was named "the advice WORKS" and ran 「難しくして」 - a
phrase the advice does not print - so it never saw this.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.revise import _LADDER, detect_revision_intent
from sidra_ai.creation.themes import THEMES, named_theme, select_theme
from sidra_ai.evals.printed_advice_actually_works import (
    VALUE_FIELDS,
    evaluate_printed_advice_actually_works,
    offered_values,
)


def test_printed_advice_eval_passes():
    result = evaluate_printed_advice_actually_works()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 26


@pytest.mark.parametrize("key,_shape", VALUE_FIELDS)
def test_the_values_come_from_the_printed_sentence(key, _shape):
    """Nothing in the eval names a rung or a colour; it reads them back."""

    assert len(offered_values(key, "adventure")) >= 2


@pytest.mark.parametrize("rung", _LADDER)
def test_every_rung_can_be_named(rung):
    intent = detect_revision_intent(f"さっきのゲームの難易度を {rung} にして")
    assert intent.adjustments.get("difficulty") == f"={rung}"


def test_naming_the_default_theme_is_naming_a_theme():
    """The hole the eval found on its first run.

    select_theme collapses 「named nothing」 into the default, so 「gameyard の
    テーマにして」 and saying nothing were the same answer - while the advice
    offers gameyard as one of the four.
    """

    assert named_theme("さっきのゲームをgameyardのテーマにして") is THEMES["gameyard"]
    assert named_theme("さっきのゲームを難しくして") is None
    # ...and select_theme keeps its old job for the callers that pick a palette.
    assert select_theme("さっきのゲームを難しくして") is THEMES["gameyard"]


def test_a_colour_word_alone_is_not_a_theme():
    """「白」 is one of paper's words; without the cue it is an accent."""

    assert named_theme("さっきのゲームを白くして") is None
    assert detect_revision_intent("さっきのゲームを白くして").adjustments.get("theme") is None
