"""Offline regression for the unauthenticated health-probe rate limit.

This eval exercises the real FastAPI dependency boundary with an in-memory
ASGI client. It proves that an unauthenticated caller cannot trigger unlimited
local model health checks, and that the rate-limit rejection occurs before the
service health method is invoked.
"""

from __future__ import annotations

import os
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.config.settings import Settings
from sidra_ai.evals.cases import EvalOutcome


class _CountingHealthService:
    def __init__(self) -> None:
        self.health_calls = 0

    def health(self) -> dict[str, Any]:
        self.health_calls += 1
        return {
            "status": "ok",
            "version": "eval",
            "model_available": True,
            "github_write_enabled": False,
        }


def _health_rate_limit_prevents_probe_amplification() -> EvalOutcome:
    failures: list[str] = []
    service = _CountingHealthService()

    with TemporaryDirectory() as data_dir:
        settings = Settings(rate_limit_per_minute=2, data_dir=data_dir)
        synthetic_api_token = "eval-token-" + ("x" * 32)
        with patch.dict(os.environ, {"SIDRA_API_TOKEN": synthetic_api_token}, clear=False):
            app = create_app(service=service, settings=settings)  # type: ignore[arg-type]
            with TestClient(app) as client:
                responses = [client.get("/health") for _ in range(3)]

    statuses = [response.status_code for response in responses]
    if statuses != [200, 200, 429]:
        failures.append(f"expected health statuses [200, 200, 429], got {statuses!r}")

    if service.health_calls != 2:
        failures.append(
            "rate-limit rejection did not occur before the health service call: "
            f"expected 2 calls, got {service.health_calls}"
        )

    if responses[0].status_code == 401 or responses[1].status_code == 401:
        failures.append("health probe unexpectedly required bearer authentication")

    if synthetic_api_token in " ".join(response.text for response in responses):
        failures.append("health/rate-limit response leaked the configured API token")

    return EvalOutcome(
        case_name="api_health_rate_limit_blocks_probe_amplification",
        passed=not failures,
        detail="health must remain unauthenticated but bounded before model health execution",
        failures=tuple(failures),
    )


def run_health_resilience_suite() -> list[EvalOutcome]:
    """Run health-endpoint availability regressions without opening a socket."""

    return [_health_rate_limit_prevents_probe_amplification()]
