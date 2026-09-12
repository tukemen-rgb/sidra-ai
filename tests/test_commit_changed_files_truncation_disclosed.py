"""C-1724: an indexed commit must disclose when its changed-file list was cut."""

from __future__ import annotations

from sidra_ai.evals.commit_changed_files_truncation_disclosed import (
    evaluate_commit_changed_files_truncation_disclosed,
)


def test_commit_changed_files_truncation_disclosed():
    result = evaluate_commit_changed_files_truncation_disclosed()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
