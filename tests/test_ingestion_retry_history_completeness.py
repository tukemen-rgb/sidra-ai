"""Retries must not bypass incremental commit-window completeness checks."""

from __future__ import annotations

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


def _snapshot(store):
    return sorted(
        (
            document.provenance.source_type.value,
            document.provenance.path,
            document.provenance.commit_sha,
            document.content,
        )
        for document in store.by_repository(REPO)
    )


def test_retry_rechecks_oversized_incremental_window_before_advancing_cursor(
    client, store, gate, tmp_path, settings, fake_github, monkeypatch
) -> None:
    pipeline = _pipeline(client, store, gate, tmp_path, settings)
    initial = pipeline.ingest_repository(REPO)
    assert initial.error == ""
    assert pipeline.state_store.load().get(REPO).last_commit_sha == OLD_SHA
    before = _snapshot(store)

    count = settings.max_items_per_source + 1
    payload = {
        "status": "ahead",
        "total_commits": count,
        "commits": [fake_github._commit(f"{index:040x}") for index in range(1, count + 1)],
        "files": [{"filename": "README.md"}],
    }
    original_route = fake_github._route

    def route(path, query):
        if f"/repos/{REPO}/compare/" in path:
            return payload
        return original_route(path, query)

    monkeypatch.setattr(fake_github, "_route", route)
    fake_github.head_sha = NEW_SHA
    fake_github.requests.clear()

    first_failed = pipeline.ingest_repository(REPO)
    first_state = pipeline.state_store.load().get(REPO)
    assert first_failed.skipped_reason == "partial_fetch"
    assert "incremental commit window exceeds" in first_failed.error
    assert first_failed.requires_inference is False
    assert first_state.last_commit_sha == OLD_SHA
    assert _snapshot(store) == before

    second_failed = pipeline.ingest_repository(REPO)
    second_state = pipeline.state_store.load().get(REPO)
    assert second_failed.skipped_reason == "partial_fetch"
    assert "incremental commit window exceeds" in second_failed.error
    assert second_failed.requires_inference is False
    assert second_state.last_commit_sha == OLD_SHA
    assert _snapshot(store) == before
    assert all(document.provenance.commit_sha != NEW_SHA for document in store.by_repository(REPO))

    compare_requests = [
        path for method, path in fake_github.requests if method == "GET" and "/compare/" in path
    ]
    assert len(compare_requests) == 2
