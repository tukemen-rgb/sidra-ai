"""GitHub read-only ingestion pipeline.

Order of operations, and why:

1. Resolve HEAD. One cheap request.
2. **Compare with stored state and local index state.** If HEAD is unchanged
   *and* this process already has retrievable documents for the repository,
   return immediately with ``changed=False``. If the SHA state survived a
   process restart but the in-memory index did not, rebuild the repository
   snapshot before applying normal differential behavior. Rehydration itself
   is not a source change and must not invoke the model when HEAD is unchanged.
3. Fetch only what changed (via ``compare``), plus README/docs on first run
   or when the diff touched them. If GitHub's compare response may be
   truncated, conservatively refresh README/docs so changed knowledge cannot
   be silently missed.
4. Screen every document through the security gate.
5. Index only ``ALLOW`` documents; quarantine the rest with reasons.
6. After a complete collection, retire README/docs paths that GitHub reports
   removed or renamed-away. Whenever README/docs were fully refreshed, also
   reconcile the current snapshot against the store so a deletion withheld
   during a failed run is still retired on the later full-snapshot retry.
7. Advance the persisted SHA only after a **complete** collection and indexing
   pass. Any source-fetch error preserves the previous cursor so the next run
   retries instead of making a partial RAG snapshot look current.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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

#: GitHub compare endpoint hard ceilings when callers do not paginate it.
COMPARE_COMMIT_CEILING = 250
COMPARE_FILE_CEILING = 300


def _comparison_may_be_truncated(comparison: dict[str, Any]) -> bool:
    """Return True when a compare payload cannot prove it is complete.

    ``total_commits`` lets us detect a shortened commit list directly. The
    file list has no equivalent total, so reaching the documented file
    ceiling is conservatively treated as truncation. A false positive only
    costs a documentation refresh; a false negative can leave stale RAG data.
    """

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
    """Return exact README/docs logical sources removed by a GitHub diff.

    Only exact paths are returned. ``renamed`` retires the previous filename;
    the new path is collected normally and becomes a distinct current source.
    Other repository files are intentionally ignored because L1's retirement
    contract is being consumed here only for RAG documentation sources.
    """

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
    """Read-only ingestion with commit-SHA differential fetching."""

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

    # ------------------------------------------------------------------
    def ingest_all(
        self, repositories: Sequence[str] | None = None, *, force: bool = False
    ) -> IngestionReport:
        targets = repositories or self.settings.allowed_repositories
        report = IngestionReport()
        for repository in targets:
            report.repositories.append(self.ingest_repository(repository, force=force))
        return report

    # ------------------------------------------------------------------
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

        # SHA state is persisted, while v0.1's retrieval index is in-memory.
        # After a process restart it is therefore possible to have a valid
        # persisted cursor but no local documents at all. In that case a
        # differential fetch is insufficient even if HEAD advanced: the new
        # process needs a complete current snapshot, not only the delta since
        # the old process. Rehydrate once before normal cheap polling resumes.
        index_missing = bool(previous_sha) and not self.store.by_repository(repository)
        rehydrate_index = index_missing and not force

        # A previous partial collection must also retry from a full snapshot.
        # In particular, HEAD may be unchanged while state.last_error records
        # that README/docs/issues/PRs were not completely fetched. Treating that
        # as a normal no-change poll would permanently freeze an incomplete RAG
        # view behind a seemingly current SHA.
        retry_full_snapshot = retry_incomplete

        # --- the differential short circuit -----------------------------
        if (
            head_sha == previous_sha
            and not force
            and not rehydrate_index
            and not retry_full_snapshot
        ):
            return RepositoryReport(
                repository=repository,
                changed=False,
                head_sha=head_sha,
                previous_sha=previous_sha,
                skipped_reason="no_new_commits",
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
            # A missing in-memory index or a previous incomplete collection
            # needs a complete snapshot, including current issues/PRs, rather
            # than only items newer than the persisted cursor.
            since=(
                None
                if rehydrate_index or retry_full_snapshot
                else (state.last_ingested_at or None)
            ),
        )

        source_changed = force or head_sha != previous_sha
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
        self._screen_and_index(documents, report)

        # Never advance the differential cursor after a partial collection.
        # Some safe documents may already have been re-indexed, but keeping the
        # old SHA and last_ingested_at makes the next run repeat the collection
        # idempotently instead of skipping missing knowledge forever. Deleted
        # source retirement is also withheld until collection is complete so a
        # transient fetch failure cannot make the local view more incomplete.
        if error:
            self.state_store.mark_error(repository, error)
            report.skipped_reason = "partial_fetch"
            return report

        for path, source_type in retirements:
            self.store.retire_source(
                repository=repository,
                path=path,
                source_type=source_type,
            )

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
            document_count=report.indexed,
            quarantined_count=report.quarantined,
            default_branch=default_branch,
            license=license_id,
        )
        return report

    # ------------------------------------------------------------------
    @staticmethod
    def _license_for(repo_meta: dict[str, Any]) -> str:
        license_info = (repo_meta or {}).get("license") or {}
        spdx = license_info.get("spdx_id")
        if spdx and spdx != "NOASSERTION":
            return str(spdx)
        return "proprietary" if (repo_meta or {}).get("private") else "unknown"

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
                    # A capped file list cannot prove README/docs were
                    # untouched, so refresh both roots at HEAD instead of
                    # silently carrying stale knowledge forward.
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

        # README/docs: always on first run, when touched, or when compare
        # completeness cannot be proven.
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

        return (
            documents,
            "; ".join(errors),
            retirements,
            full_documentation_refresh,
            current_documentation_sources,
        )

    # ------------------------------------------------------------------
    def _screen_and_index(
        self, documents: Sequence[Document], report: RepositoryReport
    ) -> None:
        for document in documents:
            result, screened = self.gate.screen_document(document)
            report.findings.extend(result.finding_labels)

            if result.decision is Decision.BLOCK:
                report.blocked += 1
                continue
            if result.decision is Decision.QUARANTINE or screened is None:
                report.quarantined += 1
                continue

            self.store.add(screened, gate_result=result)
            report.indexed += 1
