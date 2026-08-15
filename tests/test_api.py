"""The private API: starts offline, refuses unsafe input, cites its sources."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from sidra_ai.api.app import RateLimiter, create_app
from sidra_ai.api.audit import ApiAuditLog
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings, reset_settings_cache
from sidra_ai.ingestion.state import StateStore

FAKE_TOKEN = "ghp_" + "3" * 36


@pytest.fixture
def service(settings: Settings, store, gate, client, model, tmp_path) -> SidraService:
    return SidraService(
        settings,
        model=model,
        store=store,
        gate=gate,
        client=client,
        state_store=StateStore(tmp_path / "state.json"),
    )


@pytest.fixture
def api(service: SidraService, settings: Settings) -> TestClient:
    return TestClient(create_app(service, settings))


# --- health ------------------------------------------------------------

def test_health_works_with_no_weights_and_no_api_key(api: TestClient) -> None:
    response = api.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "version": "0.1.0",
        "model_available": True,
        "github_write_enabled": False,
    }


def test_health_never_leaks_runtime_topology(
    api: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The open probe must not inventory SIDRA internals for a remote caller."""

    monkeypatch.setenv("SIDRA_API_TOKEN", "leaky-token-value")
    monkeypatch.setenv("SIDRA_GITHUB_TOKEN", "leaky-github-value")
    body = api.get("/health").text

    for forbidden in (
        "leaky-token-value",
        "leaky-github-value",
        settings.model_name,
        "tukemen-rgb",
        "allowed_repositories",
        "api_token_configured",
        "github_token_configured",
        '"config"',
        '"index"',
        '"model"',
        "endpoint",
    ):
        assert forbidden not in body


def test_health_degrades_without_exposing_model_error(
    service: SidraService, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_health():
        raise RuntimeError("private-backend-host.internal:9999 refused secret topology")

    monkeypatch.setattr(service.model, "health", fail_health)
    response = TestClient(create_app(service, settings)).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["model_available"] is False
    assert "private-backend-host" not in response.text
    assert "refused secret topology" not in response.text


def test_app_starts_without_a_paid_api_key(settings: Settings) -> None:
    """The whole app must import and serve on a clean machine."""

    reset_settings_cache()
    with TestClient(create_app(settings=settings)) as bare:
        assert bare.get("/health").status_code == 200


# --- retrieve: citation-only, zero-model path -------------------------

def test_retrieve_returns_provenance_without_invoking_model(
    api: TestClient, service: SidraService, model
) -> None:
    service.analyze_github(["tukemen-rgb/site"])
    calls_before = model.calls

    response = api.post(
        "/v1/retrieve",
        json={"query": "site repository", "repositories": ["tukemen-rgb/site"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is False
    assert body["model_invoked"] is False
    assert body["external_api_cost_usd"] == 0.0
    assert body["results"]
    assert model.calls == calls_before, "retrieval-only route invoked the model"

    for result in body["results"]:
        assert set(result) == {"score", "citation"}
        citation = result["citation"]
        assert citation["repository"] == "tukemen-rgb/site"
        assert citation["commit_sha"]
        assert citation["license"]
        assert "content" not in citation


def test_retrieve_with_no_index_returns_no_evidence_without_model(
    api: TestClient, model
) -> None:
    calls_before = model.calls
    body = api.post("/v1/retrieve", json={"query": "anything"}).json()
    assert body["results"] == []
    assert body["model_invoked"] is False
    assert body["external_api_cost_usd"] == 0.0
    assert "no indexed evidence" in body["reason"]
    assert model.calls == calls_before


def test_retrieve_screens_operator_query(api: TestClient) -> None:
    response = api.post("/v1/retrieve", json={"query": f"find {FAKE_TOKEN}"})
    assert response.status_code == 200
    assert FAKE_TOKEN not in response.text


def test_retrieve_rejects_non_allowlisted_repository(api: TestClient) -> None:
    response = api.post(
        "/v1/retrieve",
        json={"query": "hi", "repositories": ["attacker/evil"]},
    )
    assert response.status_code == 403


# --- chat --------------------------------------------------------------

def test_chat_returns_citations_for_indexed_content(
    api: TestClient, service: SidraService
) -> None:
    service.analyze_github(["tukemen-rgb/site"])
    response = api.post("/v1/chat", json={"message": "What is the site repository?"})
    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is False
    assert body["citations"]
    for citation in body["citations"]:
        assert citation["repository"]
        assert citation["commit_sha"]
        assert citation["license"]


def test_chat_with_no_index_says_so_rather_than_inventing(api: TestClient) -> None:
    body = api.post("/v1/chat", json={"message": "anything"}).json()
    assert body["citations"] == []
    assert "No indexed evidence" in body["answer"]


def test_chat_screens_the_operator_message(api: TestClient) -> None:
    """An operator can paste a secret by accident; it must not be echoed."""

    body = api.post("/v1/chat", json={"message": f"is {FAKE_TOKEN} still valid?"}).json()
    assert FAKE_TOKEN not in str(body)


def test_chat_blocks_oversized_input(api: TestClient) -> None:
    response = api.post("/v1/chat", json={"message": "A" * 40_000})
    # Pydantic rejects it before it reaches the gate.
    assert response.status_code == 422


def test_chat_rejects_a_non_allowlisted_repository(api: TestClient) -> None:
    response = api.post(
        "/v1/chat", json={"message": "hi", "repositories": ["attacker/evil"]}
    )
    assert response.status_code == 403


def test_chat_validates_top_k(api: TestClient) -> None:
    assert api.post("/v1/chat", json={"message": "hi", "top_k": 999}).status_code == 422


# --- analyze -----------------------------------------------------------

def test_analyze_ingests_then_skips_when_unchanged(
    api: TestClient, model
) -> None:
    first = api.post("/v1/github/analyze", json={"repositories": ["tukemen-rgb/site"]})
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["ingestion"]["changed"] is True
    assert first_body["analysis"] is not None
    assert "retrieved" not in first_body["analysis"], (
        "analyze must not export raw retrieved chunks through its nested response"
    )
    calls = model.calls

    second = api.post("/v1/github/analyze", json={"repositories": ["tukemen-rgb/site"]})
    body = second.json()
    assert body["inference_skipped"] is True
    assert body["analysis"] is None
    assert model.calls == calls, "model ran despite no changes"


def test_analyze_rejects_a_non_allowlisted_repository(api: TestClient) -> None:
    body = api.post(
        "/v1/github/analyze", json={"repositories": ["attacker/evil"]}
    ).json()
    reports = body["ingestion"]["repositories"]
    assert reports[0]["skipped_reason"] == "not_allowed"
    assert reports[0]["indexed"] == 0


def test_no_write_routes_exist(api: TestClient) -> None:
    """The API surface itself offers no GitHub mutation."""

    paths = api.get("/openapi.json").json()["paths"]
    assert set(paths) == {
        "/health",
        "/v1/retrieve",
        "/v1/chat",
        "/v1/github/analyze",
    }
    for path, methods in paths.items():
        for method in methods:
            assert method in {"get", "post"}
    for forbidden in ("comment", "merge", "push", "deploy", "write"):
        assert not any(forbidden in path for path in paths)


# --- auth and rate limiting -------------------------------------------

def test_bearer_token_is_required_when_configured(
    service: SidraService, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIDRA_API_TOKEN", "configured-token")
    guarded = TestClient(create_app(service, settings))

    assert guarded.post("/v1/chat", json={"message": "hi"}).status_code == 401
    assert guarded.post(
        "/v1/retrieve", json={"query": "hi"}
    ).status_code == 401
    assert guarded.post(
        "/v1/chat",
        json={"message": "hi"},
        headers={"Authorization": "Bearer wrong"},
    ).status_code == 401
    assert guarded.post(
        "/v1/chat",
        json={"message": "hi"},
        headers={"Authorization": "Bearer configured-token"},
    ).status_code == 200


def test_health_stays_open_but_reveals_nothing_sensitive(
    service: SidraService, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIDRA_API_TOKEN", "configured-token")
    guarded = TestClient(create_app(service, settings))
    body = guarded.get("/health")
    assert body.status_code == 200
    assert set(body.json()) == {
        "status",
        "version",
        "model_available",
        "github_write_enabled",
    }
    assert "configured-token" not in body.text


def test_rate_limit_rejects_a_flood(service: SidraService) -> None:
    limited = TestClient(create_app(service, Settings(rate_limit_per_minute=3)))
    statuses = [
        limited.post("/v1/chat", json={"message": "hi"}).status_code for _ in range(5)
    ]
    assert 429 in statuses
    assert statuses[:3] == [200, 200, 200]


def test_rate_limiter_window_is_per_client() -> None:
    limiter = RateLimiter(per_minute=1)
    assert limiter.check("10.0.0.1") is True
    assert limiter.check("10.0.0.1") is False
    assert limiter.check("10.0.0.2") is True


def test_cors_is_not_enabled(api: TestClient) -> None:
    response = api.get("/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in {
        k.lower() for k in response.headers
    }


# --- secret-safe audit -------------------------------------------------

def test_api_audit_records_metadata_without_query_or_secret(
    service: SidraService, settings: Settings, tmp_path
) -> None:
    path = tmp_path / "audit.jsonl"
    audited = TestClient(create_app(service, settings, audit_log=ApiAuditLog(path)))
    ordinary_query = "private roadmap question"

    assert audited.post("/v1/chat", json={"message": ordinary_query}).status_code == 200
    assert audited.post(
        "/v1/retrieve", json={"query": f"find {FAKE_TOKEN}"}
    ).status_code == 200

    raw = path.read_text(encoding="utf-8")
    assert ordinary_query not in raw
    assert FAKE_TOKEN not in raw
    assert "authorization" not in raw.lower()
    assert path.stat().st_mode & 0o777 == 0o600

    events = [json.loads(line) for line in raw.splitlines()]
    assert [event["operation"] for event in events] == ["chat", "retrieve"]
    assert events[0]["input_chars"] == len(ordinary_query)
    assert events[1]["input_chars"] == len(f"find {FAKE_TOKEN}")
    assert events[1]["model_invoked"] is False


def test_api_audit_keeps_only_citation_repository_provenance(
    service: SidraService, settings: Settings, tmp_path
) -> None:
    service.analyze_github(["tukemen-rgb/site"])
    path = tmp_path / "audit.jsonl"
    audited = TestClient(create_app(service, settings, audit_log=ApiAuditLog(path)))

    response = audited.post(
        "/v1/retrieve",
        json={"query": "site repository", "repositories": ["tukemen-rgb/site"]},
    )
    assert response.status_code == 200

    event = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert event["citation_repositories"] == ["tukemen-rgb/site"]
    assert event["repository_count"] == 1
    assert "content" not in event
    assert "query" not in event
    assert "answer" not in event
