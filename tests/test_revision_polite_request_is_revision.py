"""C-1463: a polite revision request routes to the reviser (twin of C-1455).

The shared 「ますか」 veto treated 「難しくしてもらえますか」 as a question. A change
stem plus a benefactive is now a request, exempt from the veto unless it is also
an explanation question.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.revise import detect_revision_intent
from sidra_ai.evals.revision_polite_request_is_revision import (
    evaluate_revision_polite_request_is_revision,
)


def test_revision_polite_eval_passes():
    result = evaluate_revision_polite_request_is_revision()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


@pytest.mark.parametrize(
    "message",
    [
        "さっきのゲームをもっと難しくしてもらえますか",
        "前のゲームを簡単にしてもらえますか",
        "さっきのを難しくしていただけますか",
    ],
)
def test_polite_requests_route(message):
    intent = detect_revision_intent(message)
    assert intent.is_revision
    assert intent.adjustments


@pytest.mark.parametrize(
    "message",
    [
        "難しいゲームを作ってください",
        "難易度はどうやって変えるの",
        "難易度の変え方を教えてもらえますか",
    ],
)
def test_non_revisions_stay_out(message):
    assert not detect_revision_intent(message).is_revision
