"""C-1682: QuarantineReview must not crash on a non-file quarantine/release path."""

from __future__ import annotations

from sidra_ai.evals.quarantine_review_survives_nonfile_paths import (
    evaluate_quarantine_review_survives_nonfile_paths,
)


def test_quarantine_review_survives_nonfile_paths():
    result = evaluate_quarantine_review_survives_nonfile_paths()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
