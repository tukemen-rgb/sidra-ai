"""Mutable GitHub provenance must reject corrupted revision timestamps."""

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


def test_pull_request_without_updated_at_uses_authoritative_creation_time() -> None:
    document = pull_request_document(
        _pull_payload(updated_at=None),
        repository=REPO,
        commit_sha=BASE_SHA,
        license="unknown",
    )

    assert document is not None
    assert document.provenance.timestamp == datetime(
        2026, 8, 1, 0, 0, tzinfo=timezone.utc
    )


def test_pull_request_rejects_malformed_updated_at_instead_of_hiding_it() -> None:
    document = pull_request_document(
        _pull_payload(updated_at="not-a-timestamp"),
        repository=REPO,
        commit_sha=BASE_SHA,
        license="unknown",
    )

    assert document is None


def test_issue_uses_updated_at_as_revision_timestamp() -> None:
    document = issue_document(
        _issue_payload(), repository=REPO, commit_sha=BASE_SHA, license="unknown"
    )

    assert document is not None
    assert document.provenance.timestamp == datetime(
        2026, 8, 17, 7, 5, tzinfo=timezone.utc
    )


def test_issue_without_updated_at_uses_authoritative_creation_time() -> None:
    document = issue_document(
        _issue_payload(updated_at=None),
        repository=REPO,
        commit_sha=BASE_SHA,
        license="unknown",
    )

    assert document is not None
    assert document.provenance.timestamp == datetime(
        2026, 7, 1, 0, 0, tzinfo=timezone.utc
    )


def test_issue_rejects_malformed_updated_at_instead_of_hiding_it() -> None:
    document = issue_document(
        _issue_payload(updated_at="not-a-timestamp"),
        repository=REPO,
        commit_sha=BASE_SHA,
        license="unknown",
    )

    assert document is None
