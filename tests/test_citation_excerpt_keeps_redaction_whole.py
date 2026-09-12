"""C-1703: a cited excerpt must not cut a [REDACTED:...] placeholder in half."""

from __future__ import annotations

from sidra_ai.evals.citation_excerpt_keeps_redaction_whole import (
    evaluate_citation_excerpt_keeps_redaction_whole,
)


def test_citation_excerpt_keeps_redaction_whole():
    result = evaluate_citation_excerpt_keeps_redaction_whole()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
