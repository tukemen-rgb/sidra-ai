"""Offline release gate for mutable Issue activity cursor integrity.

Issue bodies and state can change while repository HEAD stays fixed. If an
incremental GitHub Issues response contains a real Issue whose ``updated_at``
cannot be trusted, advancing the local activity cursor would let SIDRA treat an
incomplete mutable-source poll as current knowledge. This suite exercises the
real ``GitHubReadOnlyClient.list_issues`` and ingestion pipeline to prove an
ambiguous Issue revision fails closed while the prior retrievable RAG snapshot
and activity cursor remain paired.
"""

from __future__ import annotations

from tempfile import TemporaryDirectory
from typing import Any, Mapping

from sidra_ai.config.settings import Settings
from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.ingestion.github_client import GitHubReadOnlyClient, Response
from sidra_ai.ingestion.pipeline import GitHubIngestionPipeline
from sidra_ai.ingestion.state import IngestionState, RepositoryState, StateStore
from sidra_ai.retrieval.search import BM25Retriever
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.gate import SecurityGate

_REPOSITORY = "tukemen-rgb/site"
_HEAD_SHA = "a" * 40
_OLD_CURSOR = "2000-01-01T00:00:00+00:00"
_OLD_QUERY = "stable_marker_issue_cursor"
_NEW_QUERY = "untrusted_new_issue_marker"


class _IssueCursorClient(GitHubReadOnlyClient):
    """Network-free client that leaves production ``list_issues`` intact."""

    def __init__(self, settings: Settings) -> None:
        def transport(
            method: str,
            url: str,
            headers: Mapping[str, str],
            timeout: float,
        ) -> Response:
            del headers, timeout
            if method != "GET":
                raise AssertionError("issue activity eval must remain GET-only")
            if "/issues?" not in url or "since=" not in url:
                raise AssertionError(f"unexpected GitHub request in offline eval: {url}")
            return Response(
                200,
                {},
                [
                    {
                        "number": 7,
                        "title": "new mutable issue revision",
                        "body": _NEW_QUERY,
                        "state": "open",
                        "updated_at": None,
                    }
                ],
            )

        super().__init__(settings=settings, transport=transport, sleep=lambda _: None)

    def get_repository(self, repository: str) -> dict[str, Any]:
        self._assert_allowed(repository)
        return {
            "default_branch": "main",
            "private": False,
            "license": {"spdx_id": "MIT"},
        }

    def get_head_sha(self, repository: str, branch: str | None = None) -> str:
        del branch
        self._assert_allowed(repository)
        return _HEAD_SHA

    def list_pull_requests(
        self, repository: str, since: str | None = None
    ) -> list[dict[str, Any]]:
        del since
        self._assert_allowed(repository)
        return []


def _seed_prior_snapshot(store: DocumentStore, state_store: StateStore) -> None:
    store.add(
        Document(
            content=f"{_OLD_QUERY} is the previously verified Issue evidence.",
            provenance=Provenance(
                source="github",
                repository=_REPOSITORY,
                path="issues/7",
                commit_sha=_HEAD_SHA,
                timestamp=_OLD_CURSOR,
                source_type=SourceType.ISSUE,
                trust_level=TrustLevel.INTERNAL_REPO,
                license="MIT",
                extra={"state": "open"},
            ),
        )
    )
    state_store.save(
        IngestionState(
            repositories={
                _REPOSITORY: RepositoryState(
                    repository=_REPOSITORY,
                    last_commit_sha=_HEAD_SHA,
                    last_ingested_at=_OLD_CURSOR,
                    default_branch="main",
                    license="MIT",
                    document_count=1,
                )
            }
        )
    )


def _search(store: DocumentStore, query: str) -> tuple[tuple[str, str, str], ...]:
    results = BM25Retriever(store).search(
        query,
        top_k=3,
        repositories=(_REPOSITORY,),
    )
    return tuple(
        (result.provenance.commit_sha, result.provenance.path, result.content)
        for result in results
    )


def run_issue_activity_cursor_safety_suite() -> list[EvalOutcome]:
    """Release-gate mutable Issue freshness without GitHub, model, or Web I/O."""

    failures: list[str] = []
    settings = Settings(allowed_repositories=(_REPOSITORY,))
    gate = SecurityGate(allowed_repositories=(_REPOSITORY,))

    with TemporaryDirectory() as data_dir:
        store = DocumentStore(gate=gate)
        state_store = StateStore(f"{data_dir}/state.json")
        _seed_prior_snapshot(store, state_store)
        before = _search(store, _OLD_QUERY)

        pipeline = GitHubIngestionPipeline(
            client=_IssueCursorClient(settings),
            store=store,
            state_store=state_store,
            gate=gate,
            settings=settings,
        )
        report = pipeline.ingest_repository(_REPOSITORY)
        state = state_store.load().get(_REPOSITORY)
        after = _search(store, _OLD_QUERY)
        untrusted = _search(store, _NEW_QUERY)

    if not before or any(item[0] != _HEAD_SHA for item in before):
        failures.append("eval fixture did not start from retrievable verified Issue evidence")
    if report.skipped_reason != "partial_fetch":
        failures.append(
            f"ambiguous Issue activity was not marked partial_fetch ({report.skipped_reason!r})"
        )
    if "invalid issue updated_at" not in report.error:
        failures.append("ambiguous Issue timestamp did not surface a fail-closed fetch error")
    if report.requires_inference:
        failures.append("ambiguous Issue activity incorrectly requested inference")
    if state.last_commit_sha != _HEAD_SHA:
        failures.append("repository SHA cursor changed during failed mutable activity poll")
    if state.last_ingested_at != _OLD_CURSOR:
        failures.append("Issue activity cursor advanced past an ambiguous revision")
    if not state.last_error:
        failures.append("ambiguous Issue activity did not persist a retryable error")
    if after != before:
        failures.append("retrievable Issue snapshot changed after incomplete activity poll")
    if untrusted:
        failures.append("Issue revision with ambiguous timestamp became retrievable")

    return [
        EvalOutcome(
            case_name="rag_issue_activity_cursor_preserves_verified_snapshot",
            passed=not failures,
            detail="ambiguous Issue activity must preserve prior cursor and RAG evidence",
            failures=tuple(failures),
        )
    ]
