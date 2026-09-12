"""C-1713: the sidra-ask CLI must give an ambiguous query a real next step."""

from __future__ import annotations

from sidra_ai.evals.cli_ambiguous_refusal_asks_which import (
    evaluate_cli_ambiguous_refusal_asks_which,
)


def test_cli_ambiguous_refusal_asks_which():
    result = evaluate_cli_ambiguous_refusal_asks_which()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
