"""Fail-closed provenance timestamp regressions for GitHub ingestion."""

from __future__ import annotations

from datetime import timezone

from sidra_ai.ingestion.normalize import (
    commit_document,
    issue_document,
    pull_request_document,
)

REPO = "tukemen-rgb/sidra-ai"
SHA = "a" * 40


def test_commit_falls_back_to_authoritative_committer_timestamp() -> None:
    document = commit_document(
        {
            "sha": SHA,
            "commit": {
                "message": "safe synthetic commit",
                "author": {"name": "tester", "date": "not-a-timestamp"},
                "committer": {"date": "2026-08-16T10:00:00+09:00"},
            },
            "html_url": "https://github.com/tukemen-rgb/sidra-ai/commit/" + SHA,
        },
        repository=REPO,
        license="unknown",
    )

    assert document is not None
    assert document.provenance.timestamp.tzinfo == timezone.utc
    assert document.provenance.timestamp.isoformat() == "2026-08-16T01:00:00+00:00"


def test_commit_without_trustworthy_timestamp_is_not_indexable() -> None:
    document = commit_document(
        {
            "sha": SHA,
            "commit": {
                "message": "safe synthetic commit",
                "author": {"date": "2026-08-16T10:00:00"},
                "committer": {"date": "malformed"},
            },
        },
        repository=REPO,
        license="unknown",
    )

    assert document is None


def test_pull_request_does_not_substitute_created_at_for_invalid_revision_time() -> None:
    document = pull_request_document(
        {
            "number": 123,
            "title": "Synthetic PR",
            "body": "safe body",
            "updated_at": "invalid",
            "created_at": "2026-08-15T23:30:00Z",
            "head": {"sha": SHA},
            "user": {"login": "tester", "type": "User"},
        },
        repository=REPO,
        commit_sha=SHA,
        license="unknown",
    )

    assert document is None


def test_issue_without_authoritative_timestamp_is_not_indexable() -> None:
    document = issue_document(
        {
            "number": 456,
            "title": "Synthetic issue",
            "body": "safe body",
            "updated_at": None,
            "created_at": "2026-08-16T10:00:00",
            "user": {"login": "tester", "type": "User"},
        },
        repository=REPO,
        commit_sha=SHA,
        license="unknown",
    )

    assert document is None
