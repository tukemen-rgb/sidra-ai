"""Incremental issue polling must not skip ambiguous revisions."""

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
def test_incremental_issue_poll_fails_closed_on_untrustworthy_updated_at(
    settings, updated_at
) -> None:
    """A real issue without an orderable revision timestamp must abort the poll."""

    client = _client(
        settings,
        [
            {"number": 7, "updated_at": updated_at},
            {"number": 6, "updated_at": "2026-08-18T00:02:00Z"},
        ],
    )

    with pytest.raises(GitHubAPIError, match="invalid issue updated_at"):
        client.list_issues(REPO, since="2026-08-18T00:00:00+00:00")


def test_incremental_issue_poll_ignores_pr_shaped_rows_before_timestamp_validation(
    settings,
) -> None:
    """The issues endpoint also returns PR rows; they are not issue provenance."""

    client = _client(
        settings,
        [
            {"number": 9, "pull_request": {"url": "ignored"}, "updated_at": None},
            {"number": 8, "updated_at": "2026-08-18T00:02:00Z"},
        ],
    )

    issues = client.list_issues(REPO, since="2026-08-18T00:00:00+00:00")

    assert [issue["number"] for issue in issues] == [8]


def test_incremental_issue_poll_rejects_malformed_cursor_without_request(settings) -> None:
    calls = 0

    def transport(method: str, url: str, headers, timeout: float) -> Response:
        nonlocal calls
        calls += 1
        return Response(200, {}, [])

    client = GitHubReadOnlyClient(settings, transport=transport, sleep=lambda _: None)

    with pytest.raises(GitHubAPIError, match="invalid issue activity cursor"):
        client.list_issues(REPO, since="not-a-cursor")

    assert calls == 0


def test_incremental_issue_poll_keeps_valid_revisions(settings) -> None:
    client = _client(
        settings,
        [
            {"number": 8, "updated_at": "2026-08-18T00:02:00Z"},
            {"number": 7, "updated_at": "2026-08-18T00:01:00+00:00"},
        ],
    )

    issues = client.list_issues(REPO, since="2026-08-18T00:00:00Z")

    assert [issue["number"] for issue in issues] == [8, 7]
