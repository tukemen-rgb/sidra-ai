"""C-1688: the chunker must not split a code fence at its `#` comment lines."""

from __future__ import annotations

from sidra_ai.evals.chunker_ignores_headings_in_code_fences import (
    evaluate_chunker_ignores_headings_in_code_fences,
)


def test_chunker_ignores_headings_in_code_fences():
    result = evaluate_chunker_ignores_headings_in_code_fences()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
