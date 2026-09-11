"""C-1661: sidra-ask must name --top-k's range instead of misdirecting."""

from __future__ import annotations

from sidra_ai.evals.cli_top_k_out_of_range_is_named import (
    evaluate_cli_top_k_out_of_range_is_named,
)


def test_cli_top_k_out_of_range_is_named():
    result = evaluate_cli_top_k_out_of_range_is_named()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
