"""Incomplete GitHub collections must not replace the live RAG snapshot."""

from __future__ import annotations

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


def test_partial_fetch_keeps_previous_retrievable_snapshot(
    client, store, gate, tmp_path, settings, fake_github, monkeypatch
) -> None:
    """A successful subset of a failed collection must stay out of live RAG."""

    pipeline = _pipeline(client, store, gate, tmp_path, settings)
    first = pipeline.ingest_repository(REPO)
    assert first.error == ""

    old_readme = next(
        document
        for document in store.by_repository(REPO)
        if document.provenance.path == "README.md"
    )
    old_content = old_readme.content
    assert old_readme.provenance.commit_sha == OLD_SHA

    original_list_issues = client.list_issues
    fake_github.readme_body = "# site\n\nCandidate content from the newer commit.\n"
    fake_github.head_sha = NEW_SHA

    def fail_issues(repository: str, since: str | None = None):
        raise GitHubAPIError("transient issue failure", status=503)

    monkeypatch.setattr(client, "list_issues", fail_issues)
    failed = pipeline.ingest_repository(REPO)
    failed_state = pipeline.state_store.load().get(REPO)

    assert failed.skipped_reason == "partial_fetch"
    assert failed.error
    assert failed.indexed == 0
    assert failed.requires_inference is False
    assert failed_state.last_commit_sha == OLD_SHA

    # The cursor and the retrievable corpus must remain one atomic view. A
    # successful README/commit fetch must not leak the newer SHA into RAG while
    # another required source failed and the cursor still points at OLD_SHA.
    current = store.by_repository(REPO)
    current_readme = next(
        document for document in current if document.provenance.path == "README.md"
    )
    assert current_readme.content == old_content
    assert current_readme.provenance.commit_sha == OLD_SHA
    assert all(document.provenance.commit_sha != NEW_SHA for document in current)

    # Once the missing source recovers, the existing last_error path forces a
    # complete retry and only then may the newer snapshot become retrievable.
    monkeypatch.setattr(client, "list_issues", original_list_issues)
    recovered = pipeline.ingest_repository(REPO)
    recovered_state = pipeline.state_store.load().get(REPO)
    recovered_readme = next(
        document
        for document in store.by_repository(REPO)
        if document.provenance.path == "README.md"
    )

    assert recovered.error == ""
    assert recovered_state.last_commit_sha == NEW_SHA
    assert recovered_readme.provenance.commit_sha == NEW_SHA
    assert "Candidate content" in recovered_readme.content
