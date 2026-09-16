"""An instruction that names a feature is an instruction (C-1878).

The judge runs the real service on both sides of one line: a message that
names a change must be carried out, and a message that asks about the same
feature must still be answered. These tests pin the line itself, so that
neither side can be widened into the other without something going red.
"""

from __future__ import annotations

import tempfile

from sidra_ai.api.service import SidraService, _feature_topics
from sidra_ai.config.settings import Settings
from sidra_ai.creation.revise import CHANGEABLE, detect_revision_intent
from sidra_ai.evals.revision_instruction_is_not_a_question import (
    INSTRUCTIONS,
    QUESTIONS,
    evaluate_revision_instruction_is_not_a_question,
)
from sidra_ai.models.echo import EchoModelAdapter


def _talk():
    service = SidraService(Settings(data_dir=tempfile.mkdtemp()), model=EchoModelAdapter())
    reply = service.chat("レースゲームを作って", history=[])
    history = [
        {"role": "user", "content": "レースゲームを作って"},
        {"role": "assistant", "content": reply.get("answer", "")},
    ]
    return service, history


def test_the_judge_is_green_and_says_which_side_it_looked_at() -> None:
    result = evaluate_revision_instruction_is_not_a_question()
    assert result.failures == ()
    assert result.passed
    assert result.carried_out == len(INSTRUCTIONS) == 6
    assert result.answered == len(QUESTIONS) == 4
    assert result.checks_total == result.checks_passed + len(result.failures)


def test_every_instruction_the_judge_uses_really_carries_a_feature_cue() -> None:
    """Otherwise the judge would be measuring ordinary revisions.

    The whole defect is that these messages LOOK like questions to the branch.
    An instruction with no cue in it proves nothing, and would quietly turn
    this judge into a second copy of ``revision_changes_what_was_named``.
    """

    for message, _field, _writes in INSTRUCTIONS:
        assert _feature_topics(message), message
        assert detect_revision_intent(message).adjustments, message


def test_every_question_the_judge_uses_is_not_read_as_a_change() -> None:
    for message, _word in QUESTIONS:
        assert _feature_topics(message), message
        assert detect_revision_intent(message).adjustments == {}, message


def test_the_daily_flag_the_branch_was_swallowing_is_a_promised_change() -> None:
    """C-1878's sharpest edge: the product closed its own promise.

    ``CHANGEABLE`` is what a refusal reads out when it says what a revision
    can change, and 今日の挑戦 is in it - while every phrasing that asked for
    it came back as a description.
    """

    assert "daily" in dict(CHANGEABLE)
    assert dict(CHANGEABLE)["daily"] == "今日の挑戦"


def test_an_instruction_naming_a_feature_reaches_the_reviser() -> None:
    service, history = _talk()
    reply = service.chat("さっきのゲームの日替わりをオンにして", history=history)
    assert reply.get("refusal") != "artifact_feature_question"
    assert (reply.get("creation") or {}).get("revision") == {"daily": "on"}
    assert "今日の挑戦" in reply.get("answer", "")


def test_a_question_about_the_same_feature_is_still_answered() -> None:
    service, history = _talk()
    reply = service.chat("さっきのゲームの今日の挑戦ってなに", history=history)
    assert reply.get("refusal") == "artifact_feature_question"
    assert "今日の挑戦" in reply.get("answer", "")
    # And not the wall C-1866 was written to remove.
    assert "POST /v1/github/analyze" not in reply.get("answer", "")


def test_a_new_title_made_of_feature_words_is_a_rename() -> None:
    service, history = _talk()
    reply = service.chat(
        "さっきのゲームのタイトルを「共有の記録」にして", history=history
    )
    assert reply.get("refusal") != "artifact_feature_question"
    assert (reply.get("creation") or {}).get("revision") == {"title": "共有の記録"}
