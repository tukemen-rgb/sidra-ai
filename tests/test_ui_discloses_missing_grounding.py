"""C-1762: the web UI must say when an answer has no indexed grounding."""

from __future__ import annotations

from sidra_ai.evals.ui_discloses_missing_grounding import (
    evaluate_ui_discloses_missing_grounding,
)


def test_ui_discloses_missing_grounding():
    result = evaluate_ui_discloses_missing_grounding()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
