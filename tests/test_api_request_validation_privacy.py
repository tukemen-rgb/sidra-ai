"""Request-validation errors must not reflect attacker-controlled values."""

from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.config.settings import Settings

_SYNTHETIC_TOKEN = "ghp_" + ("8" * 36)
_REPOSITORY = f"owner/{_SYNTHETIC_TOKEN}"


def test_request_validation_errors_are_context_free(tmp_path) -> None:
    settings = Settings(
        data_dir=str(tmp_path),
        allowed_repositories=("tukemen-rgb/site",),
        rate_limit_per_minute=100,
    )

    with TestClient(create_app(settings=settings)) as client:
        cases = (
            (
                "/v1/chat",
                {"message": "status", "repositories": [_REPOSITORY, _REPOSITORY.upper()]},
            ),
            (
                "/v1/retrieve",
                {"query": "status", "repositories": [_REPOSITORY, _REPOSITORY.upper()]},
            ),
            (
                "/v1/github/analyze",
                {"repositories": [_REPOSITORY, _REPOSITORY.upper()]},
            ),
            (
                "/v1/chat",
                {"message": "status", "top_k": _SYNTHETIC_TOKEN},
            ),
        )

        for path, payload in cases:
            response = client.post(path, json=payload)
            assert response.status_code == 422
            assert response.json() == {"detail": "request validation failed"}
            assert _SYNTHETIC_TOKEN not in response.text
            assert _REPOSITORY not in response.text
