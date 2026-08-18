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
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Iterator, Mapping, Protocol
from urllib.parse import quote, urlencode, urljoin, urlparse

from sidra_ai.config.settings import Settings, get_settings

#: The only HTTP method this package may ever issue.
ALLOWED_HTTP_METHODS = frozenset({"GET"})

#: Bound pagination so a malformed/malicious Link chain cannot consume an
#: unbounded number of GitHub requests. Exhausting this budget is treated as
#: an incomplete fetch, never as a complete source snapshot.
MAX_PAGINATION_PAGES = 50

#: Bound process-local conditional representations so a long-running poller
#: cannot accumulate one cached body for every historical ref/compare URL.
MAX_ETAG_CACHE_ENTRIES = 256


def _parse_activity_timestamp(value: Any, *, field: str) -> datetime:
    """Parse a mutable-source cursor timestamp without leaking raw values.

    Pull-request pagination is ordered by ``updated_at``. During an incremental
    poll, a missing or malformed timestamp means the client cannot prove where
    that row sits relative to the cursor. Treat that as an incomplete fetch so
    the pipeline preserves its previous cursor/snapshot instead of silently
    skipping a potentially newer revision.
    """

    if not isinstance(value, str) or not value.strip():
        raise GitHubAPIError(f"GitHub returned an invalid {field}")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise GitHubAPIError(f"GitHub returned an invalid {field}") from exc
    if parsed.tzinfo is None:
        raise GitHubAPIError(f"GitHub returned an invalid {field}")
    return parsed.astimezone(timezone.utc)


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


@dataclass(frozen=True)
class _CachedRepresentation:
    """In-memory representation used for safe conditional GET reuse.

    The cache is deliberately process-local: GitHub payloads, issue text, and
    PR bodies are never persisted here. A cached response is reused only for
    the exact same request URL after GitHub confirms ``304 Not Modified``.
    """

    etag: str
    headers: Mapping[str, str]
    body: Any


class Transport(Protocol):
    """Pluggable HTTP transport so tests never touch the network."""

    def __call__(
        self, method: str, url: str, headers: Mapping[str, str], timeout: float
    ) -> Response:  # pragma: no cover - protocol
        ...


class HttpxTransport:
    """Default transport with ambient proxy/environment routing disabled."""

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
            # GitHub bearer credentials must never depend on workstation-level
            # HTTP(S)_PROXY/ALL_PROXY/NO_PROXY or other HTTPX environment routing.
            # The API origin is already pinned by Settings; disable ambient
            # transport configuration so authenticated ingestion reaches it
            # directly instead of leaking through an operator/malware proxy.
            with httpx.Client(trust_env=False) as client:
                raw = client.get(url, headers=dict(headers), timeout=timeout)
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
        self._etag_cache: dict[str, _CachedRepresentation] = {}

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
        base = urlparse(self._api_base)
        parsed = urlparse(url)
        if parsed.scheme != base.scheme or parsed.netloc != base.netloc:
            raise GitHubAPIError(
                f"refusing request to {parsed.netloc!r}: outside the configured "
                "GitHub API base"
            )
        if params:
            filtered = {k: v for k, v in params.items() if v is not None}
            if filtered:
                url = f"{url}?{urlencode(filtered)}"
        return url

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> str:
        """Return a response header case-insensitively."""

        target = name.lower()
        for key, value in headers.items():
            if str(key).lower() == target:
                return str(value)
        return ""

    def _remember_representation(self, url: str, response: Response) -> None:
        """Keep one bounded process-local ETag representation for ``url``."""

        etag = self._header(response.headers, "etag")
        if not etag:
            self._etag_cache.pop(url, None)
            return

        # Refresh insertion order for an existing URL so frequently-polled
        # metadata survives ahead of one-off historical ref/compare entries.
        self._etag_cache.pop(url, None)
        self._etag_cache[url] = _CachedRepresentation(
            etag=etag,
            headers=dict(response.headers),
            body=response.body,
        )
        while len(self._etag_cache) > MAX_ETAG_CACHE_ENTRIES:
            oldest_url = next(iter(self._etag_cache))
            self._etag_cache.pop(oldest_url, None)

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
            request_headers = self._headers()
            cached = self._etag_cache.get(url)
            if cached is not None:
                request_headers["If-None-Match"] = cached.etag

            try:
                response = self.transport(
                    method, url, request_headers, self.settings.github_request_timeout
                )
            except GitHubAPIError as exc:
                last_error = exc
                if attempt < retries:
                    self._sleep(2**attempt)
                    continue
                raise

            if response.status == 200:
                self._remember_representation(url, response)
                return response
            if response.status == 304:
                cached = self._etag_cache.get(url)
                if cached is None:
                    raise GitHubAPIError(
                        f"received 304 without cached representation for {path}",
                        status=304,
                    )
                merged_headers = dict(cached.headers)
                merged_headers.update(response.headers)
                cached_response = Response(
                    status=200,
                    headers=merged_headers,
                    body=cached.body,
                )
                etag = self._header(merged_headers, "etag") or cached.etag
                self._remember_representation(
                    url,
                    Response(
                        status=200,
                        headers={**merged_headers, "ETag": etag},
                        body=cached.body,
                    ),
                )
                return cached_response
            if response.status == 404:
                self._etag_cache.pop(url, None)
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

    @classmethod
    def _next_link(cls, headers: Mapping[str, str]) -> str | None:
        """Extract GitHub's RFC-style ``rel=\"next\"`` Link target."""

        link = cls._header(headers, "link")
        if not link:
            return None
        for part in link.split(","):
            section = part.strip()
            if 'rel="next"' not in section:
                continue
            if not section.startswith("<") or ">" not in section:
                raise GitHubAPIError("malformed GitHub pagination Link header")
            return section[1 : section.index(">")]
        return None

    def _iter_list_pages(
        self, path: str, params: Mapping[str, Any] | None = None
    ) -> Iterator[list[dict[str, Any]]]:
        """Yield bounded list pages by following GitHub ``Link`` headers.

        Each next URL still passes through :meth:`_build_url`, so pagination
        cannot redirect this read-only client to another host or downgrade the
        configured API scheme. A repeated URL or excessive page chain fails
        closed so the ingestion pipeline can keep its prior SHA cursor.
        """

        target = path
        target_params = params
        seen: set[str] = set()

        for _ in range(MAX_PAGINATION_PAGES):
            current_url = self._build_url(target, target_params)
            if current_url in seen:
                raise GitHubAPIError("GitHub pagination loop detected")
            seen.add(current_url)

            response = self._request(target, target_params)
            if not isinstance(response.body, list):
                raise GitHubAPIError(f"expected list response for {path}")
            yield [item for item in response.body if isinstance(item, dict)]

            next_url = self._next_link(response.headers)
            if not next_url:
                return
            target = next_url
            target_params = None

        raise GitHubAPIError(
            f"GitHub pagination exceeded {MAX_PAGINATION_PAGES} pages for {path}"
        )

    # --- repository metadata -------------------------------------------
    def get_repository(self, repository: str) -> dict[str, Any]:
        self._assert_allowed(repository)
        return self._get_json(f"repos/{repository}")

    def get_license(self, repository: str) -> str:
        """Return an SPDX id, ``\"proprietary\"``, or ``\"unknown\"``.

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
        # GitHub Contents API repository paths are data, not URL syntax. Encode
        # every reserved byte while preserving path separators so valid names
        # containing spaces, '#', '?', '%', or Unicode cannot be truncated or
        # reinterpreted as a query/fragment during read-only ingestion.
        encoded_path = quote(path, safe="/")
        try:
            return self._get_json(
                f"repos/{repository}/contents/{encoded_path}", {"ref": ref}
            )
        except GitHubAPIError as exc:
            if exc.status == 404:
                return None
            raise

    def list_docs_paths(
        self, repository: str, ref: str | None = None, roots: Iterable[str] = ("docs",)
    ) -> list[dict[str, Any]]:
        """Recursively list a complete bounded documentation snapshot.

        ``max_items_per_source`` limits how many documentation files v0.1 may
        ingest. Reaching that bound is not, by itself, proof that the GitHub
        snapshot is complete. We therefore continue walking until either the
        tree ends (exactly-at-limit is safe) or one additional eligible file is
        observed. The latter fails closed instead of returning a partial list
        that the pipeline could mistake for proof that older paths were deleted.
        """

        self._assert_allowed(repository)
        found: list[dict[str, Any]] = []
        pending = list(roots)
        seen: set[str] = set()
        limit = self.settings.max_items_per_source

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
                    if len(found) > limit:
                        raise GitHubAPIError(
                            "documentation snapshot exceeds configured item limit; "
                            "refusing to treat a partial listing as complete"
                        )
        return found

    # --- history --------------------------------------------------------
    def compare(self, repository: str, base: str, head: str) -> dict[str, Any]:
        """Diff between two SHAs. This is the differential-ingestion core.

        The pipeline advances its stored SHA only after a complete collection.
        A compare response that contains more commit revisions than
        ``max_items_per_source`` cannot be fully represented by the current
        bounded commit-document pass, and GitHub can also truncate the compare
        commit list. Reject either case here instead of letting the caller
        silently slice the commit window and advance past unseen provenance.
        """

        self._assert_allowed(repository)
        comparison = self._get_json(f"repos/{repository}/compare/{base}...{head}")
        if not isinstance(comparison, dict):
            raise GitHubAPIError("GitHub compare returned a non-object response")

        # SHA-delta ingestion is safe only when GitHub explicitly proves that
        # ``head`` descends from ``base``. Missing/malformed status is not a
        # compatibility case: without that proof, a force-push or divergent
        # history could pair a new cursor with orphaned old RAG evidence.
        status = comparison.get("status")
        if not isinstance(status, str) or status.strip().lower() != "ahead":
            raise GitHubAPIError(
                "GitHub compare did not prove a forward-only history window; "
                "refusing to advance the SHA cursor"
            )

        raw_commits = comparison.get("commits") or []
        if not isinstance(raw_commits, list):
            raise GitHubAPIError("GitHub compare returned a malformed commit list")

        raw_total = comparison.get("total_commits")
        if raw_total is None:
            total_commits = len(raw_commits)
        else:
            try:
                total_commits = int(raw_total)
            except (TypeError, ValueError) as exc:
                raise GitHubAPIError("GitHub compare returned an invalid total_commits") from exc
            if total_commits < 0:
                raise GitHubAPIError("GitHub compare returned an invalid total_commits")

        if total_commits > len(raw_commits):
            raise GitHubAPIError(
                "GitHub compare omitted commits from the incremental window; "
                "refusing to advance the SHA cursor on partial commit history"
            )

        limit = self.settings.max_items_per_source
        if len(raw_commits) > limit:
            raise GitHubAPIError(
                "incremental commit window exceeds configured item limit; "
                "refusing to advance the SHA cursor past unindexed commits"
            )

        return comparison

    def list_commits(
        self, repository: str, since_sha: str | None = None, head: str | None = None
    ) -> list[dict[str, Any]]:
        """Commits newer than ``since_sha``, or the most recent pages."""

        self._assert_allowed(repository)
        limit = self.settings.max_items_per_source
        if since_sha and head:
            comparison = self.compare(repository, since_sha, head)
            return list(comparison.get("commits", []))[:limit]

        items: list[dict[str, Any]] = []
        for page in self._iter_list_pages(
            f"repos/{repository}/commits", {"per_page": min(limit, 100), "sha": head}
        ):
            items.extend(page)
            if len(items) >= limit:
                break
        return items[:limit]

    def list_pull_requests(self, repository: str, since: str | None = None) -> list[dict[str, Any]]:
        """Return PRs, draining every revision newer than ``since``.

        ``max_items_per_source`` bounds initial snapshots, but it must not cap
        incremental polling. If more than that many PRs change in one cursor
        window, truncating to the newest N and then advancing the cursor would
        permanently skip the remainder. Incremental reads therefore paginate
        until the ``since`` boundary (or the global page safety cap) is reached.
        """

        self._assert_allowed(repository)
        limit = self.settings.max_items_per_source
        since_timestamp = (
            _parse_activity_timestamp(since, field="pull request activity cursor")
            if since is not None
            else None
        )
        incremental = since_timestamp is not None
        items: list[dict[str, Any]] = []

        for page in self._iter_list_pages(
            f"repos/{repository}/pulls",
            {
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": 100 if incremental else min(limit, 100),
            },
        ):
            reached_since = False
            for pull in page:
                if since_timestamp is not None:
                    updated_at = _parse_activity_timestamp(
                        pull.get("updated_at"), field="pull request updated_at"
                    )
                    if updated_at <= since_timestamp:
                        reached_since = True
                        break
                items.append(pull)
                if not incremental and len(items) >= limit:
                    return items
            if reached_since:
                break
        return items

    def list_issues(self, repository: str, since: str | None = None) -> list[dict[str, Any]]:
        """Issues only; incremental polls drain the full ``since`` window.

        GitHub's issues endpoint also returns PR-shaped rows, which are filtered
        out. As with PRs, ``max_items_per_source`` applies only to initial
        snapshots. When a cursor is present, the bounded pagination page limit
        is the safety cap so a burst cannot be silently truncated before the
        cursor is advanced.
        """

        self._assert_allowed(repository)
        limit = self.settings.max_items_per_source
        since_timestamp = (
            _parse_activity_timestamp(since, field="issue activity cursor")
            if since is not None
            else None
        )
        incremental = since_timestamp is not None
        items: list[dict[str, Any]] = []

        for page in self._iter_list_pages(
            f"repos/{repository}/issues",
            {
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "since": since,
                "per_page": 100 if incremental else min(limit, 100),
            },
        ):
            for issue in page:
                if "pull_request" in issue:
                    continue
                if since_timestamp is not None:
                    _parse_activity_timestamp(
                        issue.get("updated_at"), field="issue updated_at"
                    )
                items.append(issue)
                if not incremental and len(items) >= limit:
                    return items
        return items
