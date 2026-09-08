"""C-1487: the gate lets an all-same-digit placeholder phone through.

A real telephone number never has all-identical digits, so ``000-0000-0000`` in
a form spec or a design Issue is a placeholder, not PII. Quarantining it held the
whole benign document from the index. The exemption is recall-safe: real numbers
(varied digits) still quarantine.
"""

from __future__ import annotations

import pytest

from sidra_ai.security.decisions import Decision
from sidra_ai.security.gate import SecurityGate
from sidra_ai.evals.gate_allows_placeholder_phone import (
    evaluate_gate_allows_placeholder_phone,
)

_REPO = "tukemen-rgb/site"


def _gate() -> SecurityGate:
    return SecurityGate(allowed_repositories=[_REPO])


def _decision(gate: SecurityGate, content: str) -> Decision:
    return gate.inspect(content, source="github", repository=_REPO).decision


def test_placeholder_phone_eval_passes():
    result = evaluate_gate_allows_placeholder_phone()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


@pytest.mark.parametrize(
    "content",
    [
        "電話欄のプレースホルダは 000-0000-0000 とする。",
        "ダミー番号 00-0000-0000 を記載。",
        "0000000000 はサンプルの電話番号です。",
    ],
)
def test_all_same_digit_placeholder_is_allowed(content):
    assert _decision(_gate(), content) == Decision.ALLOW


@pytest.mark.parametrize(
    "content",
    [
        "連絡先は 03-1234-5678 です。",
        "電話は09012345678までお願いします。",
        "0120-123-456 へどうぞ。",
        "call +81-90-1234-5678 now.",
    ],
)
def test_real_phone_numbers_still_quarantine(content):
    assert _decision(_gate(), content) == Decision.QUARANTINE
