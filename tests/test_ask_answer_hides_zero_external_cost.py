"""C-1668: sidra-ask must not print a zero external-API cost on every answer."""

from __future__ import annotations

from sidra_ai.evals.ask_answer_hides_zero_external_cost import (
    evaluate_ask_answer_hides_zero_external_cost,
)


def test_ask_answer_hides_zero_external_cost():
    result = evaluate_ask_answer_hides_zero_external_cost()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
