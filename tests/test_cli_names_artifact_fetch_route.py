"""C-1705: the CLI must name a retrieval route for a generated artifact."""

from __future__ import annotations

from sidra_ai.evals.cli_names_artifact_fetch_route import (
    evaluate_cli_names_artifact_fetch_route,
)


def test_cli_names_artifact_fetch_route():
    result = evaluate_cli_names_artifact_fetch_route()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
