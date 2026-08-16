"""Offline release gate for bounded API repository scopes.

This eval exercises the real FastAPI/Pydantic request boundary added by the
API repository-scope hardening. Oversized scope lists or repository strings
must be rejected before service work begins, while the exact configured
boundary must remain usable.
"""

from __future__ import annotations

from tempfile import TemporaryDirectory
from typing import Any

from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.api.schemas import MAX_REPOSITORY_NAME_CHARS, MAX_REPOSITORY_SCOPE_ITEMS
from sidra_ai.config.settings import Settings
from sidra_ai.evals.cases import EvalOutcome


class _CountingScopeService:
    """Minimal service double that records whether request validation was bypassed."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.chat_calls = 0
        self.retrieve_calls = 0
        self.analyze_calls = 0

    def chat(
        self,
        message: str,
        *,
        top_k: int = 5,
        repositories: list[str] | None = None,
    ) -> dict[str, Any]:
        self.chat_calls += 1
        return {
            "answer": "ok",
            "refused": False,
            "reason": "",
            "citations": [],
            "security": {},
            "model": {},
        }

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        repositories: list[str] | None = None,
    ) -> dict[str, Any]:
        self.retrieve_calls += 1
        return {
            "refused": False,
            "reason": "",
            "results": [],
            "security": {},
            "model_invoked": False,
            "external_api_cost_usd": 0.0,
        }

    def analyze_github(
        self,
        repositories: list[str] | None = None,
        *,
        force: bool = False,
        question: str = "",
    ) -> dict[str, Any]:
        self.analyze_calls += 1
        return {
            "ingestion": {},
            "inference_skipped": True,
            "reason": "eval",
            "analysis": None,
        }


def _repository_scope_boundary_is_enforced_before_service_work() -> EvalOutcome:
    failures: list[str] = []
    allowed = [f"eval/repo-{index:02d}" for index in range(MAX_REPOSITORY_SCOPE_ITEMS)]
    oversized = [*allowed, "eval/repo-overflow"]
    overlong = "eval/" + ("r" * MAX_REPOSITORY_NAME_CHARS)

    with TemporaryDirectory() as data_dir:
        settings = Settings(
            data_dir=data_dir,
            rate_limit_per_minute=100,
            allowed_repositories=tuple(allowed),
        )
        service = _CountingScopeService(settings)
        app = create_app(service=service, settings=settings)  # type: ignore[arg-type]

        with TestClient(app) as client:
            oversized_requests = (
                ("chat", client.post("/v1/chat", json={"message": "scope eval", "repositories": oversized})),
                ("retrieve", client.post("/v1/retrieve", json={"query": "scope eval", "repositories": oversized})),
                ("analyze", client.post("/v1/github/analyze", json={"repositories": oversized, "question": "scope eval"})),
            )
            overlong_requests = (
                ("chat", client.post("/v1/chat", json={"message": "scope eval", "repositories": [overlong]})),
                ("retrieve", client.post("/v1/retrieve", json={"query": "scope eval", "repositories": [overlong]})),
                ("analyze", client.post("/v1/github/analyze", json={"repositories": [overlong], "question": "scope eval"})),
            )

            for name, response in (*oversized_requests, *overlong_requests):
                if response.status_code != 422:
                    failures.append(
                        f"{name} oversized repository scope reached HTTP {response.status_code}, expected 422"
                    )

            if (service.chat_calls, service.retrieve_calls, service.analyze_calls) != (0, 0, 0):
                failures.append(
                    "oversized repository scope reached service work before validation: "
                    f"chat={service.chat_calls}, retrieve={service.retrieve_calls}, "
                    f"analyze={service.analyze_calls}"
                )

            boundary_responses = (
                ("chat", client.post("/v1/chat", json={"message": "scope eval", "repositories": allowed})),
                ("retrieve", client.post("/v1/retrieve", json={"query": "scope eval", "repositories": allowed})),
                ("analyze", client.post("/v1/github/analyze", json={"repositories": allowed, "question": "scope eval"})),
            )

    for name, response in boundary_responses:
        if response.status_code != 200:
            failures.append(
                f"{name} rejected the exact {MAX_REPOSITORY_SCOPE_ITEMS}-repository boundary "
                f"with HTTP {response.status_code}"
            )

    if (service.chat_calls, service.retrieve_calls, service.analyze_calls) != (1, 1, 1):
        failures.append(
            "exact repository-scope boundary did not reach each service exactly once: "
            f"chat={service.chat_calls}, retrieve={service.retrieve_calls}, "
            f"analyze={service.analyze_calls}"
        )

    return EvalOutcome(
        case_name="api_repository_scope_request_boundary",
        passed=not failures,
        detail=(
            "repository scope count/name limits must reject before service work "
            "without off-by-one rejection at the configured boundary"
        ),
        failures=tuple(failures),
    )


def run_repository_scope_boundary_suite() -> list[EvalOutcome]:
    """Run repository-scope request-boundary regressions without external I/O."""

    return [_repository_scope_boundary_is_enforced_before_service_work()]
