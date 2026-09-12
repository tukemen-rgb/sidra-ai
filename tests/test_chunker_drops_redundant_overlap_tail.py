"""C-1693: the chunker must not emit a redundant overlap-tail chunk."""

from __future__ import annotations

from sidra_ai.evals.chunker_drops_redundant_overlap_tail import (
    evaluate_chunker_drops_redundant_overlap_tail,
)


def test_chunker_drops_redundant_overlap_tail():
    result = evaluate_chunker_drops_redundant_overlap_tail()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
