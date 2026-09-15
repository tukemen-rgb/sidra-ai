"""C-1853: a revision moves the thing that was named, or nothing.

「さっきのゲームの宝石をもっと増やして」 wrote a new version of an adventure with
「敵の数 4」 and announced that as the requested change. The band words had always
fired on the verb; nothing had ever read the object.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.revise import band_owner, detect_revision_intent, names_the_band
from sidra_ai.creation.tuning import AXIS_LABELS
from sidra_ai.evals.revision_changes_what_was_named import (
    NOT_THE_AXIS,
    evaluate_revision_changes_what_was_named,
)


def test_revision_changes_what_was_named_eval_passes():
    result = evaluate_revision_changes_what_was_named()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 20


@pytest.mark.parametrize("template", sorted(AXIS_LABELS))
def test_every_template_names_the_thing_its_axis_counts(template):
    """The owner is the head noun, not the whole label.

    A person types 「敵を増やして」, never 「敵の数を増やして」, so an owner that
    kept the 「の数」 tail would refuse the one phrasing the rule exists for.
    """

    owner = band_owner(template)
    label = AXIS_LABELS[template][1]
    assert owner
    assert label.startswith(owner)
    if "の" in label:
        assert owner != label


@pytest.mark.parametrize("word", NOT_THE_AXIS)
def test_a_thing_the_axis_is_not_an_amount_of_is_not_the_axis(word):
    assert not names_the_band("adventure", f"さっきのゲームの{word}を増やして")


def test_the_axis_own_word_is_the_axis():
    assert names_the_band("adventure", "さっきのゲームの敵を増やして")
    assert names_the_band("platformer", "さっきのゲームの足場を増やして")
    # ...and each template judges by its own label, not by the adventure's.
    assert not names_the_band("platformer", "さっきのゲームの敵を増やして")


def test_the_object_is_read_off_the_message():
    assert detect_revision_intent("さっきのゲームの宝石を増やして").band_object == "宝石"
    assert detect_revision_intent("さっきのゲームの敵を増やして").band_object == "敵"


def test_naming_the_artifact_is_naming_no_object():
    """「ゲームをもっと増やして」 asks for the axis, not for more games."""

    for message in ("さっきのゲームをもっと増やして", "さっきのやつをもっと増やして",
                    "もっと増やして"):
        intent = detect_revision_intent(message)
        assert intent.adjustments.get("band") == "+1"
        assert intent.band_object == ""
