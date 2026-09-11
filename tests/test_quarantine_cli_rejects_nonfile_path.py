"""C-1677: sidra-quarantine must reject a non-file --path, not crash."""

from __future__ import annotations

from sidra_ai.evals.quarantine_cli_rejects_nonfile_path import (
    evaluate_quarantine_cli_rejects_nonfile_path,
)


def test_quarantine_cli_rejects_nonfile_path():
    result = evaluate_quarantine_cli_rejects_nonfile_path()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
