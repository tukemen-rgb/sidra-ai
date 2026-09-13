"""C-1748: the per-project file listing must disclose its true count."""

from __future__ import annotations

from sidra_ai.evals.project_file_listing_discloses_total import (
    evaluate_project_file_listing_discloses_total,
)


def test_project_file_listing_discloses_total():
    result = evaluate_project_file_listing_discloses_total()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
