"""C-1680: the artifact/project listing must report the true total when capped."""

from __future__ import annotations

from sidra_ai.evals.artifact_listing_reports_true_total import (
    evaluate_artifact_listing_reports_true_total,
)


def test_artifact_listing_reports_true_total():
    result = evaluate_artifact_listing_reports_true_total()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
