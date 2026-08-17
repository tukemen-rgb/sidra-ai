"""Incremental pull-request polling must not skip ambiguous revisions."""

from __future__ import annotations

import pytest

from sidra_ai.ingestion.github_client import GitHubAPIError, GitHubReadOnlyClient, Response

REPO = "tukemen-rgb/site"


def _client(settings, rows):
    def transport(method: str, url: str, headers, timeout: float) -> Response:
        assert method == "GET"
        return Response(200, {}, rows)

    return GitHubReadOnlyClient(settings, transport=transport, sleep=lambda _: None)


@pytest.mark.parametrize(
    "updated_at",
    [None, "", "not-a-timestamp", "2026-08-18T00:01:00"],
)
def test_incremental_pull_poll_fails_closed_on_untrustworthy_updated_at(
    settings, updated_at
) -> None:
    """A row that cannot be ordered against the cursor must abort the poll."""

    client = _client(
        settings,
        [
            {"number": 7, "updated_at": updated_at},
            {"number": 6, "updated_at": "2026-08-17T23:59:00Z"},
        ],
    )

    with pytest.raises(GitHubAPIError, match="invalid pull request updated_at"):
        client.list_pull_requests(REPO, since="2026-08-18T00:00:00+00:00")


def test_incremental_pull_poll_compares_equivalent_offsets_as_instants(settings) -> None:
    """The same UTC instant must be a cursor boundary regardless of ISO spelling."""

    client = _client(
        settings,
        [
            {"number": 7, "updated_at": "2026-08-18T00:00:00Z"},
            {"number": 6, "updated_at": "2026-08-17T23:59:00Z"},
        ],
    )

    assert client.list_pull_requests(
        REPO, since="2026-08-18T00:00:00+00:00"
    ) == []


def test_incremental_pull_poll_keeps_only_revisions_newer_than_cursor(settings) -> None:
    client = _client(
        settings,
        [
            {"number": 8, "updated_at": "2026-08-18T00:02:00Z"},
            {"number": 7, "updated_at": "2026-08-18T00:00:00Z"},
        ],
    )

    pulls = client.list_pull_requests(REPO, since="2026-08-18T00:00:00+00:00")

    assert [pull["number"] for pull in pulls] == [8]


def test_incremental_pull_poll_rejects_malformed_cursor_without_request(settings) -> None:
    calls = 0

    def transport(method: str, url: str, headers, timeout: float) -> Response:
        nonlocal calls
        calls += 1
        return Response(200, {}, [])

    client = GitHubReadOnlyClient(settings, transport=transport, sleep=lambda _: None)

    with pytest.raises(GitHubAPIError, match="invalid pull request activity cursor"):
        client.list_pull_requests(REPO, since="not-a-cursor")

    assert calls == 0
