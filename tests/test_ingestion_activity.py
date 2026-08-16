"""Mutable GitHub activity must stay fresh even when repository HEAD is stable."""

from __future__ import annotations

from sidra_ai.ingestion.github_client import GitHubAPIError
from sidra_ai.ingestion.pipeline import GitHubIngestionPipeline
from sidra_ai.ingestion.state import StateStore

REPO = "tukemen-rgb/site"


def _pipeline(client, store, gate, tmp_path, settings) -> GitHubIngestionPipeline:
    return GitHubIngestionPipeline(
        client=client,
        store=store,
        state_store=StateStore(tmp_path / "state.json"),
        gate=gate,
        settings=settings,
    )


def _force_activity_poll_due(pipeline: GitHubIngestionPipeline) -> None:
    state = pipeline.state_store.load()
    record = state.get(REPO)
    # Older than both the local poll interval and the fake issue update after
    # the pipeline's conservative overlap is applied.
    record.last_ingested_at = "2026-08-01T23:59:00+00:00"
    pipeline.state_store.save(state)


def _issue_content(store) -> str:
    for document in store.by_repository(REPO):
        if document.provenance.path == "issue/12":
            return document.content
    raise AssertionError("issue/12 is not retrievable")


def test_issue_body_update_is_ingested_without_a_new_commit(
    client, store, gate, tmp_path, settings, fake_github
) -> None:
    pipeline = _pipeline(client, store, gate, tmp_path, settings)
    first = pipeline.ingest_repository(REPO)
    assert first.changed is True

    original_head = fake_github.head_sha
    fake_github.issue_body = "Updated issue body without any repository commit."
    _force_activity_poll_due(pipeline)
    fake_github.requests.clear()

    report = pipeline.ingest_repository(REPO)
    paths = [path for _, path in fake_github.requests]

    assert fake_github.head_sha == original_head
    assert report.head_sha == report.previous_sha == original_head
    assert report.changed is True
    assert report.skipped_reason == "mutable_source_updated"
    assert report.indexed == 1
    assert report.requires_inference is True
    assert "Updated issue body" in _issue_content(store)

    # HEAD equality must skip commit/doc work but not mutable GitHub sources.
    assert any("/pulls" in path for path in paths)
    assert any("/issues" in path for path in paths)
    assert not any("/compare/" in path for path in paths)
    assert not any(path.endswith("/readme") for path in paths)
    assert not any("/contents/" in path for path in paths)


def test_due_activity_poll_deduplicates_overlap_without_inference(
    client, store, gate, tmp_path, settings, fake_github
) -> None:
    pipeline = _pipeline(client, store, gate, tmp_path, settings)
    pipeline.ingest_repository(REPO)
    _force_activity_poll_due(pipeline)
    fake_github.requests.clear()

    report = pipeline.ingest_repository(REPO)
    paths = [path for _, path in fake_github.requests]

    # The fake issues endpoint intentionally ignores its `since` query, so the
    # old issue comes back inside the overlap window. Material-revision
    # de-duplication must keep that from becoming a false source change.
    assert report.changed is False
    assert report.indexed == 0
    assert report.requires_inference is False
    assert report.skipped_reason == "no_new_commits"
    assert any("/pulls" in path for path in paths)
    assert any("/issues" in path for path in paths)
    assert not any("/compare/" in path for path in paths)


def test_partial_activity_poll_keeps_old_view_until_complete_retry(
    client, store, gate, tmp_path, settings, fake_github, monkeypatch
) -> None:
    pipeline = _pipeline(client, store, gate, tmp_path, settings)
    pipeline.ingest_repository(REPO)
    old_content = _issue_content(store)
    old_state = pipeline.state_store.load().get(REPO).last_ingested_at

    fake_github.issue_body = "Changed while the issues request is temporarily failing."
    _force_activity_poll_due(pipeline)
    due_cursor = pipeline.state_store.load().get(REPO).last_ingested_at
    original_list_issues = client.list_issues

    def fail_issues(repository: str, since: str | None = None):
        raise GitHubAPIError("transient issue failure", status=503)

    monkeypatch.setattr(client, "list_issues", fail_issues)
    failed = pipeline.ingest_repository(REPO)
    failed_state = pipeline.state_store.load().get(REPO)

    assert failed.error
    assert failed.skipped_reason == "partial_fetch"
    assert failed.requires_inference is False
    assert _issue_content(store) == old_content
    assert failed_state.last_ingested_at == due_cursor
    assert failed_state.last_error
    assert failed_state.last_ingested_at != old_state

    monkeypatch.setattr(client, "list_issues", original_list_issues)
    recovered = pipeline.ingest_repository(REPO)
    recovered_state = pipeline.state_store.load().get(REPO)

    assert recovered.error == ""
    assert recovered.changed is True
    assert recovered.requires_inference is True
    assert "Changed while" in _issue_content(store)
    assert recovered_state.last_error == ""
