from datetime import datetime, timezone

import pytest

from sidra_ai.ingestion.normalize import issue_document, pull_request_document


@pytest.mark.parametrize(
    ("factory", "payload"),
    [
        (
            pull_request_document,
            {
                "number": 7,
                "title": "Mutable PR",
                "body": "body",
                "state": "open",
                "head": {"sha": "f" * 40},
                "created_at": "2026-08-01T01:02:03Z",
                "updated_at": "not-a-timestamp",
            },
        ),
        (
            issue_document,
            {
                "number": 8,
                "title": "Mutable issue",
                "body": "body",
                "state": "open",
                "created_at": "2026-08-01T01:02:03Z",
                "updated_at": "2026-08-01 01:02:03",
            },
        ),
    ],
)
def test_present_but_untrusted_updated_at_is_not_hidden_by_created_at(factory, payload):
    document = factory(
        payload,
        repository="tukemen-rgb/sidra-ai",
        commit_sha="a" * 40,
        license="Proprietary",
    )

    assert document is None


@pytest.mark.parametrize("factory", [pull_request_document, issue_document])
def test_absent_updated_at_keeps_created_at_compatibility_fallback(factory):
    payload = {
        "number": 9,
        "title": "Mutable source",
        "body": "body",
        "state": "open",
        "created_at": "2026-08-01T01:02:03Z",
    }
    if factory is pull_request_document:
        payload["head"] = {"sha": "b" * 40}

    document = factory(
        payload,
        repository="tukemen-rgb/sidra-ai",
        commit_sha="c" * 40,
        license="Proprietary",
    )

    assert document is not None
    assert document.provenance.timestamp == datetime(
        2026, 8, 1, 1, 2, 3, tzinfo=timezone.utc
    )
