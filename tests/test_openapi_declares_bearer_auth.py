"""C-1642: the published OpenAPI schema must declare the bearer auth it enforces."""

from __future__ import annotations

from sidra_ai.evals.openapi_declares_bearer_auth import (
    evaluate_openapi_declares_bearer_auth,
)


def test_openapi_declares_bearer_auth():
    result = evaluate_openapi_declares_bearer_auth()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
