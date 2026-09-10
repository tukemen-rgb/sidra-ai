"""C-1644: analyze's reason must tell a fetch failure from 'no new commits'."""

from __future__ import annotations

from sidra_ai.evals.analyze_reason_distinguishes_fetch_failure import (
    evaluate_analyze_reason_distinguishes_fetch_failure,
)


def test_analyze_reason_distinguishes_fetch_failure():
    result = evaluate_analyze_reason_distinguishes_fetch_failure()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
