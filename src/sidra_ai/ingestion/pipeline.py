"""GitHub read-only ingestion pipeline.

Order of operations, and why:

1. Resolve HEAD. One cheap request.
2. **Compare with stored state.** If HEAD is unchanged, return immediately
   with ``changed=False``. Nothing is fetched, nothing is chunked, and the
   caller knows not to run inference. Idle repositories cost one API call.
3. Fetch only what changed (via ``compare``), plus README/docs on first run
   or when the diff touched them.
4. Screen every document through the security gate.
5. Index only ``ALLOW`` documents; quarantine the rest with reasons.
6. Persist the new SHA **after** indexing, so a crash mid-run re-ingests
   rather than skipping content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from sidra_ai.config.settings import Settings, get_settings
from sidra_ai.documents import Document
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
        """Only changed repositories justify spending model time."""

        return self.changed and self.indexed > 0

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

        try:
            repo_meta = self.client.get_repository(repository)
            default_branch = str(repo_meta.get("default_branch") or "main")
            head_sha = self.client.get_head_sha(repository, default_branch)
        except (GitHubAPIError, RepositoryNotAllowedError) as exc:
            self.state_store.mark_error(repository, str(exc))
            return RepositoryReport(
                repository=repository, changed=False, previous_sha=previous_sha,
                error=str(exc), skipped_reason="fetch_failed",
            )

        # --- the differential short circuit -----------------------------
        if head_sha == previous_sha and not force:
            return RepositoryReport(
                repository=repository,
                changed=False,
                head_sha=head_sha,
                previous_sha=previous_sha,
                skipped_reason="no_new_commits",
            )

        license_id = self._license_for(repo_meta)
        documents, error = self._collect(
            repository,
            head_sha=head_sha,
            previous_sha=previous_sha,
            license_id=license_id,
            first_run=not previous_sha or force,
            since=state.last_ingested_at or None,
        )

        report = RepositoryReport(
            repository=repository,
            changed=True,
            head_sha=head_sha,
            previous_sha=previous_sha,
            error=error,
        )
        self._screen_and_index(documents, report)

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
    ) -> tuple[list[Document], str]:
        """Gather documents for this run. Errors degrade, never abort."""

        documents: list[Document] = []
        errors: list[str] = []

        changed_paths: set[str] = set()
        commits: list[dict[str, Any]] = []

        try:
            if previous_sha and not first_run:
                comparison = self.client.compare(repository, previous_sha, head_sha)
                commits = list(comparison.get("commits", []))
                changed_paths = {
                    str(f.get("filename", "")) for f in comparison.get("files", [])
                }
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

        # README/docs: always on first run, otherwise only when touched.
        readme_touched = first_run or any(
            path.lower().startswith("readme") for path in changed_paths
        )
        docs_touched = first_run or any(
            path.startswith(DOC_ROOTS) for path in changed_paths
        )

        if readme_touched:
            try:
                payload = self.client.get_readme(repository, ref=head_sha)
                if payload:
                    document = normalize.readme_document(
                        payload, repository=repository, commit_sha=head_sha,
                        license=license_id,
                    )
                    if document is not None:
                        documents.append(document)
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
                        payload, repository=repository, commit_sha=head_sha,
                        license=license_id,
                    )
                    if document is not None:
                        documents.append(document)
            except GitHubAPIError as exc:
                errors.append(f"docs: {exc}")

        try:
            for payload in self.client.list_pull_requests(repository, since=since):
                document = normalize.pull_request_document(
                    payload, repository=repository, commit_sha=head_sha,
                    license=license_id,
                )
                if document is not None:
                    documents.append(document)
        except GitHubAPIError as exc:
            errors.append(f"pulls: {exc}")

        try:
            for payload in self.client.list_issues(repository, since=since):
                document = normalize.issue_document(
                    payload, repository=repository, commit_sha=head_sha,
                    license=license_id,
                )
                if document is not None:
                    documents.append(document)
        except GitHubAPIError as exc:
            errors.append(f"issues: {exc}")

        return documents, "; ".join(errors)

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
