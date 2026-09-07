"""C-1470: 「難易度を上げて／下げて」 changes difficulty like 「難しく／簡単に」.

The revision detector knew the adjectival words but not the explicit idiom; the
change-verb gate also lacked 上げて/下げて. Both are recognised now, and the
ambiguous 「レベルを上げて」 still maps to no difficulty change.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.revise import detect_revision_intent
from sidra_ai.evals.revision_difficulty_idiom import evaluate_revision_difficulty_idiom


def test_revision_difficulty_eval_passes():
    result = evaluate_revision_difficulty_idiom()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 13


@pytest.mark.parametrize(
    "message",
    ["これの難易度を上げて", "これの難易度を上げる", "これの難易度をあげて", "これの難易度を高くして"],
)
def test_explicit_harder_idiom(message):
    intent = detect_revision_intent(message)
    assert intent.is_revision
    assert intent.adjustments.get("difficulty") == "+1"


@pytest.mark.parametrize(
    "message",
    ["これの難易度を下げて", "これの難易度を下げる", "これの難易度をさげて", "これの難易度を低くして"],
)
def test_explicit_easier_idiom(message):
    intent = detect_revision_intent(message)
    assert intent.is_revision
    assert intent.adjustments.get("difficulty") == "-1"


def test_polite_difficulty_idiom_composes():
    intent = detect_revision_intent("これの難易度を上げてもらえますか")
    assert intent.is_revision
    assert intent.adjustments.get("difficulty") == "+1"


@pytest.mark.parametrize(
    "message",
    ["これを難しくして", "これを簡単にして"],
)
def test_adjectival_forms_unchanged(message):
    assert detect_revision_intent(message).is_revision


def test_ambiguous_level_up_is_not_difficulty():
    assert "difficulty" not in detect_revision_intent("これのレベルを上げて").adjustments


def test_band_change_not_pulled_into_difficulty():
    adj = detect_revision_intent("これの敵を増やして").adjustments
    assert adj.get("band") == "+1"
    assert "difficulty" not in adj
