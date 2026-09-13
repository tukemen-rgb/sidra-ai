"""C-1750: a model answer cut off at the token cap must be disclosed."""

from __future__ import annotations

from sidra_ai.evals.answer_truncation_is_disclosed import (
    evaluate_answer_truncation_is_disclosed,
)


def test_answer_truncation_is_disclosed():
    result = evaluate_answer_truncation_is_disclosed()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
