"""Oversized data files stay out of the index, and that is the decision.

Two JSON files in ``tukemen-rgb/site`` exceed the byte budget and are BLOCKed.
They are record arrays, not prose, and the backlog asked whether to build a
separate path that makes them searchable anyway. The answer is no, for reasons
that are worth pinning rather than re-deciding:

* The budget is a boundary, and splitting dissolves it. A path that cuts an
  oversized payload into sub-budget pieces does not respect the limit, it
  changes the unit the limit counts. One input would still be able to consume
  unbounded downstream work; the guard would only look like it was there.
* The supported route already exists and has the right shape.
  ``SIDRA_MAX_INPUT_BYTES`` raises the budget by operator decision, validated
  at startup and visible in ``redacted_dict()``. "I want that catalog indexed"
  is answerable today by an auditable configuration change, rather than by
  code that quietly exempts a class of file from the limit.
* Indexing record arrays would work against retrieval, which is the point.
  ``_diversify_results`` exists because one document dominating the top-k
  degrades answers; a few thousand near-identical records is that pathology
  on purpose.

What the gate must keep providing is enough information to make that operator
decision: which repository, and why. These tests hold the decision and that
attribution in place.
"""

from __future__ import annotations

import json

from datetime import datetime, timezone

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.ingestion.pipeline import GitHubIngestionPipeline, RepositoryReport
from sidra_ai.ingestion.state import StateStore
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.decisions import Decision
from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

REPOSITORY = "tukemen-rgb/site"
BUDGET = 2048


def _catalog(records: int = 200) -> str:
    """A record array shaped like the files this decision is about."""

    return json.dumps([{"id": n, "name": f"item-{n}"} for n in range(records)])


def _provenance() -> Provenance:
    return Provenance(
        source="github",
        repository=REPOSITORY,
        path="src/data/catalog.json",
        commit_sha="a" * 40,
        timestamp=datetime(2026, 8, 19, tzinfo=timezone.utc),
        source_type=SourceType.DOCS,
        trust_level=TrustLevel.INTERNAL_REPO,
        license="proprietary",
    )


def _gate(tmp_path, *, max_bytes: int = BUDGET, released=None) -> SecurityGate:
    return SecurityGate(
        GatePolicy(max_input_bytes=max_bytes),
        allowed_repositories=(REPOSITORY,),
        quarantine_store=QuarantineStore(tmp_path / "quarantine.jsonl"),
        released_document_ids=released,
    )


def test_an_oversized_data_file_is_blocked_and_never_indexed(tmp_path) -> None:
    gate = _gate(tmp_path)
    document = Document(content=_catalog(), provenance=_provenance())

    result, screened = gate.screen_document(document)

    assert result.decision is Decision.BLOCK
    assert screened is None, "an oversized payload must not produce indexable content"
    # The rejection is about size and says so, rather than being a generic refusal.
    assert result.finding_labels == ("oversized_input:byte_budget",)
    (finding,) = result.findings
    assert finding.metadata["max_bytes"] == BUDGET
    assert finding.metadata["size_bytes"] > BUDGET


def test_the_rejection_is_attributable_to_a_repository_and_a_reason(
    tmp_path, client, settings
) -> None:
    """An operator has to be able to act on this, so the report must say enough.

    Not "two documents were rejected" - which repository, and because of what.
    Without both, the configuration change this decision points to is not a
    decision anyone can make.
    """

    gate = _gate(tmp_path)
    pipeline = GitHubIngestionPipeline(
        client=client,
        store=DocumentStore(gate),
        state_store=StateStore(tmp_path / "state.json"),
        gate=gate,
        settings=settings,
    )
    report = RepositoryReport(repository=REPOSITORY, changed=True)

    pipeline._screen_and_index(
        [Document(content=_catalog(), provenance=_provenance())], report
    )

    assert report.repository == REPOSITORY
    assert report.blocked == 1
    assert report.indexed == 0
    assert "oversized_input:byte_budget" in report.findings
    assert "oversized_input:byte_budget" in report.to_dict()["findings"]


def test_raising_the_budget_is_the_supported_route(tmp_path) -> None:
    """The escape hatch exists; it is a configuration decision, not a code path.

    The same document the default budget refuses is indexed once an operator
    raises the limit. That is deliberately the only way in: it is explicit,
    auditable and applies to every input rather than to a favoured class.
    """

    content = _catalog()
    generous = _gate(tmp_path, max_bytes=len(content.encode("utf-8")) + 1)
    store = DocumentStore(generous)

    result, screened = generous.screen_document(
        Document(content=content, provenance=_provenance())
    )

    assert result.decision is Decision.ALLOW
    assert screened is not None
    store.add(screened, gate_result=result)
    assert len(store) == 1


def test_human_release_does_not_admit_an_oversized_file(tmp_path) -> None:
    """There is no review-shaped way around the budget either.

    ``sidra-quarantine release`` is the other route by which a rejected
    document can reach the index. It is deliberately QUARANTINE-only: a BLOCK
    is a policy refusal, and approving one would turn the boundary into a
    suggestion. Pinned here because it would otherwise be an easy accident.
    """

    document = Document(content=_catalog(), provenance=_provenance())
    gate = _gate(tmp_path, released=lambda: {document.doc_id})

    result, screened = gate.screen_document(document)

    assert result.decision is Decision.BLOCK
    assert screened is None
