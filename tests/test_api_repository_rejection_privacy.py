"""Repository allowlist failures must not echo attacker-controlled identifiers."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.config.settings import Settings
from sidra_ai.ingestion.github_client import RepositoryNotAllowedError

_SYNTHETIC_TOKEN = "ghp_" + "7" * 36
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


def _client(settings: Settings, service) -> TestClient:
    return TestClient(create_app(service=service, settings=settings))


def _assert_private_forbidden(response) -> None:
    assert response.status_code == 403
    assert response.json() == {"detail": _SAFE_DETAIL}
    assert _SYNTHETIC_TOKEN not in response.text
    assert _REJECTED_REPOSITORY not in response.text


def test_chat_and_retrieve_do_not_echo_rejected_repository(settings: Settings) -> None:
    service = _RejectingService(settings)
    client = _client(settings, service)

    chat = client.post(
        "/v1/chat",
        json={"message": "hi", "repositories": [_REJECTED_REPOSITORY]},
    )
    retrieve = client.post(
        "/v1/retrieve",
        json={"query": "hi", "repositories": [_REJECTED_REPOSITORY]},
    )

    _assert_private_forbidden(chat)
    _assert_private_forbidden(retrieve)
    assert service.calls == 0


def test_github_analyze_rejects_repository_before_service_work(settings: Settings) -> None:
    service = _RejectingService(settings)
    response = _client(settings, service).post(
        "/v1/github/analyze",
        json={"repositories": [_REJECTED_REPOSITORY]},
    )

    _assert_private_forbidden(response)
    assert service.calls == 0


def test_github_analyze_rejects_mixed_scope_before_any_service_work(
    settings: Settings,
) -> None:
    service = _RejectingService(settings)
    response = _client(settings, service).post(
        "/v1/github/analyze",
        json={"repositories": [_ALLOWED_REPOSITORY, _REJECTED_REPOSITORY]},
    )

    _assert_private_forbidden(response)
    assert service.calls == 0


def test_global_repository_exception_handler_is_context_free(settings: Settings) -> None:
    service = _LateRejectingService(settings)
    response = _client(settings, service).post(
        "/v1/retrieve",
        json={"query": "hi", "repositories": [_ALLOWED_REPOSITORY]},
    )

    _assert_private_forbidden(response)
    assert service.calls == 1
