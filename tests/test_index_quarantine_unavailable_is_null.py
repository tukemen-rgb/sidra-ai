"""C-1631: ``GET /v1/index`` must report an unreadable quarantine log's counts as
``null`` (unknown), never ``0`` (which reads as "nothing held back")."""

from __future__ import annotations

from sidra_ai.evals.index_quarantine_unavailable_is_null_not_zero import (
    evaluate_index_quarantine_unavailable_is_null_not_zero,
)


def test_unavailable_quarantine_counts_are_null_not_zero():
    result = evaluate_index_quarantine_unavailable_is_null_not_zero()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
