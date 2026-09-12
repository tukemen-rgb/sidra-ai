"""C-1731: the quarantine triage list must disclose when an entry has more findings."""

from __future__ import annotations

from sidra_ai.evals.quarantine_list_discloses_finding_count import (
    evaluate_quarantine_list_discloses_finding_count,
)


def test_quarantine_list_discloses_finding_count():
    result = evaluate_quarantine_list_discloses_finding_count()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
