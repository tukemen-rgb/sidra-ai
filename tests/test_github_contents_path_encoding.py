"""GitHub Contents API paths must preserve repository filenames exactly."""

from __future__ import annotations

from typing import Mapping
from urllib.parse import parse_qs, urlparse

import pytest

from sidra_ai.ingestion.github_client import GitHubReadOnlyClient, Response

REPO = "tukemen-rgb/site"
REF = "a" * 40


class RecordingContentsTransport:
    """Record one contents request without touching the network."""

    def __init__(self, repository_path: str) -> None:
        self.repository_path = repository_path
        self.urls: list[str] = []

    def __call__(
        self, method: str, url: str, headers: Mapping[str, str], timeout: float
    ) -> Response:
        self.urls.append(url)
        return Response(
            200,
            {},
            {
                "path": self.repository_path,
                "encoding": "base64",
                "content": "IyBPSwo=",
                "html_url": f"https://github.com/{REPO}/blob/main/{self.repository_path}",
            },
        )


@pytest.mark.parametrize(
    ("repository_path", "encoded_path"),
    (
        ("docs/name #100%.md", "docs/name%20%23100%25.md"),
        ("docs/literal%2Fslash?.md", "docs/literal%252Fslash%3F.md"),
        ("docs/日本語.md", "docs/%E6%97%A5%E6%9C%AC%E8%AA%9E.md"),
    ),
)
def test_get_contents_percent_encodes_repository_path(
    settings, repository_path: str, encoded_path: str
) -> None:
    transport = RecordingContentsTransport(repository_path)
    client = GitHubReadOnlyClient(settings, transport=transport, sleep=lambda _: None)

    payload = client.get_contents(REPO, repository_path, ref=REF)

    assert payload is not None
    assert payload["path"] == repository_path
    assert len(transport.urls) == 1

    parsed = urlparse(transport.urls[0])
    assert parsed.path == f"/repos/{REPO}/contents/{encoded_path}"
    assert parse_qs(parsed.query) == {"ref": [REF]}
    assert parsed.fragment == ""
