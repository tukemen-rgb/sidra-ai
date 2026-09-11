"""C-1686: a usage-ledger disk write failure must not fail a good local answer."""

from __future__ import annotations

from sidra_ai.evals.usage_ledger_disk_write_is_best_effort import (
    evaluate_usage_ledger_disk_write_is_best_effort,
)


def test_usage_ledger_disk_write_is_best_effort():
    result = evaluate_usage_ledger_disk_write_is_best_effort()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
