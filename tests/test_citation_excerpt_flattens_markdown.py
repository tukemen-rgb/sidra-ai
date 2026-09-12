"""C-1711: the citation excerpt shown to a reader must flatten Markdown decoration."""

from __future__ import annotations

from sidra_ai.evals.citation_excerpt_flattens_markdown import (
    evaluate_citation_excerpt_flattens_markdown,
)


def test_citation_excerpt_flattens_markdown():
    result = evaluate_citation_excerpt_flattens_markdown()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
