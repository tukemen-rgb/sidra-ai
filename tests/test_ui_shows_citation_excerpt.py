"""C-1689: the web UI must show the citation excerpt it already receives."""

from __future__ import annotations

from sidra_ai.evals.ui_shows_citation_excerpt import (
    evaluate_ui_shows_citation_excerpt,
)


def test_ui_shows_citation_excerpt():
    result = evaluate_ui_shows_citation_excerpt()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
