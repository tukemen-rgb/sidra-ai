"""Fail-closed coverage for bounded documentation snapshots."""

from __future__ import annotations

from dataclasses import replace

import pytest

from sidra_ai.ingestion.github_client import GitHubAPIError, GitHubReadOnlyClient
from sidra_ai.ingestion.pipeline import GitHubIngestionPipeline
from sidra_ai.ingestion.state import StateStore

REPO = "tukemen-rgb/site"


def _overflowing_docs_get_contents(client: GitHubReadOnlyClient):
    original = client.get_contents

    def get_contents(repository: str, path: str, ref: str | None = None):
        if path == "docs":
            return [
                {"type": "file", "name": "arch.md", "path": "docs/arch.md"},
                {"type": "file", "name": "extra.md", "path": "docs/extra.md"},
            ]
        return original(repository, path, ref)

    return get_contents


def test_docs_listing_refuses_partial_snapshot_beyond_limit(
    settings, fake_github, monkeypatch
) -> None:
    limited = replace(settings, max_items_per_source=1)
    client = GitHubReadOnlyClient(limited, transport=fake_github, sleep=lambda _: None)
    monkeypatch.setattr(client, "get_contents", _overflowing_docs_get_contents(client))

    with pytest.raises(GitHubAPIError, match="documentation snapshot exceeds"):
        client.list_docs_paths(REPO, ref="a" * 40)


def test_docs_listing_allows_exact_limit_when_tree_is_complete(
    settings, fake_github
) -> None:
    limited = replace(settings, max_items_per_source=1)
    client = GitHubReadOnlyClient(limited, transport=fake_github, sleep=lambda _: None)

    entries = client.list_docs_paths(REPO, ref="a" * 40)

    assert [entry["path"] for entry in entries] == ["docs/arch.md"]


def test_incomplete_docs_snapshot_does_not_advance_sha_or_retire_old_docs(
    settings, client, fake_github, gate, store, tmp_path, monkeypatch
) -> None:
    state_store = StateStore(tmp_path / "state.json")
    baseline = GitHubIngestionPipeline(client, store, state_store, gate, settings)
    first = baseline.ingest_repository(REPO)
    assert first.error == ""
    assert any(
        document.provenance.path == "docs/arch.md"
        for document in store.by_repository(REPO)
    )

    limited = replace(settings, max_items_per_source=1)
    limited_client = GitHubReadOnlyClient(
        limited, transport=fake_github, sleep=lambda _: None
    )
    monkeypatch.setattr(
        limited_client,
        "get_contents",
        _overflowing_docs_get_contents(limited_client),
    )
    pipeline = GitHubIngestionPipeline(
        limited_client, store, state_store, gate, limited
    )

    fake_github.head_sha = "e" * 40
    report = pipeline.ingest_repository(REPO)
    state = state_store.load().get(REPO)

    assert report.skipped_reason == "partial_fetch"
    assert "docs: documentation snapshot exceeds" in report.error
    assert state.last_commit_sha == "a" * 40
    assert state.last_error
    assert any(
        document.provenance.path == "docs/arch.md"
        for document in store.by_repository(REPO)
    ), "an incomplete listing must never be treated as proof of deletion"
