"""C-1669: sidra-ask must catch a non-allowlisted --repository before sending."""

from __future__ import annotations

from sidra_ai.evals.ask_rejects_unknown_repository import (
    evaluate_ask_rejects_unknown_repository,
)


def test_ask_rejects_unknown_repository():
    result = evaluate_ask_rejects_unknown_repository()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
