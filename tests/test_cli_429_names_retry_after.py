"""C-1718: the ask CLI must name the Retry-After seconds on a rate limit."""

from __future__ import annotations

from sidra_ai.evals.cli_429_names_retry_after import (
    evaluate_cli_429_names_retry_after,
)


def test_cli_429_names_retry_after():
    result = evaluate_cli_429_names_retry_after()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
