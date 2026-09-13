"""C-1758: the first-run ingestion snapshot must disclose when it hit the item cap."""

from __future__ import annotations

from sidra_ai.evals.ingestion_snapshot_cap_is_disclosed import (
    evaluate_ingestion_snapshot_cap_is_disclosed,
)


def test_ingestion_snapshot_cap_is_disclosed():
    result = evaluate_ingestion_snapshot_cap_is_disclosed()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
