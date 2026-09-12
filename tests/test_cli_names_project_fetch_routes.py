"""C-1730: the CLI must name a fetch route for a project creation's files."""

from __future__ import annotations

from sidra_ai.evals.cli_names_project_fetch_routes import (
    evaluate_cli_names_project_fetch_routes,
)


def test_cli_names_project_fetch_routes():
    result = evaluate_cli_names_project_fetch_routes()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
