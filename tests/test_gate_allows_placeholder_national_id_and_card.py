"""C-1489: the gate lets all-same-digit placeholder My Numbers and cards through.

The C-1487 follow-through for national_id and payment_card. A real My Number or
card never has all-identical digits, so 「000000000000」 / 「0000 0000 0000 0000」
(the latter even passes Luhn) is a placeholder, not PII. Quarantining it held the
whole benign document from the index. Recall-safe: real values (varied digits,
including the 4111... Visa test number) still quarantine.
"""

from __future__ import annotations

import pytest

from sidra_ai.security.decisions import Decision
from sidra_ai.security.gate import SecurityGate
from sidra_ai.evals.gate_allows_placeholder_national_id_and_card import (
    evaluate_gate_allows_placeholder_national_id_and_card,
)

_REPO = "tukemen-rgb/site"


def _decision(content: str) -> Decision:
    return SecurityGate(allowed_repositories=[_REPO]).inspect(
        content, source="github", repository=_REPO
    ).decision


def test_placeholder_number_eval_passes():
    result = evaluate_gate_allows_placeholder_national_id_and_card()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


@pytest.mark.parametrize(
    "content",
    [
        "マイナンバー欄の例: 000000000000",
        "マイナンバーのプレースホルダは 0000-0000-0000 とする",
        "カード番号のプレースホルダは 0000 0000 0000 0000",
        "テストカード 0000-0000-0000-0000 を使う",
    ],
)
def test_all_same_digit_number_is_allowed(content):
    assert _decision(content) == Decision.ALLOW


@pytest.mark.parametrize(
    "content",
    [
        "マイナンバー記入例 1234-5678-9012",
        "カードは 4111 1111 1111 1111 です",
        "連絡先は 03-1234-5678 です",
    ],
)
def test_real_values_still_quarantine(content):
    assert _decision(content) == Decision.QUARANTINE
