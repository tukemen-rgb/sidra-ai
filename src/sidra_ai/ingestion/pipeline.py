"""GitHub read-only ingestion pipeline.

Order of operations, and why:

1. Resolve HEAD. One cheap request.
2. **Compare with stored state and local index state.** If HEAD is unchanged
   *and* this process already has retrievable documents for the repository,
   keep the commit path cheap but periodically poll mutable PR/issue sources.
   If the SHA state survived a process restart but the in-memory index did not,
   rebuild the repository snapshot before applying normal differential behavior.
   Rehydration itself is not a source change and must not invoke the model when
   GitHub content is unchanged.
3. Fetch only what changed (via ``compare``), plus README/docs on first run
   or when the diff touched them. If GitHub's compare response may be
   truncated, conservatively refresh README/docs so changed knowledge cannot
   be silently missed.
4. Poll PR/issue bodies independently of commit HEAD. Those GitHub objects can
   change without a repository commit, so SHA equality alone is not a valid
   freshness proof. Idle polls are rate-limited locally and use a conservative
   overlap cursor; repeated overlap results are de-duplicated by source revision.
5. Screen every document through the security gate.
6. Index only ``ALLOW`` documents; quarantine the rest with reasons. For
   mutable GitHub sources, remember a rejected newest revision as a pending
   retirement instead of silently falling back to an older safe revision.
7. After a complete collection, retire README/docs paths that GitHub reports
   removed or renamed-away and apply pending security retirements. Whenever
   README/docs were fully refreshed, also reconcile the current snapshot
   against the store so a deletion withheld during a failed run is still
   retired on the later full-snapshot retry.
8. Advance persisted polling state only after a **complete** collection and
   indexing pass. Any source-fetch error preserves the previous cursor so the
   next run retries instead of making a partial RAG snapshot look current.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sidra_ai.config.settings import Settings, get_settings
from sidra_ai.documents import Document, SourceType
from sidra_ai.ingestion import normalize
from sidra_ai.ingestion.github_client import (
    GitHubAPIError,
    GitHubReadOnlyClient,
    RepositoryNotAllowedError,
)
from sidra_ai.ingestion.state import StateStore
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.decisions import Decision
from sidra_ai.security.gate import SecurityGate

#: Paths that always count as documentation roots.
DOC_ROOTS = ("docs",)

#: Mutable GitHub metadata is checked independently of repository HEAD because
#: PR/issue bodies and state can change without a commit. Five minutes keeps
#: interactive polling cheap while the hourly automation still always checks.
ACTIVITY_POLL_INTERVAL_SECONDS = 300

#: ``last_ingested_at`` is a local completion timestamp in the current v0.1
#: state schema, not an authoritative GitHub event watermark. Look back when
#: querying mutable sources so an update racing the previous poll is not lost.
#: Duplicate overlap results are removed against the current source revision.
ACTIVITY_CURSOR_OVERLAP_SECONDS = 600

#: GitHub source types whose logical path can be revised over time. If the
#: newest observed revision is unsafe, an older safe revision must not remain
#: retrievable as if it were current. Commit documents are immutable by SHA and
#: therefore are intentionally excluded.
MUTABLE_GITHUB_SOURCE_TYPES = frozenset(
    {
        SourceType.README,
        SourceType.DOCS,
        SourceType.PULL_REQUEST,
        SourceType.ISSUE,
    }
)

#: GitHub compare endpoint hard ceilings when callers do not paginate it.
COMPARE_COMMIT_CEILING = 250
COMPARE_FILE_CEILING = 300


def _comparison_may_be_truncated(comparison: dict[str, Any]) -> bool:
    """Return True when a compare payload cannot prove it is complete."""

    commits = list(comparison.get("commits") or [])
    files = list(comparison.get("files") or [])
    try:
        total_commits = int(comparison.get("total_commits") or 0)
    except (TypeError, ValueError):
        total_commits = 0

    return (
        total_commits > len(commits)
        or len(commits) >= COMPARE_COMMIT_CEILING
        or len(files) >= COMPARE_FILE_CEILING
    )


def _documentation_retirements(
    comparison: dict[str, Any],
) -> list[tuple[str, SourceType]]:
    """Return exact README/docs logical sources removed by a GitHub diff."""

    retirements: list[tuple[str, SourceType]] = []
    seen: set[tuple[str, SourceType]] = set()

    for file_info in comparison.get("files") or []:
        status = str(file_info.get("status") or "").strip().lower()
        candidates: list[str] = []
        if status == "removed":
            candidates.append(str(file_info.get("filename") or ""))
        elif status == "renamed":
            candidates.append(str(file_info.get("previous_filename") or ""))

        for path in candidates:
            path = path.strip()
            if not path:
                continue
            lowered = path.lower()
            if lowered.startswith("readme"):
                source_type = SourceType.README
            elif lowered == "docs" or lowered.startswith("docs/"):
                source_type = SourceType.DOCS
            else:
                continue

            key = (path, source_type)
            if key not in seen:
                seen.add(key)
                retirements.append(key)

    return retirements


def _parse_utc(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp as UTC, returning ``None`` if untrusted."""

    value = value.strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _activity_poll_due(last_ingested_at: str, *, now: datetime | None = None) -> bool:
    """Return whether mutable PR/issue sources should be checked now.

    An absent or invalid timestamp fails open *for polling*: doing a bounded
    read-only check is safer than silently treating an unknown cursor as fresh.
    """

    previous = _parse_utc(last_ingested_at)
    if previous is None:
        return True
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return (current - previous).total_seconds() >= ACTIVITY_POLL_INTERVAL_SECONDS


def _activity_since(last_ingested_at: str) -> str | None:
    """Return a conservative GitHub ``since`` cursor with overlap."""

    previous = _parse_utc(last_ingested_at)
    if previous is None:
        return None
    return (previous - timedelta(seconds=ACTIVITY_CURSOR_OVERLAP_SECONDS)).isoformat()


@dataclass
class RepositoryReport:
    """What happened for one repository."""

    repository: str
    changed: bool
    head_sha: str = ""
    previous_sha: str = ""
    indexed: int = 0
    quarantined: int = 0
    blocked: int = 0
    skipped_reason: str = ""
    error: str = ""
    findings: list[str] = field(default_factory=list)

    @property
    def requires_inference(self) -> bool:
        """Only a complete changed snapshot justifies spending model time."""

        return self.changed and self.indexed > 0 and not self.error

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "changed": self.changed,
            "head_sha": self.head_sha,
            "previous_sha": self.previous_sha,
            "indexed": self.indexed,
            "quarantined": self.quarantined,
            "blocked": self.blocked,
            "skipped_reason": self.skipped_reason,
            "error": self.error,
            "findings": list(self.findings),
        }


@dataclass
class IngestionReport:
    repositories: list[RepositoryReport] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return any(r.changed for r in self.repositories)

    @property
    def requires_inference(self) -> bool:
        return any(r.requires_inference for r in self.repositories)

    @property
    def total_indexed(self) -> int:
        return sum(r.indexed for r in self.repositories)

    @property
    def total_quarantined(self) -> int:
        return sum(r.quarantined for r in self.repositories)

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "requires_inference": self.requires_inference,
            "total_indexed": self.total_indexed,
            "total_quarantined": self.total_quarantined,
            "repositories": [r.to_dict() for r in self.repositories],
        }


class GitHubIngestionPipeline:
    """Read-only ingestion with commit-SHA and mutable-source polling."""

    def __init__(
        self,
        client: GitHubReadOnlyClient,
        store: DocumentStore,
        state_store: StateStore,
        gate: SecurityGate,
        settings: Settings | None = None,
    ) -> None:
        self.client = client
        self.store = store
        self.state_store = state_store
        self.gate = gate
        self.settings = settings or get_settings()

    def ingest_all(
        self, repositories: Sequence[str] | None = None, *, force: bool = False
    ) -> IngestionReport:
        targets = repositories or self.settings.allowed_repositories
        report = IngestionReport()
        for repository in targets:
            report.repositories.append(self.ingest_repository(repository, force=force))
        return report

    def ingest_repository(self, repository: str, *, force: bool = False) -> RepositoryReport:
        if not self.settings.is_repository_allowed(repository):
            return RepositoryReport(
                repository=repository,
                changed=False,
                error="repository is not on the SIDRA allowlist",
                skipped_reason="not_allowed",
            )

        state = self.state_store.load().get(repository)
        previous_sha = state.last_commit_sha
        retry_incomplete = bool(state.last_error) and not force

        try:
            repo_meta = self.client.get_repository(repository)
            default_branch = str(repo_meta.get("default_branch") or "main")
            head_sha = self.client.get_head_sha(repository, default_branch)
        except (GitHubAPIError, RepositoryNotAllowedError) as exc:
            self.state_store.mark_error(repository, str(exc))
            return RepositoryReport(
                repository=repository,
                changed=False,
                previous_sha=previous_sha,
                error=str(exc),
                skipped_reason="fetch_failed",
            )

        index_missing = bool(previous_sha) and not self.store.by_repository(repository)
        rehydrate_index = index_missing and not force
        retry_full_snapshot = retry_incomplete

        head_unchanged = head_sha == previous_sha
        if (
            head_unchanged
            and not force
            and not rehydrate_index
            and not retry_full_snapshot
        ):
            if not _activity_poll_due(state.last_ingested_at):
                return RepositoryReport(
                    repository=repository,
                    changed=False,
                    head_sha=head_sha,
                    previous_sha=previous_sha,
                    skipped_reason="no_new_commits",
                )
            return self._poll_mutable_activity(
                repository,
                head_sha=head_sha,
                previous_sha=previous_sha,
                default_branch=default_branch,
                license_id=self._license_for(repo_meta),
                since=_activity_since(state.last_ingested_at),
                previous_quarantined=state.quarantined_count,
            )

        license_id = self._license_for(repo_meta)
        (
            documents,
            error,
            retirements,
            documentation_snapshot_complete,
            current_documentation_sources,
        ) = self._collect(
            repository,
            head_sha=head_sha,
            previous_sha=previous_sha,
            license_id=license_id,
            first_run=(
                not previous_sha or force or rehydrate_index or retry_full_snapshot
            ),
            since=(
                None
                if rehydrate_index or retry_full_snapshot
                else _activity_since(state.last_ingested_at)
            ),
        )

        activity_changed = (
            not rehydrate_index and self._activity_documents_changed(documents)
        )
        source_changed = force or head_sha != previous_sha or activity_changed
        report = RepositoryReport(
            repository=repository,
            changed=source_changed,
            head_sha=head_sha,
            previous_sha=previous_sha,
            error=error,
            skipped_reason=(
                "index_rehydrated"
                if rehydrate_index and not source_changed
                else (
                    "partial_fetch_recovered"
                    if retry_full_snapshot and not source_changed
                    else ""
                )
            ),
        )
        security_retirements = self._screen_and_index(documents, report)

        if error:
            self.state_store.mark_error(repository, error)
            report.skipped_reason = "partial_fetch"
            return report

        self._apply_retirements(repository, [*retirements, *security_retirements])

        if documentation_snapshot_complete:
            current_keys = set(current_documentation_sources)
            for existing in tuple(self.store.by_repository(repository)):
                provenance = existing.provenance
                if provenance.source != "github":
                    continue
                if provenance.source_type not in {SourceType.README, SourceType.DOCS}:
                    continue
                key = (provenance.path, provenance.source_type)
                if key in current_keys:
                    continue
                self.store.retire_source(
                    repository=repository,
                    path=provenance.path,
                    source_type=provenance.source_type,
                )

        self.state_store.mark_ingested(
            repository,
            commit_sha=head_sha,
            document_count=len(self.store.by_repository(repository)),
            quarantined_count=state.quarantined_count + report.quarantined,
            default_branch=default_branch,
            license=license_id,
        )
        return report

    def _poll_mutable_activity(
        self,
        repository: str,
        *,
        head_sha: str,
        previous_sha: str,
        default_branch: str,
        license_id: str,
        since: str | None,
        previous_quarantined: int,
    ) -> RepositoryReport:
        """Poll PR/issues even when repository HEAD has not moved.

        The existing state schema stores a local completion timestamp, so the
        query intentionally overlaps that cursor. Returned overlap items are
        compared with the currently indexed logical revision before screening;
        unchanged items do not trigger inference or redundant index writes.
        """

        documents, error = self._collect_activity(
            repository,
            head_sha=head_sha,
            license_id=license_id,
            since=since,
        )
        changed_documents = [
            document
            for document in documents
            if not self._activity_revision_is_current(document)
        ]
        report = RepositoryReport(
            repository=repository,
            changed=bool(changed_documents),
            head_sha=head_sha,
            previous_sha=previous_sha,
            error=error,
            skipped_reason=(
                "mutable_source_updated" if changed_documents else "no_new_commits"
            ),
        )
        if error:
            self.state_store.mark_error(repository, error)
            report.skipped_reason = "partial_fetch"
            return report

        security_retirements = self._screen_and_index(changed_documents, report)
        self._apply_retirements(repository, security_retirements)
        self.state_store.mark_ingested(
            repository,
            commit_sha=head_sha,
            document_count=len(self.store.by_repository(repository)),
            quarantined_count=previous_quarantined + report.quarantined,
            default_branch=default_branch,
            license=license_id,
        )
        return report

    def _activity_revision_is_current(self, document: Document) -> bool:
        """Return True when the store already has this PR/issue revision.

        PR/issue ``updated_at`` can move for comment-only activity that v0.1 does
        not ingest. Compare the material fields SIDRA actually stores instead:
        body/title content, PR head observation, and state metadata. This
        suppresses cursor-overlap duplicates and comment-only churn without
        hiding a body/title/state revision.
        """

        provenance = document.provenance
        if provenance.source_type not in {SourceType.PULL_REQUEST, SourceType.ISSUE}:
            return False
        for existing in self.store.by_repository(provenance.repository):
            current = existing.provenance
            if current.source != provenance.source:
                continue
            if current.source_type is not provenance.source_type:
                continue
            if current.path != provenance.path:
                continue
            return (
                current.commit_sha == provenance.commit_sha
                and dict(current.extra) == dict(provenance.extra)
                and existing.content == document.content
            )
        return False

    def _activity_documents_changed(self, documents: Sequence[Document]) -> bool:
        """Whether a complete collection contains a newer PR/issue revision."""

        return any(
            document.provenance.source_type
            in {SourceType.PULL_REQUEST, SourceType.ISSUE}
            and not self._activity_revision_is_current(document)
            for document in documents
        )

    def _apply_retirements(
        self,
        repository: str,
        retirements: Sequence[tuple[str, SourceType]],
    ) -> None:
        for path, source_type in dict.fromkeys(retirements):
            self.store.retire_source(
                repository=repository,
                path=path,
                source_type=source_type,
            )

    @staticmethod
    def _license_for(repo_meta: dict[str, Any]) -> str:
        license_info = (repo_meta or {}).get("license") or {}
        spdx = license_info.get("spdx_id")
        if spdx and spdx != "NOASSERTION":
            return str(spdx)
        return "proprietary" if (repo_meta or {}).get("private") else "unknown"

    def _collect_activity(
        self,
        repository: str,
        *,
        head_sha: str,
        license_id: str,
        since: str | None,
    ) -> tuple[list[Document], str]:
        documents: list[Document] = []
        errors: list[str] = []

        try:
            for payload in self.client.list_pull_requests(repository, since=since):
                document = normalize.pull_request_document(
                    payload,
                    repository=repository,
                    commit_sha=head_sha,
                    license=license_id,
                )
                if document is not None:
                    documents.append(document)
        except GitHubAPIError as exc:
            errors.append(f"pulls: {exc}")

        try:
            for payload in self.client.list_issues(repository, since=since):
                document = normalize.issue_document(
                    payload,
                    repository=repository,
                    commit_sha=head_sha,
                    license=license_id,
                )
                if document is not None:
                    documents.append(document)
        except GitHubAPIError as exc:
            errors.append(f"issues: {exc}")

        return documents, "; ".join(errors)

    def _collect(
        self,
        repository: str,
        *,
        head_sha: str,
        previous_sha: str,
        license_id: str,
        first_run: bool,
        since: str | None,
    ) -> tuple[
        list[Document],
        str,
        list[tuple[str, SourceType]],
        bool,
        set[tuple[str, SourceType]],
    ]:
        """Gather documents for this run. Errors degrade, never abort."""

        documents: list[Document] = []
        errors: list[str] = []
        retirements: list[tuple[str, SourceType]] = []
        current_documentation_sources: set[tuple[str, SourceType]] = set()

        changed_paths: set[str] = set()
        commits: list[dict[str, Any]] = []
        full_documentation_refresh = first_run

        try:
            if previous_sha and not first_run:
                comparison = self.client.compare(repository, previous_sha, head_sha)
                commits = list(comparison.get("commits", []))
                changed_paths = {
                    str(f.get("filename", "")) for f in comparison.get("files", [])
                }
                retirements = _documentation_retirements(comparison)
                if _comparison_may_be_truncated(comparison):
                    full_documentation_refresh = True
            else:
                commits = self.client.list_commits(repository, head=head_sha)
        except GitHubAPIError as exc:
            errors.append(f"history: {exc}")

        for payload in commits[: self.settings.max_items_per_source]:
            document = normalize.commit_document(
                payload, repository=repository, license=license_id
            )
            if document is not None:
                documents.append(document)

        readme_touched = full_documentation_refresh or any(
            path.lower().startswith("readme") for path in changed_paths
        )
        docs_touched = full_documentation_refresh or any(
            path.startswith(DOC_ROOTS) for path in changed_paths
        )

        if readme_touched:
            try:
                payload = self.client.get_readme(repository, ref=head_sha)
                if payload:
                    document = normalize.readme_document(
                        payload,
                        repository=repository,
                        commit_sha=head_sha,
                        license=license_id,
                    )
                    if document is not None:
                        documents.append(document)
                        if full_documentation_refresh:
                            current_documentation_sources.add(
                                (document.provenance.path, SourceType.README)
                            )
            except GitHubAPIError as exc:
                errors.append(f"readme: {exc}")

        if docs_touched:
            try:
                for entry in self.client.list_docs_paths(repository, ref=head_sha):
                    payload = self.client.get_contents(
                        repository, entry["path"], ref=head_sha
                    )
                    if not isinstance(payload, dict):
                        continue
                    document = normalize.doc_document(
                        payload,
                        repository=repository,
                        commit_sha=head_sha,
                        license=license_id,
                    )
                    if document is not None:
                        documents.append(document)
                        if full_documentation_refresh:
                            current_documentation_sources.add(
                                (document.provenance.path, SourceType.DOCS)
                            )
            except GitHubAPIError as exc:
                errors.append(f"docs: {exc}")

        activity_documents, activity_error = self._collect_activity(
            repository,
            head_sha=head_sha,
            license_id=license_id,
            since=since,
        )
        documents.extend(activity_documents)
        if activity_error:
            errors.append(activity_error)

        return (
            documents,
            "; ".join(errors),
            retirements,
            full_documentation_refresh,
            current_documentation_sources,
        )

    def _screen_and_index(
        self, documents: Sequence[Document], report: RepositoryReport
    ) -> list[tuple[str, SourceType]]:
        """Screen/index documents and return unsafe mutable sources to retire."""

        security_retirements: list[tuple[str, SourceType]] = []
        seen: set[tuple[str, SourceType]] = set()

        for document in documents:
            result, screened = self.gate.screen_document(document)
            report.findings.extend(result.finding_labels)

            rejected = result.decision is not Decision.ALLOW or screened is None
            if rejected:
                if result.decision is Decision.BLOCK:
                    report.blocked += 1
                else:
                    report.quarantined += 1

                provenance = document.provenance
                if (
                    provenance.source == "github"
                    and provenance.source_type in MUTABLE_GITHUB_SOURCE_TYPES
                ):
                    key = (provenance.path, provenance.source_type)
                    if key not in seen:
                        seen.add(key)
                        security_retirements.append(key)
                continue

            self.store.add(screened, gate_result=result)
            report.indexed += 1

        return security_retirements
