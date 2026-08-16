"""Shared fixtures.

Every fixture here is offline: no network, no model weights, no API keys.
The fake GitHub transport serves canned payloads so ingestion is fully
deterministic.
"""

from __future__ import annotations

import base64
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

import pytest

from sidra_ai.config.settings import Settings, reset_settings_cache
from sidra_ai.ingestion.github_client import GitHubReadOnlyClient, Response
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

ALLOWED = (
    "tukemen-rgb/site",
    "tukemen-rgb/creater-yard",
    "tukemen-rgb/Fg",
    "tukemen-rgb/marketing",
    "tukemen-rgb/sidra-ai",
)

SHA_A = "a" * 40
SHA_B = "b" * 40


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


class FakeGitHub:
    """Minimal, deterministic stand-in for the GitHub REST API.

    Records every request so tests can assert that an unchanged repository
    triggers only the two metadata calls and nothing else.
    """

    def __init__(self, head_sha: str = SHA_A) -> None:
        self.head_sha = head_sha
        self.requests: list[tuple[str, str]] = []
        self.readme_body = "# site\n\nSIDRA STUDIO marketing site.\n"
        self.doc_body = "# Architecture\n\nLocal-first RAG over GitHub.\n"
        self.commit_message = "feat: add pricing page"
        self.issue_body = "Please add a dark theme to the pricing page."
        self.pr_body = "Adds the pricing page and its tests."

    # ------------------------------------------------------------------
    def __call__(
        self, method: str, url: str, headers: Mapping[str, str], timeout: float
    ) -> Response:
        parsed = urlparse(url)
        path = parsed.path
        self.requests.append((method, path))
        query = parse_qs(parsed.query)
        body = self._route(path, query)
        if body is None:
            return Response(404, {}, {"message": "Not Found"})
        return Response(200, {}, body)

    # ------------------------------------------------------------------
    def _route(self, path: str, query: dict[str, list[str]]) -> Any:
        parts = [p for p in path.split("/") if p]
        # /repos/{owner}/{repo}/...
        if len(parts) < 3 or parts[0] != "repos":
            return None
        repository = f"{parts[1]}/{parts[2]}"
        tail = parts[3:]

        if not tail:
            return {
                "full_name": repository,
                "default_branch": "main",
                "private": False,
                "license": {"spdx_id": "MIT"},
            }

        if tail[0] == "commits" and len(tail) == 2:
            return {"sha": self.head_sha, "commit": {"message": self.commit_message}}

        if tail[0] == "commits":
            return [self._commit(self.head_sha)]

        if tail[0] == "compare":
            return {
                "commits": [self._commit(self.head_sha)],
                "files": [{"filename": "README.md"}, {"filename": "docs/arch.md"}],
            }

        if tail[0] == "readme":
            return {
                "path": "README.md",
                "encoding": "base64",
                "content": _b64(self.readme_body),
                "html_url": f"https://github.com/{repository}/blob/main/README.md",
            }

        if tail[0] == "contents":
            sub = "/".join(tail[1:])
            if sub == "docs":
                return [
                    {"type": "file", "name": "arch.md", "path": "docs/arch.md"},
                ]
            if sub == "docs/arch.md":
                return {
                    "path": "docs/arch.md",
                    "encoding": "base64",
                    "content": _b64(self.doc_body),
                    "html_url": f"https://github.com/{repository}/blob/main/docs/arch.md",
                }
            return None

        if tail[0] == "pulls":
            return [
                {
                    "number": 7,
                    "title": "Add pricing page",
                    "body": self.pr_body,
                    "state": "open",
                    "updated_at": "2026-08-01T00:00:00Z",
                    "created_at": "2026-08-01T00:00:00Z",
                    "merged_at": None,
                    "head": {"sha": self.head_sha},
                    "user": {"login": "contributor", "type": "User"},
                    "html_url": "https://github.com/x/y/pull/7",
                }
            ]

        if tail[0] == "issues":
            return [
                {
                    "number": 12,
                    "title": "Dark theme",
                    "body": self.issue_body,
                    "state": "open",
                    "updated_at": "2026-08-02T00:00:00Z",
                    "created_at": "2026-08-02T00:00:00Z",
                    "user": {"login": "outsider", "type": "User"},
                    "html_url": "https://github.com/x/y/issues/12",
                }
            ]

        return None

    def _commit(self, sha: str) -> dict[str, Any]:
        return {
            "sha": sha,
            "commit": {
                "message": self.commit_message,
                "author": {"name": "dev", "date": "2026-08-01T10:00:00Z"},
            },
            "html_url": f"https://github.com/x/y/commit/{sha}",
            "files": [{"filename": "README.md"}],
        }


class CountingModel(EchoModelAdapter):
    """Echo backend that records how many times it was invoked."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def generate(self, request):  # type: ignore[override]
        self.calls += 1
        return super().generate(request)


# ----------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """No inherited configuration, no inherited secrets, no shared state."""

    for name in (
        "SIDRA_HOST",
        "SIDRA_PORT",
        "SIDRA_ALLOW_PUBLIC_BIND",
        "SIDRA_API_TOKEN",
        "SIDRA_GITHUB_TOKEN",
        "SIDRA_MODEL_BACKEND",
        "SIDRA_MODEL_ENDPOINT",
        "SIDRA_ALLOWED_REPOSITORIES",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SIDRA_DATA_DIR", str(tmp_path / "sidra"))
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        allowed_repositories=ALLOWED,
        data_dir=str(tmp_path / "sidra"),
    )


@pytest.fixture
def gate(tmp_path) -> SecurityGate:
    return SecurityGate(
        GatePolicy(),
        allowed_repositories=ALLOWED,
        quarantine_store=QuarantineStore(tmp_path / "quarantine.jsonl"),
    )


@pytest.fixture
def store(gate: SecurityGate) -> DocumentStore:
    return DocumentStore(gate)


@pytest.fixture
def fake_github() -> FakeGitHub:
    return FakeGitHub()


@pytest.fixture
def client(settings: Settings, fake_github: FakeGitHub) -> GitHubReadOnlyClient:
    return GitHubReadOnlyClient(settings, transport=fake_github, sleep=lambda _: None)


@pytest.fixture
def model() -> CountingModel:
    return CountingModel()
