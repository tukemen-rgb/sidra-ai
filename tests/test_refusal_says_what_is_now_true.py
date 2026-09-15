"""C-1871 (§33 事実 5): a declined change says the artifact is untouched.

The narrow half of this item is the point. Eight refusals were measured and
five did not say what is true now, but only one of the five has anything to
report the state OF - which is why the eval checks the other four stay quiet.
"""

from __future__ import annotations

import pytest

from sidra_ai.evals.refusal_says_what_is_now_true import (
    MUST_NOT_SAY,
    MUST_SAY,
    STATE_SENTENCE,
    evaluate_refusal_says_what_is_now_true,
)


def test_says_what_is_now_true_eval_passes():
    result = evaluate_refusal_says_what_is_now_true()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 14


def test_the_exclusions_are_deliberate_and_reasoned():
    """Three codes are kept OUT, each for its own reason.

    Asserted so that "add it everywhere" is a change somebody has to make on
    purpose, against the reasons in the eval's docstring, rather than a tidy
    generalisation nobody argued for. §33 事実 4: a line met over and over
    goes stale.
    """

    assert set(MUST_NOT_SAY.values()) == {
        "artifact_feature_question",  # a question, not a change request
        "revision_kind",              # names an artifact that does not exist
        "revision_target",            # no target was ever resolved
    }
    assert len(MUST_SAY) == 2


@pytest.mark.parametrize("message", MUST_SAY)
def test_the_sentence_is_one_sentence(message):
    """Short enough to sit inside an answer that already says a lot."""

    assert STATE_SENTENCE.count("。") == 0
    assert len(STATE_SENTENCE) < 20
