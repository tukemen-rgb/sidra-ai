"""C-1673: sidra-ask must reject a non-positive --timeout, not crash."""

from __future__ import annotations

from sidra_ai.evals.ask_rejects_nonpositive_timeout import (
    evaluate_ask_rejects_nonpositive_timeout,
)


def test_ask_rejects_nonpositive_timeout():
    result = evaluate_ask_rejects_nonpositive_timeout()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
