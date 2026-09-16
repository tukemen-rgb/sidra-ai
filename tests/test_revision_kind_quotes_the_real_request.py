"""C-1876: 「もう一度送ってください」 has to mean *their* request.

Revision is game-only, so 「さっきのレポートを直して」 is answered with advice to
send the creation request again - correct - beside a generic example,
「レポートを作って」. Measured: after 「犬のレポートを作って」, sending that example
produced a second report with no dog in it. The instruction promised 「同じ内容
で」 and the example broke the promise.

Documents and decks write no `.meta.json` (measured: the directory holds the
`.md` and nothing beside it), so the conversation is the only place the real
request exists.
"""

from __future__ import annotations

import pytest

from sidra_ai.api.service import last_creation_request
from sidra_ai.evals.revision_kind_quotes_the_real_request import (
    evaluate_revision_kind_quotes_the_real_request,
)


def _history(*questions: str) -> list[tuple[str, str]]:
    return [(q, "…") for q in questions]


def test_the_request_that_was_sent_is_the_one_quoted() -> None:
    history = _history("犬のレポートを作って")

    assert last_creation_request(history, "レポート") == "犬のレポートを作って"


def test_the_most_recent_matching_request_wins() -> None:
    history = _history("犬のレポートを作って", "猫のレポートを作って")

    assert last_creation_request(history, "レポート") == "猫のレポートを作って"


@pytest.mark.parametrize(
    "history,why",
    [
        ([], "an empty conversation has nothing to quote"),
        (_history("収益化の方針を教えて"), "a question is not a creation request"),
        (_history("猫のスライドを作って"), "a スライド request is not a レポート request"),
        (_history("さっきのレポートを直して"), "a revision request is not a creation request"),
    ],
)
def test_nothing_is_quoted_when_there_is_nothing_to_quote(history, why) -> None:
    assert last_creation_request(history, "レポート") is None, why


def test_a_request_too_long_to_quote_is_not_truncated() -> None:
    """Half a request is not the request.

    Sending a truncated quote produces something else, which is the very
    defect this item is about arriving by another door - so the reply drops
    the example rather than shortening it.
    """

    long_request = "レポートを作って。" + "犬と猫と鳥と魚と馬と牛と羊と鹿と熊と狐について、" * 3

    assert len(long_request) > 60
    assert last_creation_request(_history(long_request), "レポート") is None


def test_the_judge_agrees_and_says_so() -> None:
    result = evaluate_revision_kind_quotes_the_real_request()

    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total == 6
