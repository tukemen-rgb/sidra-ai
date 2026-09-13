"""C-1771: a 200-status model-server error body must become a refusal, not empty."""

from __future__ import annotations

from sidra_ai.evals.model_error_body_is_not_a_silent_empty_answer import (
    evaluate_model_error_body_is_not_a_silent_empty_answer,
)


def test_model_error_body_is_not_a_silent_empty_answer():
    result = evaluate_model_error_body_is_not_a_silent_empty_answer()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
