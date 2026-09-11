"""C-1664: `sidra-api --check` must surface the staged-model/echo caution."""

from __future__ import annotations

from sidra_ai.evals.startup_check_warns_staged_model_echo import (
    evaluate_startup_check_warns_staged_model_echo,
)


def test_startup_check_warns_staged_model_echo():
    result = evaluate_startup_check_warns_staged_model_echo()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
