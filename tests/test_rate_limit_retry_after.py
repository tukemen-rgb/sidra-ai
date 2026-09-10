"""C-1639: a 429 rate-limit response must carry a usable Retry-After header."""

from __future__ import annotations

from sidra_ai.evals.rate_limit_429_sets_retry_after import (
    evaluate_rate_limit_429_sets_retry_after,
)


def test_429_sets_retry_after_header():
    result = evaluate_rate_limit_429_sets_retry_after()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
