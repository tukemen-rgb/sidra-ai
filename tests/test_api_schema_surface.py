"""Private API metadata must not be exposed by unauthenticated FastAPI docs routes."""

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


def test_generated_schema_and_docs_routes_are_disabled(tmp_path) -> None:
    app = create_app(
        service=_HealthOnlyService(),
        settings=Settings(data_dir=str(tmp_path)),
    )
    api = TestClient(app)

    assert app.openapi_url is None
    assert app.docs_url is None
    assert app.redoc_url is None
    assert api.get("/openapi.json").status_code == 404
    assert api.get("/docs").status_code == 404
    assert api.get("/redoc").status_code == 404


def test_health_remains_available_with_schema_routes_disabled(tmp_path) -> None:
    api = TestClient(
        create_app(
            service=_HealthOnlyService(),
            settings=Settings(data_dir=str(tmp_path)),
        )
    )

    response = api.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
