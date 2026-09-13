"""C-1769: sidra-ask must say what to do for an unnamed creation request."""

from __future__ import annotations

from sidra_ai.evals.cli_says_what_to_do_for_unnamed import (
    evaluate_cli_says_what_to_do_for_unnamed,
)


def test_cli_says_what_to_do_for_unnamed():
    result = evaluate_cli_says_what_to_do_for_unnamed()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
