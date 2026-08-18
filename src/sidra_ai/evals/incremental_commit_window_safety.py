"""Offline release gate for complete incremental GitHub commit ingestion.

A repository SHA cursor is a grounding boundary: once it advances, SIDRA treats
that GitHub revision as observed. If a compare window is truncated or larger
than the bounded commit-document budget, advancing after indexing only a prefix
would permanently hide commit provenance from RAG. This suite uses the real
``GitHubReadOnlyClient.compare`` and ingestion pipeline to prove incomplete
commit history fails closed while the previous retrievable snapshot and SHA
cursor remain paired.
"""

from __future__ import annotations

from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from typing import Any

from sidra_ai.config.settings import Settings
from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.ingestion.github_client import GitHubReadOnlyClient
from sidra_ai.ingestion.pipeline import GitHubIngestionPipeline
from sidra_ai.ingestion.state import StateStore
from sidra_ai.retrieval.search import BM25Retriever
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.gate import SecurityGate

_REPOSITORY = "tukemen-rgb/site"
_OLD_SHA = "a" * 40
_NEW_SHA = "e" * 40
_QUERY = "stable_marker_commit_window"


class _IncrementalWindowClient(GitHubReadOnlyClient):
    """Network-free client that leaves production ``compare`` logic intact."""

    def __init__(self, settings: Settings, comparison: dict[str, Any]) -> None:
        super().__init__(settings=settings)
        self._comparison = comparison

    def _get_json(self, path: str, params=None):  # noqa: ANN001, ANN201
        if "/compare/" in path:
            return self._comparison
        raise AssertionError(f"unexpected GitHub request in offline eval: {path}")

    def get_repository(self, repository: str) -> dict[str, Any]:
        self._assert_allowed(repository)
        return {
            "default_branch": "main",
            "private": False,
            "license": {"spdx_id": "MIT"},
        }

    def get_head_sha(self, repository: str, branch: str | None = None) -> str:
        self._assert_allowed(repository)
        return _NEW_SHA

    def list_pull_requests(
        self, repository: str, since: str | None = None
    ) -> list[dict[str, Any]]:
        self._assert_allowed(repository)
        return []

    def list_issues(
        self, repository: str, since: str | None = None
    ) -> list[dict[str, Any]]:
        self._assert_allowed(repository)
        return []


def _seed_snapshot(store: DocumentStore, state_store: StateStore) -> None:
    document = Document(
        content=f"{_QUERY} is the previously verified grounding evidence.",
        provenance=Provenance(
            source="github",
            repository=_REPOSITORY,
            path="README.md",
            commit_sha=_OLD_SHA,
            timestamp=datetime(2026, 8, 17, tzinfo=timezone.utc),
            source_type=SourceType.README,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="MIT",
        ),
    )
    store.add(document)
    state_store.mark_ingested(
        _REPOSITORY,
        commit_sha=_OLD_SHA,
        document_count=1,
        default_branch="main",
        license="MIT",
    )


def _retrieved_snapshot(store: DocumentStore) -> tuple[tuple[str, str, str], ...]:
    results = BM25Retriever(store).search(
        _QUERY,
        top_k=3,
        repositories=(_REPOSITORY,),
    )
    return tuple(
        (result.provenance.commit_sha, result.provenance.path, result.content)
        for result in results
    )


def _run_incomplete_window_case(
    *,
    case_name: str,
    comparison: dict[str, Any],
    expected_error_fragment: str,
) -> EvalOutcome:
    failures: list[str] = []
    settings = Settings(
        allowed_repositories=(_REPOSITORY,),
        max_items_per_source=2,
    )
    gate = SecurityGate(allowed_repositories=(_REPOSITORY,))

    with TemporaryDirectory() as data_dir:
        store = DocumentStore(gate=gate)
        state_store = StateStore(f"{data_dir}/state.json")
        _seed_snapshot(store, state_store)
        before = _retrieved_snapshot(store)

        client = _IncrementalWindowClient(settings, comparison)
        pipeline = GitHubIngestionPipeline(
            client=client,
            store=store,
            state_store=state_store,
            gate=gate,
            settings=settings,
        )
        report = pipeline.ingest_repository(_REPOSITORY)
        state = state_store.load().get(_REPOSITORY)
        after = _retrieved_snapshot(store)

    if not before or any(item[0] != _OLD_SHA for item in before):
        failures.append("eval fixture did not start from retrievable old-SHA evidence")
    if report.skipped_reason != "partial_fetch":
        failures.append(
            f"incomplete history was not marked partial_fetch ({report.skipped_reason!r})"
        )
    if expected_error_fragment not in report.error:
        failures.append("incomplete commit history did not surface the expected fail-closed error")
    if report.requires_inference:
        failures.append("incomplete commit history incorrectly requested inference")
    if state.last_commit_sha != _OLD_SHA:
        failures.append("SHA cursor advanced past an incomplete commit window")
    if not state.last_error:
        failures.append("incomplete commit history did not persist a retryable error")
    if after != before:
        failures.append("retrievable RAG snapshot changed after incomplete commit history")
    if any(item[0] == _NEW_SHA for item in after):
        failures.append("new incomplete SHA became retrievable")

    return EvalOutcome(
        case_name=case_name,
        passed=not failures,
        detail="incomplete commit history must preserve the prior SHA/RAG snapshot",
        failures=tuple(failures),
    )


def run_incremental_commit_window_safety_suite() -> list[EvalOutcome]:
    """Release-gate commit-window completeness without GitHub or model I/O."""

    oversized = {
        "status": "ahead",
        "total_commits": 3,
        "commits": [
            {"sha": "1" * 40},
            {"sha": "2" * 40},
            {"sha": "3" * 40},
        ],
        "files": [],
    }
    truncated = {
        "status": "ahead",
        "total_commits": 3,
        "commits": [
            {"sha": "1" * 40},
            {"sha": "2" * 40},
        ],
        "files": [],
    }
    return [
        _run_incomplete_window_case(
            case_name="rag_incremental_commit_window_budget_preserves_snapshot",
            comparison=oversized,
            expected_error_fragment="incremental commit window exceeds",
        ),
        _run_incomplete_window_case(
            case_name="rag_truncated_compare_preserves_snapshot",
            comparison=truncated,
            expected_error_fragment="omitted commits",
        ),
    ]
