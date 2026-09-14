"""A named artifact plus an unreadable change must not become a corpus search.

C-1814, the mirror of C-1797. 「さっきのゲームの音を消して」 names its artifact and
carries a change verb, but 音 is not among the eight things a revision sets, so
the detector reported not-a-revision and the message fell to 「現時点では十分な
根拠がありません … POST /v1/github/analyze を管理者に依頼してください」. That is
C-1261's mistake, and it is the exact outcome C-1797 was written to prevent for
the case where the change was known and the artifact was not.

The detail that makes it worse: the sibling refusal tells the reader to write
「それ」「さっきの」, and they had. The product's own advice did not work on the
product - so the example the new refusal prints is executed here, not trusted.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.creation.revise import CHANGEABLE, detect_revision_intent  # noqa: E402


@pytest.mark.parametrize(
    "message",
    ["さっきのゲームの音を消して", "それのBGMを変えて", "さっきのゲームの背景を暗くして"],
)
def test_a_named_artifact_with_an_unreadable_change_is_flagged(message: str) -> None:
    intent = detect_revision_intent(message)
    assert intent.wants_change
    assert not intent.is_revision, "an edit must not be invented from an unread change"


@pytest.mark.parametrize("message", ["さっきのゲームを難しくして", "さっきのゲームのタイトルを「星の道」にして"])
def test_a_change_that_is_read_is_still_a_revision(message: str) -> None:
    intent = detect_revision_intent(message)
    assert intent.is_revision and not intent.wants_change


def test_c1797s_side_is_untouched() -> None:
    """A change with no artifact stays the other refusal, not this one."""

    intent = detect_revision_intent("難しくして")
    assert intent.wants_referent and not intent.wants_change


def test_a_message_that_points_at_nothing_is_not_swept_in() -> None:
    """No referent and no readable change is not evidence of a revision.

    Sweeping these in would be a guess rather than a reading, and it is what
    keeps the Q&A path from being swallowed.
    """

    intent = detect_revision_intent("音を消して")
    assert not intent.wants_change and not intent.wants_referent


def test_the_offered_list_comes_from_the_detectors_own_table() -> None:
    """The reply must not repeat a sentence that can drift from the code."""

    keys = [key for key, _label in CHANGEABLE]
    assert keys == ["difficulty", "theme", "band", "accent", "daily", "brief", "title", "revert"]
    assert all(label for _key, label in CHANGEABLE)


def test_the_example_the_refusal_prints_actually_works() -> None:
    """The defect was a refusal whose advice did not work. Run the advice."""

    from sidra_ai.evals.revision_names_what_it_can_change import (
        evaluate_revision_names_what_it_can_change,
    )

    result = evaluate_revision_names_what_it_can_change()
    assert result.passed, result.failures
