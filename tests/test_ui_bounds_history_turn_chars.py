"""C-1684: the conversation UI must bound history turn length, like the server."""

from __future__ import annotations

from sidra_ai.evals.ui_bounds_history_turn_chars import (
    evaluate_ui_bounds_history_turn_chars,
)


def test_ui_bounds_history_turn_chars():
    result = evaluate_ui_bounds_history_turn_chars()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
