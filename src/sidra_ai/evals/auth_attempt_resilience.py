"""Offline release gate for bearer-attempt throttling.

The private API must count missing/malformed/invalid bearer attempts before
credential comparison so authentication floods cannot bypass throttling.  The
eval uses FastAPI's in-memory TestClient only: no socket is opened and no real
credential is used.
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


class _CountingService:
    def __init__(self) -> None:
        self.chat_calls = 0
        self.health_calls = 0

    def chat(self, *_: Any, **__: Any) -> dict[str, Any]:
        self.chat_calls += 1
        return {
            "answer": "unexpected",
            "citations": [],
            "refused": False,
            "reason": "",
            "security": {"decision": "allow", "reasons": [], "findings": []},
            "model": {"backend": "echo", "model": "eval", "input_tokens": 1, "output_tokens": 1, "latency_ms": 0.0, "streamed": False},
        }

    def health(self) -> dict[str, Any]:
        self.health_calls += 1
        return {
            "status": "ok",
            "version": "eval",
            "model_available": True,
            "github_write_enabled": False,
        }


def _invalid_bearer_attempts_are_throttled_pre_auth() -> EvalOutcome:
    failures: list[str] = []
    service = _CountingService()
    synthetic_api_token = "eval-token-" + ("x" * 32)

    with TemporaryDirectory() as data_dir:
        settings = Settings(rate_limit_per_minute=2, data_dir=data_dir)
        with patch.dict(os.environ, {"SIDRA_API_TOKEN": synthetic_api_token}, clear=False):
            app = create_app(service=service, settings=settings)  # type: ignore[arg-type]
            with TestClient(app) as client:
                responses = [
                    client.post("/v1/chat", json={"message": "hi"}),
                    client.post(
                        "/v1/chat",
                        json={"message": "hi"},
                        headers={"Authorization": "Bearer wrong"},
                    ),
                    client.post(
                        "/v1/chat",
                        json={"message": "hi"},
                        headers={"Authorization": "Basic malformed"},
                    ),
                ]

    statuses = [response.status_code for response in responses]
    if statuses != [401, 401, 429]:
        failures.append(f"expected auth-attempt statuses [401, 401, 429], got {statuses!r}")

    if service.chat_calls != 0:
        failures.append(
            "authentication rejection reached the chat service: "
            f"expected 0 calls, got {service.chat_calls}"
        )

    combined_response_text = " ".join(response.text for response in responses)
    if synthetic_api_token in combined_response_text:
        failures.append("authentication/rate-limit response leaked the configured API token")

    return EvalOutcome(
        case_name="api_invalid_bearer_attempts_throttled_before_auth",
        passed=not failures,
        detail="missing and invalid bearer attempts must consume a bounded pre-auth budget",
        failures=tuple(failures),
    )


def _health_budget_remains_independent() -> EvalOutcome:
    failures: list[str] = []
    service = _CountingService()
    synthetic_api_token = "eval-token-" + ("y" * 32)

    with TemporaryDirectory() as data_dir:
        settings = Settings(rate_limit_per_minute=1, data_dir=data_dir)
        with patch.dict(os.environ, {"SIDRA_API_TOKEN": synthetic_api_token}, clear=False):
            app = create_app(service=service, settings=settings)  # type: ignore[arg-type]
            with TestClient(app) as client:
                rejected = client.post(
                    "/v1/chat",
                    json={"message": "hi"},
                    headers={"Authorization": "Bearer wrong"},
                )
                health = client.get("/health")

    if rejected.status_code != 401:
        failures.append(f"expected invalid bearer status 401, got {rejected.status_code}")
    if health.status_code != 200:
        failures.append(f"auth-attempt budget leaked into /health: got {health.status_code}")
    if service.chat_calls != 0:
        failures.append("invalid bearer attempt unexpectedly reached chat service")
    if service.health_calls != 1:
        failures.append(f"expected one health service call, got {service.health_calls}")
    if synthetic_api_token in rejected.text or synthetic_api_token in health.text:
        failures.append("response leaked the configured API token")

    return EvalOutcome(
        case_name="api_auth_attempt_budget_isolated_from_health",
        passed=not failures,
        detail="bearer-attempt throttling must not consume the independent health-probe budget",
        failures=tuple(failures),
    )


def run_auth_attempt_resilience_suite() -> list[EvalOutcome]:
    """Run authentication-throttling regressions without opening a socket."""

    return [
        _invalid_bearer_attempts_are_throttled_pre_auth(),
        _health_budget_remains_independent(),
    ]
