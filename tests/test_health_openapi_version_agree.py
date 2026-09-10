"""C-1649: /health and /openapi.json must report one single-sourced version."""

from __future__ import annotations

from sidra_ai.evals.health_openapi_version_agree import (
    evaluate_health_openapi_version_agree,
)


def test_health_openapi_version_agree():
    result = evaluate_health_openapi_version_agree()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
