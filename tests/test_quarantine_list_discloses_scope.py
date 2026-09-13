"""C-1743: `sidra-quarantine list` must disclose that it shows only pending."""

from __future__ import annotations

from sidra_ai.evals.quarantine_list_discloses_scope import (
    evaluate_quarantine_list_discloses_scope,
)


def test_quarantine_list_discloses_scope():
    result = evaluate_quarantine_list_discloses_scope()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
