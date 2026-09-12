"""C-1691: the sidra-ask CLI must show the citation excerpt, like the web UI."""

from __future__ import annotations

from sidra_ai.evals.cli_shows_citation_excerpt import (
    evaluate_cli_shows_citation_excerpt,
)


def test_cli_shows_citation_excerpt():
    result = evaluate_cli_shows_citation_excerpt()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
