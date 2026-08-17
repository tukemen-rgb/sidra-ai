"""Offline release gate for repository-rejection response privacy.

Repository identifiers are request-controlled data. This eval exercises the
real FastAPI boundary and proves allowlist failures never reflect rejected
identifiers or credential-shaped content in HTTP responses. No socket, model,
or external service is used.
"""

from __future__ import annotations

from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.config.settings import Settings
from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.ingestion.github_client import RepositoryNotAllowedError

_SYNTHETIC_TOKEN = "ghp_" + ("7" * 36)
_REJECTED_REPOSITORY = f"owner/{_SYNTHETIC_TOKEN}"
_ALLOWED_REPOSITORY = "tukemen-rgb/site"
_SAFE_DETAIL = "repository is not allowlisted"


class _RejectingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.calls = 0

    def chat(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("chat should not run for a rejected repository")

    def retrieve(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("retrieve should not run for a rejected repository")

    def analyze_github(self, repositories, **kwargs):
        self.calls += 1
        raise RepositoryNotAllowedError(
            f"repository {repositories[0]!r} is not on the SIDRA allowlist"
        )


class _LateRejectingService(_RejectingService):
    def retrieve(self, *args, **kwargs):
        self.calls += 1
        raise RepositoryNotAllowedError(
            f"repository {_SYNTHETIC_TOKEN!r} failed a downstream allowlist check"
        )


def _check_private_forbidden(response, *, label: str, failures: list[str]) -> None:
    if response.status_code != 403:
        failures.append(f"{label}: expected HTTP 403, got {response.status_code}")
        return

    try:
        payload = response.json()
    except Exception as exc:  # pragma: no cover - defensive reporting path
        failures.append(f"{label}: response was not valid JSON ({type(exc).__name__})")
        return

    if payload != {"detail": _SAFE_DETAIL}:
        failures.append(f"{label}: rejection detail was not context-free")

    if _SYNTHETIC_TOKEN in response.text or _REJECTED_REPOSITORY in response.text:
        failures.append(f"{label}: rejected repository data leaked into HTTP response")


def _repository_rejection_response_privacy() -> EvalOutcome:
    failures: list[str] = []

    with TemporaryDirectory() as data_dir:
        settings = Settings(
            data_dir=data_dir,
            allowed_repositories=(_ALLOWED_REPOSITORY,),
            rate_limit_per_minute=100,
        )

        service = _RejectingService(settings)
        with TestClient(create_app(service=service, settings=settings)) as client:  # type: ignore[arg-type]
            chat = client.post(
                "/v1/chat",
                json={"message": "hi", "repositories": [_REJECTED_REPOSITORY]},
            )
            retrieve = client.post(
                "/v1/retrieve",
                json={"query": "hi", "repositories": [_REJECTED_REPOSITORY]},
            )
            analyze = client.post(
                "/v1/github/analyze",
                json={"repositories": [_REJECTED_REPOSITORY]},
            )

        _check_private_forbidden(chat, label="chat pre-service rejection", failures=failures)
        _check_private_forbidden(
            retrieve,
            label="retrieve pre-service rejection",
            failures=failures,
        )
        _check_private_forbidden(
            analyze,
            label="github analyze pre-service rejection",
            failures=failures,
        )

        if service.calls != 0:
            failures.append(
                "repository allowlist preflight did not stop all service work "
                f"(calls={service.calls})"
            )

        late_service = _LateRejectingService(settings)
        with TestClient(
            create_app(service=late_service, settings=settings)  # type: ignore[arg-type]
        ) as client:
            late = client.post(
                "/v1/retrieve",
                json={"query": "hi", "repositories": [_ALLOWED_REPOSITORY]},
            )

        _check_private_forbidden(
            late,
            label="global repository exception handler",
            failures=failures,
        )
        if late_service.calls != 1:
            failures.append(
                "global repository exception path was not exercised exactly once "
                f"(calls={late_service.calls})"
            )

    return EvalOutcome(
        case_name="api_repository_rejection_response_privacy",
        passed=not failures,
        detail="repository allowlist failures must return fixed 403 detail without echoing input",
        failures=tuple(failures),
    )


def run_repository_rejection_privacy_suite() -> list[EvalOutcome]:
    """Run repository-rejection HTTP privacy regressions entirely offline."""

    return [_repository_rejection_response_privacy()]
