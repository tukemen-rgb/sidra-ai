"""C-1767: sidra-ask must name a duplicate --repository, not misdirect to the question."""

from __future__ import annotations

from sidra_ai.evals.cli_names_duplicate_repository import (
    evaluate_cli_names_duplicate_repository,
)


def test_cli_names_duplicate_repository():
    result = evaluate_cli_names_duplicate_repository()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
