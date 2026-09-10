"""C-1646: /v1/retrieve must return distinct sources in descending score order."""

from __future__ import annotations

from sidra_ai.evals.retrieve_dedupes_sources import evaluate_retrieve_dedupes_sources


def test_retrieve_dedupes_sources():
    result = evaluate_retrieve_dedupes_sources()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
