"""Offline release gate for request-validation response privacy.

FastAPI/Pydantic validation errors can contain request-controlled ``input``
values. SIDRA must not reflect credential-shaped repository identifiers or
other malformed payload values back through HTTP 422 responses, where they can
be copied into downstream access logs. This suite exercises the real FastAPI
boundary without sockets, models, GitHub, or Web fetches.
"""

from __future__ import annotations

from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.config.settings import Settings
from sidra_ai.evals.cases import EvalOutcome

_SAFE_DETAIL = "request validation failed"
_SYNTHETIC_TOKEN = "ghp_" + ("8" * 36)
_DUPLICATE_REPOSITORY = f"owner/{_SYNTHETIC_TOKEN}"
_DUPLICATE_REPOSITORY_CASE_VARIANT = _DUPLICATE_REPOSITORY.upper()


class _NoServiceWork:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.calls = 0

    def chat(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("chat service must not run for invalid request bodies")

    def retrieve(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("retrieve service must not run for invalid request bodies")

    def analyze_github(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("analyze service must not run for invalid request bodies")


def _check_context_free_422(response, *, label: str, failures: list[str]) -> None:
    if response.status_code != 422:
        failures.append(f"{label}: expected HTTP 422, got {response.status_code}")
        return

    try:
        payload = response.json()
    except Exception as exc:  # pragma: no cover - defensive reporting path
        failures.append(f"{label}: response was not valid JSON ({type(exc).__name__})")
        return

    if payload != {"detail": _SAFE_DETAIL}:
        failures.append(f"{label}: validation response was not context-free")

    forbidden = (
        _SYNTHETIC_TOKEN,
        _DUPLICATE_REPOSITORY,
        _DUPLICATE_REPOSITORY_CASE_VARIANT,
    )
    if any(value in response.text for value in forbidden):
        failures.append(f"{label}: request-controlled validation input leaked into response")


def _request_validation_response_privacy() -> EvalOutcome:
    failures: list[str] = []

    with TemporaryDirectory() as data_dir:
        settings = Settings(
            data_dir=data_dir,
            allowed_repositories=("tukemen-rgb/site",),
            rate_limit_per_minute=100,
        )
        service = _NoServiceWork(settings)

        with TestClient(create_app(service=service, settings=settings)) as client:  # type: ignore[arg-type]
            duplicate_scope = [
                _DUPLICATE_REPOSITORY,
                _DUPLICATE_REPOSITORY_CASE_VARIANT,
            ]
            chat = client.post(
                "/v1/chat",
                json={"message": "status", "repositories": duplicate_scope},
            )
            retrieve = client.post(
                "/v1/retrieve",
                json={"query": "status", "repositories": duplicate_scope},
            )
            analyze = client.post(
                "/v1/github/analyze",
                json={"repositories": duplicate_scope},
            )
            scalar = client.post(
                "/v1/chat",
                json={"message": "status", "top_k": _SYNTHETIC_TOKEN},
            )

        _check_context_free_422(chat, label="chat duplicate scope", failures=failures)
        _check_context_free_422(
            retrieve,
            label="retrieve duplicate scope",
            failures=failures,
        )
        _check_context_free_422(
            analyze,
            label="analyze duplicate scope",
            failures=failures,
        )
        _check_context_free_422(
            scalar,
            label="chat malformed scalar",
            failures=failures,
        )

        if service.calls != 0:
            failures.append(
                "request validation did not stop service work before dispatch "
                f"(calls={service.calls})"
            )

    return EvalOutcome(
        case_name="api_request_validation_response_privacy",
        passed=not failures,
        detail="HTTP 422 responses must not reflect request-controlled validation inputs",
        failures=tuple(failures),
    )


def run_request_validation_privacy_suite() -> list[EvalOutcome]:
    """Run request-validation HTTP privacy regressions entirely offline."""

    return [_request_validation_response_privacy()]
