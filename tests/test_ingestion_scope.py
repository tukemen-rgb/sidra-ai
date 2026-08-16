"""Scope semantics for bulk GitHub ingestion."""

from __future__ import annotations

from sidra_ai.ingestion.pipeline import GitHubIngestionPipeline, RepositoryReport
from sidra_ai.ingestion.state import StateStore


def _pipeline(client, store, gate, tmp_path, settings) -> GitHubIngestionPipeline:
    return GitHubIngestionPipeline(
        client=client,
        store=store,
        state_store=StateStore(tmp_path / "state.json"),
        gate=gate,
        settings=settings,
    )


def test_explicit_empty_repository_scope_is_a_network_free_noop(
    client, store, gate, tmp_path, settings, fake_github
) -> None:
    """An explicit empty scope must never broaden to the configured allowlist."""

    pipeline = _pipeline(client, store, gate, tmp_path, settings)

    report = pipeline.ingest_all([])

    assert report.repositories == []
    assert report.changed is False
    assert report.requires_inference is False
    assert report.total_indexed == 0
    assert fake_github.requests == [], "empty scope unexpectedly contacted GitHub"
    assert store.all_documents() == []


def test_none_repository_scope_still_means_configured_allowlist(
    client, store, gate, tmp_path, settings, monkeypatch
) -> None:
    """Keep the established default-all behavior only for an omitted scope."""

    pipeline = _pipeline(client, store, gate, tmp_path, settings)
    calls: list[tuple[str, bool]] = []

    def record(repository: str, *, force: bool = False) -> RepositoryReport:
        calls.append((repository, force))
        return RepositoryReport(repository=repository, changed=False)

    monkeypatch.setattr(pipeline, "ingest_repository", record)

    report = pipeline.ingest_all(None, force=True)

    assert calls == [(repository, True) for repository in settings.allowed_repositories]
    assert [item.repository for item in report.repositories] == list(
        settings.allowed_repositories
    )
