"""C-1735: the web UI must link each citation to the source it cites."""

from __future__ import annotations

from sidra_ai.evals.ui_citation_links_to_source import (
    evaluate_ui_citation_links_to_source,
)


def test_ui_citation_links_to_source():
    result = evaluate_ui_citation_links_to_source()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
