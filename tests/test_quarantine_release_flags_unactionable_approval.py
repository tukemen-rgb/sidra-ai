"""C-1663: releasing a document-id-less entry must not look actionable."""

from __future__ import annotations

from sidra_ai.evals.quarantine_release_flags_unactionable_approval import (
    evaluate_quarantine_release_flags_unactionable_approval,
)


def test_quarantine_release_flags_unactionable_approval():
    result = evaluate_quarantine_release_flags_unactionable_approval()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
