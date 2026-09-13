"""C-1753: the web UI must say when a model answer was cut off at the token cap."""

from __future__ import annotations

from sidra_ai.evals.ui_discloses_answer_truncation import (
    evaluate_ui_discloses_answer_truncation,
)


def test_ui_discloses_answer_truncation():
    result = evaluate_ui_discloses_answer_truncation()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
