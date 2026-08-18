"""Private API metadata must not bypass SIDRA's request boundary."""

from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.config.settings import Settings


class _HealthOnlyService:
    def health(self):
        return {
            "status": "ok",
            "version": "0.1.0",
            "model_available": True,
            "github_write_enabled": False,
        }


def test_interactive_docs_are_disabled_but_local_schema_remains_available(tmp_path) -> None:
    app = create_app(
        service=_HealthOnlyService(),
        settings=Settings(data_dir=str(tmp_path)),
    )
    api = TestClient(app)

    assert app.openapi_url is None
    assert app.docs_url is None
    assert app.redoc_url is None
    assert api.get("/docs").status_code == 404
    assert api.get("/redoc").status_code == 404

    schema = api.get("/openapi.json")
    assert schema.status_code == 200
    assert "/v1/chat" in schema.json()["paths"]


def test_schema_requires_bearer_when_public_bind_is_explicit(
    tmp_path, monkeypatch
) -> None:
    token = "schema-test-token-0123456789"
    monkeypatch.setenv("SIDRA_API_TOKEN", token)
    settings = Settings(
        host="0.0.0.0",
        allow_public_bind=True,
        data_dir=str(tmp_path),
    )
    api = TestClient(create_app(service=_HealthOnlyService(), settings=settings))

    assert api.get("/openapi.json").status_code == 401
    authorized = api.get(
        "/openapi.json",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert authorized.status_code == 200
    assert "/v1/github/analyze" in authorized.json()["paths"]


def test_health_remains_available_with_schema_hardening(tmp_path) -> None:
    api = TestClient(
        create_app(
            service=_HealthOnlyService(),
            settings=Settings(data_dir=str(tmp_path)),
        )
    )

    response = api.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
