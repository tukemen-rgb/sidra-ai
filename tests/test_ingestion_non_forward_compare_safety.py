"""Non-fast-forward GitHub history must never be promoted as a SHA delta."""

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


def _commit(fake_github, sha: str):
    return fake_github._commit(sha)


@pytest.mark.parametrize("status", ["behind", "diverged", "identical", "unexpected"])
def test_compare_rejects_explicit_non_forward_history(
    client, fake_github, monkeypatch, status
) -> None:
    _install_compare_payload(
        monkeypatch,
        fake_github,
        {
            "status": status,
            "total_commits": 1,
            "commits": [_commit(fake_github, NEW_SHA)],
            "files": [{"filename": "README.md"}],
        },
    )

    with pytest.raises(GitHubAPIError, match="forward-only history window"):
        client.compare(REPO, OLD_SHA, NEW_SHA)


def test_compare_accepts_explicit_forward_history(client, fake_github, monkeypatch) -> None:
    _install_compare_payload(
        monkeypatch,
        fake_github,
        {
            "status": "ahead",
            "total_commits": 1,
            "commits": [_commit(fake_github, NEW_SHA)],
            "files": [{"filename": "README.md"}],
        },
    )

    comparison = client.compare(REPO, OLD_SHA, NEW_SHA)

    assert comparison["status"] == "ahead"


def test_diverged_history_preserves_cursor_and_retrievable_snapshot(
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

    _install_compare_payload(
        monkeypatch,
        fake_github,
        {
            "status": "diverged",
            "total_commits": 1,
            "commits": [_commit(fake_github, NEW_SHA)],
            "files": [{"filename": "README.md"}],
        },
    )
    fake_github.head_sha = NEW_SHA
    fake_github.readme_body = "# rewritten history\n\nThis must not become current evidence.\n"

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
    assert "forward-only history window" in report.error
    assert not report.requires_inference
    assert state.last_commit_sha == OLD_SHA
    assert state.last_error
    assert after == before
    assert all(
        document.provenance.commit_sha != NEW_SHA
        for document in store.by_repository(REPO)
    )
