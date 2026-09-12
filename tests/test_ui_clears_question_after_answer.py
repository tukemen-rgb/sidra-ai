"""C-1700: the conversation UI must clear the question box after a real answer."""

from __future__ import annotations

from sidra_ai.evals.ui_clears_question_after_answer import (
    evaluate_ui_clears_question_after_answer,
)


def test_ui_clears_question_after_answer():
    result = evaluate_ui_clears_question_after_answer()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
