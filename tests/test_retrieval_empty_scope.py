"""Fail-closed retrieval semantics for explicitly empty scopes."""

from __future__ import annotations

from sidra_ai.api.service import SidraService
from sidra_ai.ingestion.pipeline import GitHubIngestionPipeline
from sidra_ai.ingestion.state import StateStore
from sidra_ai.retrieval.search import BM25Retriever

REPO = "tukemen-rgb/site"


def _populate(client, store, gate, settings, tmp_path) -> None:
    pipeline = GitHubIngestionPipeline(
        client=client,
        store=store,
        state_store=StateStore(tmp_path / "state.json"),
        gate=gate,
        settings=settings,
    )
    report = pipeline.ingest_repository(REPO)
    assert report.indexed > 0


def test_explicit_empty_repository_scope_never_broadens_to_all(
    client, store, gate, settings, tmp_path
) -> None:
    _populate(client, store, gate, settings, tmp_path)
    retriever = BM25Retriever(store)

    assert retriever.search("SIDRA", repositories=None)
    assert retriever.search("SIDRA", repositories=[]) == []


def test_explicit_empty_source_type_scope_returns_nothing(
    client, store, gate, settings, tmp_path
) -> None:
    _populate(client, store, gate, settings, tmp_path)
    retriever = BM25Retriever(store)

    assert retriever.search("SIDRA", source_types=[]) == []


def test_retrieve_api_preserves_explicit_empty_repository_scope(
    client, store, gate, settings, tmp_path, model
) -> None:
    _populate(client, store, gate, settings, tmp_path)
    service = SidraService(
        settings,
        model=model,
        store=store,
        gate=gate,
        client=client,
        state_store=StateStore(tmp_path / "service-state.json"),
    )

    response = service.retrieve("SIDRA", repositories=[])

    assert response["refused"] is False
    assert response["results"] == []
    assert response["model_invoked"] is False
    assert response["external_api_cost_usd"] == 0.0
