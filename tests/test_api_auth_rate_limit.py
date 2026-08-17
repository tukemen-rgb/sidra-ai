"""Authentication attempts must be throttled before bearer-token comparison."""

from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.config.settings import Settings


def test_invalid_bearer_attempts_are_rate_limited_before_auth(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("SIDRA_API_TOKEN", "configured-token")
    settings = Settings(rate_limit_per_minute=2, data_dir=str(tmp_path))
    api = TestClient(create_app(service=object(), settings=settings))
    headers = {"Authorization": "Bearer wrong"}

    statuses = [
        api.post("/v1/chat", json={"message": "hi"}, headers=headers).status_code
        for _ in range(3)
    ]

    assert statuses == [401, 401, 429]


def test_health_uses_separate_limiter_from_bearer_attempts(
    tmp_path, monkeypatch
) -> None:
    class HealthOnlyService:
        def health(self):
            return {
                "status": "ok",
                "version": "0.1.0",
                "model_available": True,
                "github_write_enabled": False,
            }

    monkeypatch.setenv("SIDRA_API_TOKEN", "configured-token")
    settings = Settings(rate_limit_per_minute=1, data_dir=str(tmp_path))
    api = TestClient(create_app(service=HealthOnlyService(), settings=settings))

    assert (
        api.post(
            "/v1/chat",
            json={"message": "hi"},
            headers={"Authorization": "Bearer wrong"},
        ).status_code
        == 401
    )
    assert api.get("/health").status_code == 200
