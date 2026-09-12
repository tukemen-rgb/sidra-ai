"""C-1721: the web UI must name the Retry-After seconds on a rate limit."""

from __future__ import annotations

from sidra_ai.evals.ui_429_names_retry_after import (
    evaluate_ui_429_names_retry_after,
)


def test_ui_429_names_retry_after():
    result = evaluate_ui_429_names_retry_after()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
