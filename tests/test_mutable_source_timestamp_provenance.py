"""Mutable GitHub provenance must use an authoritative revision timestamp."""

from __future__ import annotations

from datetime import datetime, timezone

from sidra_ai.ingestion.normalize import issue_document, pull_request_document

REPO = "tukemen-rgb/site"
BASE_SHA = "a" * 40


def _pull_payload(**overrides):
    payload = {
        "number": 42,
        "title": "Mutable PR",
        "body": "Current body",
        "state": "open",
        "updated_at": "2026-08-17T07:00:00Z",
        "created_at": "2026-08-01T00:00:00Z",
        "merged_at": None,
        "html_url": "https://github.com/tukemen-rgb/site/pull/42",
        "user": {"login": "outside-contributor", "type": "User"},
        "head": {"sha": "b" * 40},
    }
    payload.update(overrides)
    return payload


def _issue_payload(**overrides):
    payload = {
        "number": 7,
        "title": "Mutable issue",
        "body": "Current body",
        "state": "open",
        "updated_at": "2026-08-17T07:05:00Z",
        "created_at": "2026-07-01T00:00:00Z",
        "html_url": "https://github.com/tukemen-rgb/site/issues/7",
        "user": {"login": "outside-reporter", "type": "User"},
    }
    payload.update(overrides)
    return payload


def test_pull_request_uses_updated_at_as_revision_timestamp() -> None:
    document = pull_request_document(
        _pull_payload(), repository=REPO, commit_sha=BASE_SHA, license="unknown"
    )

    assert document is not None
    assert document.provenance.timestamp == datetime(
        2026, 8, 17, 7, 0, tzinfo=timezone.utc
    )


def test_pull_request_rejects_missing_or_malformed_updated_at() -> None:
    for updated_at in (None, "", "not-a-timestamp"):
        document = pull_request_document(
            _pull_payload(updated_at=updated_at),
            repository=REPO,
            commit_sha=BASE_SHA,
            license="unknown",
        )
        assert document is None, "created_at must not substitute for PR revision time"


def test_issue_uses_updated_at_as_revision_timestamp() -> None:
    document = issue_document(
        _issue_payload(), repository=REPO, commit_sha=BASE_SHA, license="unknown"
    )

    assert document is not None
    assert document.provenance.timestamp == datetime(
        2026, 8, 17, 7, 5, tzinfo=timezone.utc
    )


def test_issue_rejects_missing_or_malformed_updated_at() -> None:
    for updated_at in (None, "", "not-a-timestamp"):
        document = issue_document(
            _issue_payload(updated_at=updated_at),
            repository=REPO,
            commit_sha=BASE_SHA,
            license="unknown",
        )
        assert document is None, "created_at must not substitute for issue revision time"
