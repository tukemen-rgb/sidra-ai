"""C-1761: /v1/index must reveal a staged-model-but-running-echo fallback."""

from __future__ import annotations

from sidra_ai.evals.index_surfaces_staged_model_echo import (
    evaluate_index_surfaces_staged_model_echo,
)


def test_index_surfaces_staged_model_echo():
    result = evaluate_index_surfaces_staged_model_echo()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
