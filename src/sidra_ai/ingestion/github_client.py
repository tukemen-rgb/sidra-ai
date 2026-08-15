"""Read-only GitHub client.

v0.1 has **no** write capability, and that is enforced structurally rather
than by convention:

* :meth:`GitHubReadOnlyClient._request` refuses any HTTP method other than
  ``GET``. There is no code path that can pass anything else.
* The requested URL must resolve under the configured API base, so a crafted
  path cannot redirect the client to another host.
* The repository must be on the allowlist before a request is issued.

``tests/test_read_only.py`` additionally scans this package's source for
write verbs, so adding one is a test failure, not a review miss.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Protocol
from urllib.parse import urlencode, urljoin, urlparse

from sidra_ai.config.settings import Settings, get_settings

#: The only HTTP method this package may ever issue.
ALLOWED_HTTP_METHODS = frozenset({"GET"})


class WriteOperationForbiddenError(RuntimeError):
    """Raised when anything attempts a non-GET GitHub request."""


class RepositoryNotAllowedError(PermissionError):
    """Raised when a repository is not on the configured allowlist."""


class GitHubAPIError(RuntimeError):
    """Raised for transport failures and non-success responses."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: Any


class Transport(Protocol):
    """Pluggable HTTP transport so tests never touch the network."""

    def __call__(
        self, method: str, url: str, headers: Mapping[str, str], timeout: float
    ) -> Response:  # pragma: no cover - protocol
        ...


class HttpxTransport:
    """Default transport. ``httpx`` is imported lazily."""

    def __call__(
        self, method: str, url: str, headers: Mapping[str, str], timeout: float
    ) -> Response:
        if method not in ALLOWED_HTTP_METHODS:
            raise WriteOperationForbiddenError(
                f"transport refused method {method!r}: SIDRA AI v0.1 is read-only"
            )
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise GitHubAPIError("httpx is required for GitHub ingestion") from exc

        try:
            raw = httpx.get(url, headers=dict(headers), timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            raise GitHubAPIError(f"GitHub request failed: {exc}") from exc

        try:
            body = raw.json()
        except (ValueError, json.JSONDecodeError):
            body = raw.text
        return Response(status=raw.status_code, headers=dict(raw.headers), body=body)


class GitHubReadOnlyClient:
    """Fetches repository content. Cannot write, by construction."""

    def __init__(
        self,
        settings: Settings | None = None,
        transport: Transport | Callable[..., Response] | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or get_settings()
        self.transport = transport or HttpxTransport()
        self._sleep = sleep
        self._api_base = self.settings.github_api_base.rstrip("/") + "/"

    # ------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "sidra-ai/0.1 (read-only)",
        }
        token = self.settings.github_token
        if token:
            # Never logged: this dict is not included in any error message.
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _assert_allowed(self, repository: str) -> None:
        if not self.settings.is_repository_allowed(repository):
            raise RepositoryNotAllowedError(
                f"repository {repository!r} is not on the SIDRA allowlist"
            )

    def _build_url(self, path: str, params: Mapping[str, Any] | None = None) -> str:
        url = urljoin(self._api_base, path.lstrip("/"))
        base_host = urlparse(self._api_base).netloc
        if urlparse(url).netloc != base_host:
            raise GitHubAPIError(
                f"refusing request to {urlparse(url).netloc!r}: outside the "
                f"configured GitHub API base"
            )
        if params:
            filtered = {k: v for k, v in params.items() if v is not None}
            if filtered:
                url = f"{url}?{urlencode(filtered)}"
        return url

    def _request(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        method: str = "GET",
        retries: int = 2,
    ) -> Response:
        if method not in ALLOWED_HTTP_METHODS:
            raise WriteOperationForbiddenError(
                f"method {method!r} is forbidden: SIDRA AI v0.1 GitHub access is "
                "read-only"
            )

        url = self._build_url(path, params)
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = self.transport(
                    method, url, self._headers(), self.settings.github_request_timeout
                )
            except GitHubAPIError as exc:
                last_error = exc
                if attempt < retries:
                    self._sleep(2**attempt)
                    continue
                raise

            if response.status == 200:
                return response
            if response.status == 404:
                raise GitHubAPIError(f"not found: {path}", status=404)
            if response.status in (403, 429):
                # Secondary rate limit. Back off rather than hammering.
                if attempt < retries:
                    self._sleep(2**attempt)
                    continue
                raise GitHubAPIError(
                    f"GitHub rate limited or forbidden for {path}", status=response.status
                )
            raise GitHubAPIError(
                f"unexpected status {response.status} for {path}", status=response.status
            )

        raise GitHubAPIError(f"request to {path} failed: {last_error}")

    def _get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        return self._request(path, params).body

    # --- repository metadata -------------------------------------------
    def get_repository(self, repository: str) -> dict[str, Any]:
        self._assert_allowed(repository)
        return self._get_json(f"repos/{repository}")

    def get_license(self, repository: str) -> str:
        """Return an SPDX id, ``"proprietary"``, or ``"unknown"``.

        Never raises: a missing license must not stop ingestion, it must be
        recorded honestly in provenance.
        """

        try:
            repo = self.get_repository(repository)
        except (GitHubAPIError, RepositoryNotAllowedError):
            return "unknown"
        license_info = (repo or {}).get("license") or {}
        spdx = license_info.get("spdx_id")
        if spdx and spdx not in {"NOASSERTION"}:
            return str(spdx)
        if (repo or {}).get("private"):
            return "proprietary"
        return "unknown"

    def get_head_sha(self, repository: str, branch: str | None = None) -> str:
        """Current HEAD SHA of ``branch`` (default branch when omitted)."""

        self._assert_allowed(repository)
        if branch is None:
            repo = self.get_repository(repository)
            branch = repo.get("default_branch", "main")
        data = self._get_json(f"repos/{repository}/commits/{branch}")
        sha = (data or {}).get("sha")
        if not sha:
            raise GitHubAPIError(f"could not resolve HEAD for {repository}")
        return str(sha)

    # --- content --------------------------------------------------------
    def get_readme(self, repository: str, ref: str | None = None) -> dict[str, Any] | None:
        self._assert_allowed(repository)
        try:
            return self._get_json(f"repos/{repository}/readme", {"ref": ref})
        except GitHubAPIError as exc:
            if exc.status == 404:
                return None
            raise

    def get_contents(
        self, repository: str, path: str, ref: str | None = None
    ) -> Any:
        self._assert_allowed(repository)
        try:
            return self._get_json(f"repos/{repository}/contents/{path}", {"ref": ref})
        except GitHubAPIError as exc:
            if exc.status == 404:
                return None
            raise

    def list_docs_paths(
        self, repository: str, ref: str | None = None, roots: Iterable[str] = ("docs",)
    ) -> list[dict[str, Any]]:
        """Recursively list markdown/text files under ``roots``."""

        self._assert_allowed(repository)
        found: list[dict[str, Any]] = []
        pending = list(roots)
        seen: set[str] = set()

        while pending:
            current = pending.pop(0)
            if current in seen:
                continue
            seen.add(current)
            entries = self.get_contents(repository, current, ref)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if entry.get("type") == "dir":
                    pending.append(entry["path"])
                elif entry.get("type") == "file" and entry.get("name", "").lower().endswith(
                    (".md", ".markdown", ".txt", ".rst")
                ):
                    found.append(entry)
                    if len(found) >= self.settings.max_items_per_source:
                        return found
        return found

    # --- history --------------------------------------------------------
    def compare(self, repository: str, base: str, head: str) -> dict[str, Any]:
        """Diff between two SHAs. This is the differential-ingestion core."""

        self._assert_allowed(repository)
        return self._get_json(f"repos/{repository}/compare/{base}...{head}")

    def list_commits(
        self, repository: str, since_sha: str | None = None, head: str | None = None
    ) -> list[dict[str, Any]]:
        """Commits newer than ``since_sha``, or the most recent page."""

        self._assert_allowed(repository)
        limit = self.settings.max_items_per_source
        if since_sha and head:
            comparison = self.compare(repository, since_sha, head)
            return list(comparison.get("commits", []))[:limit]
        data = self._get_json(
            f"repos/{repository}/commits", {"per_page": min(limit, 100), "sha": head}
        )
        return list(data or [])[:limit]

    def list_pull_requests(self, repository: str, since: str | None = None) -> list[dict[str, Any]]:
        self._assert_allowed(repository)
        data = self._get_json(
            f"repos/{repository}/pulls",
            {
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": min(self.settings.max_items_per_source, 100),
            },
        )
        items = list(data or [])
        if since:
            items = [p for p in items if str(p.get("updated_at", "")) > since]
        return items[: self.settings.max_items_per_source]

    def list_issues(self, repository: str, since: str | None = None) -> list[dict[str, Any]]:
        """Issues only. GitHub returns PRs from this endpoint too; filtered out."""

        self._assert_allowed(repository)
        data = self._get_json(
            f"repos/{repository}/issues",
            {
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "since": since,
                "per_page": min(self.settings.max_items_per_source, 100),
            },
        )
        items = [i for i in (data or []) if "pull_request" not in i]
        return items[: self.settings.max_items_per_source]
