"""C-1742: the sidra-ask CLI must show each citation's source URL."""

from __future__ import annotations

from sidra_ai.evals.cli_names_citation_source_url import (
    evaluate_cli_names_citation_source_url,
)


def test_cli_names_citation_source_url():
    result = evaluate_cli_names_citation_source_url()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
