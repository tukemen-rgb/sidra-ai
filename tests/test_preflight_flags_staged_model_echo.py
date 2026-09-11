"""C-1666: local_preflight must surface the staged-model/echo advisory."""

from __future__ import annotations

from sidra_ai.evals.preflight_flags_staged_model_echo import (
    evaluate_preflight_flags_staged_model_echo,
)


def test_preflight_flags_staged_model_echo():
    result = evaluate_preflight_flags_staged_model_echo()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
