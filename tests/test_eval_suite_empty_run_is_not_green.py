"""C-1754: sidra-evals must not report success when it judged nothing."""

from __future__ import annotations

from sidra_ai.evals.eval_suite_empty_run_is_not_green import (
    evaluate_eval_suite_empty_run_is_not_green,
)


def test_eval_suite_empty_run_is_not_green():
    result = evaluate_eval_suite_empty_run_is_not_green()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
