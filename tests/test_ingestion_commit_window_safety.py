"""Incremental commit windows must never be silently truncated before cursor advance."""

from __future__ import annotations

import pytest

from sidra_ai.ingestion.github_client import GitHubAPIError
from sidra_ai.ingestion.pipeline import GitHubIngestionPipeline
from sidra_ai.ingestion.state import StateStore

REPO = "tukemen-rgb/site"
OLD_SHA = "a" * 40
NEW_SHA = "e" * 40


def _pipeline(client, store, gate, tmp_path, settings) -> GitHubIngestionPipeline:
    return GitHubIngestionPipeline(
        client=client,
        store=store,
        state_store=StateStore(tmp_path / "state.json"),
        gate=gate,
        settings=settings,
    )


def _install_compare_payload(monkeypatch, fake_github, payload) -> None:
    original_route = fake_github._route

    def route(path, query):
        if f"/repos/{REPO}/compare/" in path:
            return payload
        return original_route(path, query)

    monkeypatch.setattr(fake_github, "_route", route)


def _commit(fake_github, index: int):
    return fake_github._commit(f"{index:040x}")


def test_compare_rejects_incremental_window_larger_than_index_limit(
    client, settings, fake_github, monkeypatch
) -> None:
    count = settings.max_items_per_source + 1
    _install_compare_payload(
        monkeypatch,
        fake_github,
        {
            "total_commits": count,
            "commits": [_commit(fake_github, index) for index in range(1, count + 1)],
            "files": [],
        },
    )

    with pytest.raises(GitHubAPIError, match="incremental commit window exceeds"):
        client.compare(REPO, OLD_SHA, NEW_SHA)


def test_compare_rejects_github_truncated_commit_window(
    client, fake_github, monkeypatch
) -> None:
    _install_compare_payload(
        monkeypatch,
        fake_github,
        {
            "total_commits": 3,
            "commits": [_commit(fake_github, 1), _commit(fake_github, 2)],
            "files": [],
        },
    )

    with pytest.raises(GitHubAPIError, match="omitted commits"):
        client.compare(REPO, OLD_SHA, NEW_SHA)


def test_oversized_incremental_window_preserves_sha_cursor_and_rag_snapshot(
    client, store, gate, tmp_path, settings, fake_github, monkeypatch
) -> None:
    pipeline = _pipeline(client, store, gate, tmp_path, settings)
    initial = pipeline.ingest_repository(REPO)
    assert initial.error == ""
    assert pipeline.state_store.load().get(REPO).last_commit_sha == OLD_SHA

    before = sorted(
        (
            document.provenance.source_type.value,
            document.provenance.path,
            document.provenance.commit_sha,
            document.content,
        )
        for document in store.by_repository(REPO)
    )

    count = settings.max_items_per_source + 1
    _install_compare_payload(
        monkeypatch,
        fake_github,
        {
            "total_commits": count,
            "commits": [_commit(fake_github, index) for index in range(1, count + 1)],
            "files": [{"filename": "README.md"}],
        },
    )
    fake_github.head_sha = NEW_SHA

    report = pipeline.ingest_repository(REPO)
    state = pipeline.state_store.load().get(REPO)
    after = sorted(
        (
            document.provenance.source_type.value,
            document.provenance.path,
            document.provenance.commit_sha,
            document.content,
        )
        for document in store.by_repository(REPO)
    )

    assert report.skipped_reason == "partial_fetch"
    assert "incremental commit window exceeds" in report.error
    assert state.last_commit_sha == OLD_SHA
    assert after == before
