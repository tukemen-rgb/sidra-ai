"""C-1765: re-screening replayed history must not pollute the quarantine review."""

from __future__ import annotations

from sidra_ai.evals.history_screening_does_not_pollute_quarantine import (
    evaluate_history_screening_does_not_pollute_quarantine,
)


def test_history_screening_does_not_pollute_quarantine():
    result = evaluate_history_screening_does_not_pollute_quarantine()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
