"""``GET /v1/index``: what SIDRA knows, without disclosing any of it.

An operator looking at a thin answer needs to separate two causes that look
identical from outside: nothing was ingested, or what was ingested was held
back. This endpoint exists to tell them apart, which means it has to report
counts honestly and content never.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.ingestion.state import StateStore


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


def test_an_empty_index_says_so_per_repository(
    api: TestClient, settings: Settings
) -> None:
    """Every allowlisted repository is listed, including the empty ones.

    An absent row does not say "SIDRA has never ingested this"; it says
    nothing at all, and the difference is the whole point of the endpoint.
    """

    body = api.get("/v1/index").json()

    assert body["documents"] == 0
    assert body["chunks"] == 0
    assert [row["repository"] for row in body["repositories"]] == list(
        settings.allowed_repositories
    )
    for row in body["repositories"]:
        assert row["documents"] == 0
        assert row["last_ingested_at"] == ""
        assert row["has_error"] is False


def test_the_counts_follow_what_was_actually_ingested(api: TestClient) -> None:
    api.post("/v1/github/analyze", json={"repositories": ["tukemen-rgb/site"]})

    body = api.get("/v1/index").json()
    rows = {row["repository"]: row for row in body["repositories"]}
    site = rows["tukemen-rgb/site"]

    assert body["documents"] > 0
    assert body["chunks"] > 0
    assert site["documents"] > 0
    assert site["source_types"], "a repository with documents must break them down"
    assert sum(site["source_types"].values()) == site["documents"]
    assert site["last_ingested_at"], "the freshness cursor is the point of the row"
    assert site["last_commit_sha"]

    # Repositories that were not ingested stay visibly empty rather than
    # inheriting the one that was.
    assert rows["tukemen-rgb/marketing"]["documents"] == 0
    assert rows["tukemen-rgb/marketing"]["last_ingested_at"] == ""

    # The per-repository breakdown must add up to the global one.
    assert sum(row["documents"] for row in body["repositories"]) == body["documents"]
    assert sum(body["source_types"].values()) == body["documents"]


def test_the_index_view_never_carries_document_content(
    api: TestClient, service: SidraService, fake_github
) -> None:
    """Counts cross this boundary. Text, paths, URLs and authors do not.

    Citations are ``/v1/retrieve``'s job, where the caller asked for a
    specific document. Here nobody asked for one, so nothing identifying a
    document may appear - otherwise this becomes a second retrieval path with
    none of the first one's screening.
    """

    api.post("/v1/github/analyze", json={"repositories": ["tukemen-rgb/site"]})
    raw = api.get("/v1/index").text

    documents = service.store.documents()
    assert documents, "this test proves nothing against an empty index"

    for document in documents:
        provenance = document.provenance
        assert provenance.path not in raw
        assert document.content[:80] not in raw
        if provenance.url:
            assert provenance.url not in raw
        if provenance.author:
            assert provenance.author not in raw

    for leaked in ("content", "text", "path", "url", "author", "citation"):
        assert leaked not in raw

    # The body of a fixture document, quoted directly, must not be findable.
    assert fake_github.doc_body.strip() not in raw


def test_an_ingestion_error_is_a_flag_not_a_message(
    api: TestClient, service: SidraService
) -> None:
    """``last_error`` is up to 500 characters of exception text.

    It can quote a GitHub response, so it is reported as a boolean. An
    operator learns that the repository is unhealthy here and reads the
    reason from the logs, rather than the reporting endpoint becoming an
    exception-text channel.
    """

    marker = "pytest-only failure detail " + "x" * 40
    service.state_store.mark_error("tukemen-rgb/site", marker)

    response = api.get("/v1/index")
    body = response.json()
    rows = {row["repository"]: row for row in body["repositories"]}

    assert rows["tukemen-rgb/site"]["has_error"] is True
    assert rows["tukemen-rgb/marketing"]["has_error"] is False
    assert marker not in response.text
    assert "last_error" not in response.text


def test_an_unreadable_quarantine_log_reports_unavailable_not_zero(
    api: TestClient, service: SidraService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zeros would read as "nothing is held back", which is the opposite.

    A reporting surface that cannot reach its source has to say so; quietly
    substituting zeros turns a broken audit log into a clean bill of health.
    """

    def explode() -> dict[str, object]:
        raise OSError("quarantine log unreadable")

    monkeypatch.setattr(
        "sidra_ai.security.quarantine_review.QuarantineReview.stats",
        lambda _self: explode(),
    )

    body = api.get("/v1/index").json()

    assert body["quarantine"]["available"] is False
    assert body["quarantine"]["total"] == 0
    assert body["documents"] == 0, "the rest of the report still works"


def test_the_index_endpoint_is_authenticated(tmp_path, monkeypatch) -> None:
    """Unlike ``/health``, this discloses repository names and counts.

    So it sits behind the same bearer check as retrieval rather than beside
    the open liveness probe.
    """

    monkeypatch.setenv("SIDRA_API_TOKEN", "x" * 40)
    settings = Settings(rate_limit_per_minute=10, data_dir=str(tmp_path))
    api = TestClient(create_app(service=object(), settings=settings))

    unauthenticated = api.get("/v1/index")
    wrong_token = api.get("/v1/index", headers={"Authorization": "Bearer nope"})

    assert unauthenticated.status_code == 401
    assert wrong_token.status_code == 401
    assert "tukemen-rgb" not in unauthenticated.text


def test_health_still_does_not_answer_this_question(api: TestClient) -> None:
    """The open probe stays content-free; adding /v1/index must not widen it."""

    api.post("/v1/github/analyze", json={"repositories": ["tukemen-rgb/site"]})
    health = api.get("/health").text

    assert "tukemen-rgb" not in health
    assert "documents" not in health
    assert "repositories" not in health
