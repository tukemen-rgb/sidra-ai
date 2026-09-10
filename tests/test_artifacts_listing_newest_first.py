"""C-1641: the artifacts/projects listing must order truly newest-first."""

from __future__ import annotations

from sidra_ai.evals.artifacts_listing_newest_first import (
    evaluate_artifacts_listing_newest_first,
)


def test_listing_is_newest_first():
    result = evaluate_artifacts_listing_newest_first()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
