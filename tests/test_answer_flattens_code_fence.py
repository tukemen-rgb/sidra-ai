"""C-1695: answer/evidence flattening must strip code fences, not leave marks."""

from __future__ import annotations

from sidra_ai.evals.answer_flattens_code_fence import (
    evaluate_answer_flattens_code_fence,
)


def test_answer_flattens_code_fence():
    result = evaluate_answer_flattens_code_fence()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
