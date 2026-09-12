"""C-1715: the CLI must name a fetch route for a creation's companion flat artifacts."""

from __future__ import annotations

from sidra_ai.evals.cli_names_companion_fetch_routes import (
    evaluate_cli_names_companion_fetch_routes,
)


def test_cli_names_companion_fetch_routes():
    result = evaluate_cli_names_companion_fetch_routes()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
