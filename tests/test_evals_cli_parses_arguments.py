"""C-1672: sidra-evals must parse its arguments like the other CLIs."""

from __future__ import annotations

from sidra_ai.evals.evals_cli_parses_arguments import (
    evaluate_evals_cli_parses_arguments,
)


def test_evals_cli_parses_arguments():
    result = evaluate_evals_cli_parses_arguments()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
