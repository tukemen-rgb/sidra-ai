"""Offline RAG grounding checks.

The v0.1 service can return provenance-rich citations, but a generative local
model may still fabricate source labels (for example ``[S99]``), omit citations
entirely while making factual claims, pretend to have evidence when retrieval
returned nothing, or answer from two active versions of the same logical
source. These checks make those regressions measurable without a network
connection or model weights.

This evaluator intentionally checks *citation integrity, abstention, and source
version consistency*, not semantic truth. Semantic entailment needs a stronger
judge/model later; v0.1 must first guarantee that cited labels actually came
from the retrieval context and that conflicting historical versions do not
silently support a factual answer.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence

from sidra_ai.documents import Chunk, Provenance, SourceType, TrustLevel
from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.models.base import GenerationRequest
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.security.data_envelope import build_data_context

_CITATION = re.compile(r"\[(S\d+)\]")
_NO_EVIDENCE_MARKERS = (
    "no indexed evidence",
    "there is insufficient evidence",
    "insufficient evidence",
    "there is not enough evidence",
    "not enough evidence",
    "the data does not answer",
    "the evidence does not answer",
    "現時点では十分な根拠がありません",
    "現在の情報では十分な根拠がありません",
    "根拠がありません",
    "十分な根拠がありません",
    "情報がありません",
    "情報が見つかりません",
)
_ABSTENTION_ADVISORY_PREFIXES = (
    "run ",
    "rephrase ",
    "provide ",
    "please provide ",
    "try ",
    "add ",
    "ingest ",
    "question received:",
    "追加",
    "別の",
    "再度",
    "確認",
    "資料を",
    "情報を",
)
_ABSTENTION_CONTRAST = re.compile(
    r"(?:\bbut\b|\bhowever\b|\bnevertheless\b|\bnonetheless\b|\byet\b|"
    r"\bstill\b|\bthough\b|\balthough\b|ただし|しかし|だが|でも|とはいえ)"
)
_SENTENCE_SPLIT = re.compile(r"(?:[.!?。！？]+|\n+)\s*")
_LEADING_FORMAT = " \t\r\n-*#>_:;,.!?()[]{}'\"`。！？：「」『』（）"


@dataclass(frozen=True)
class GroundingResult:
    """Citation-level grounding verdict for one generated answer."""

    passed: bool
    used_labels: tuple[str, ...]
    available_labels: tuple[str, ...]
    failures: tuple[str, ...] = ()


def _abstention_marker_at_start(text: str) -> str | None:
    normalized = text.lower().lstrip(_LEADING_FORMAT)
    for marker in _NO_EVIDENCE_MARKERS:
        if normalized.startswith(marker):
            return marker
    return None


def _is_abstention(answer: str) -> bool:
    """Return True only for a clear abstention, not a hedge around a claim.

    A substring check is unsafe here: ``"insufficient evidence, but X is true"``
    would otherwise bypass the no-evidence and conflicting-version guards. The
    evaluator therefore requires the first sentence to start with an explicit
    abstention marker, forbids citations and contrastive claim continuations,
    and only permits later sentences that are another abstention or operational
    advice about obtaining evidence.
    """

    stripped = answer.strip()
    if not stripped or _CITATION.search(stripped):
        return False

    sentences = [part.strip() for part in _SENTENCE_SPLIT.split(stripped) if part.strip()]
    if not sentences:
        return False

    first = sentences[0]
    marker = _abstention_marker_at_start(first)
    if marker is None:
        return False

    first_normalized = first.lower().lstrip(_LEADING_FORMAT)
    first_tail = first_normalized[len(marker) :]
    if _ABSTENTION_CONTRAST.search(first_tail):
        return False

    for sentence in sentences[1:]:
        normalized = sentence.lower().lstrip(_LEADING_FORMAT)
        if _abstention_marker_at_start(normalized) is not None:
            continue
        if any(normalized.startswith(prefix) for prefix in _ABSTENTION_ADVISORY_PREFIXES):
            continue
        return False

    return True


def _conflicting_source_versions(
    citations: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    """Return logical sources that appear at more than one commit SHA.

    Incremental ingestion currently identifies documents using commit SHA, so a
    replaced README/doc can coexist with its historical version unless the
    indexing path explicitly retires the old entry. Both labels are syntactically
    valid citations, but treating them as simultaneous evidence can produce a
    confidently cited stale answer. Until the store guarantees one active
    version per logical source, grounding must fail closed on that ambiguity.
    """

    versions: dict[tuple[str, str], set[str]] = defaultdict(set)
    for item in citations:
        repository = str(item.get("repository") or "").strip()
        path = str(item.get("path") or "").strip()
        commit_sha = str(item.get("commit_sha") or "").strip()
        if repository and path and commit_sha:
            versions[(repository, path)].add(commit_sha)

    conflicts: list[str] = []
    for (repository, path), shas in sorted(versions.items()):
        if len(shas) <= 1:
            continue
        short = ",".join(sorted(sha[:7] for sha in shas))
        conflicts.append(f"{repository}:{path}@[{short}]")
    return tuple(conflicts)


def evaluate_grounding(
    answer: str,
    citations: Sequence[Mapping[str, object]],
    *,
    require_citation_when_evidence_exists: bool = True,
) -> GroundingResult:
    """Validate citation integrity, abstention, and source-version consistency.

    Rules:
    - every ``[S#]`` label used by the answer must exist in ``citations``;
    - when retrieval returned evidence, a factual/non-abstaining answer must cite
      at least one available label;
    - a *clear* abstention is allowed even when retrieval returned chunks,
      because retrieval relevance is imperfect and the model may correctly
      decide that the retrieved text does not answer the question;
    - an answer that merely embeds an abstention phrase around a factual claim is
      not treated as an abstention;
    - when retrieval returned no evidence, the answer must not invent a source
      label and must explicitly indicate that evidence is unavailable;
    - if the retrieval context contains multiple commit versions of the same
      repository/path, a factual answer must abstain rather than choose one
      silently. This is conservative until ingestion/store retirement is fixed.
    """

    available = tuple(
        str(item.get("label"))
        for item in citations
        if item.get("label") is not None and str(item.get("label")).strip()
    )
    available_set = set(available)
    used = tuple(dict.fromkeys(_CITATION.findall(answer)))
    used_set = set(used)
    failures: list[str] = []
    abstained = _is_abstention(answer)

    invented = sorted(used_set - available_set)
    if invented:
        failures.append("invented citation labels: " + ", ".join(invented))

    conflicts = _conflicting_source_versions(citations)
    if conflicts and answer.strip() and not abstained:
        failures.append(
            "retrieval context contains multiple versions of the same logical source: "
            + "; ".join(conflicts)
        )

    if available_set:
        if (
            require_citation_when_evidence_exists
            and answer.strip()
            and not abstained
            and not (used_set & available_set)
        ):
            failures.append("answer made a grounded claim but cited none of the available labels")
    else:
        if used:
            failures.append("answer cited a source even though retrieval returned no evidence")
        if answer.strip() and not abstained:
            failures.append("no-evidence answer did not explicitly abstain")

    return GroundingResult(
        passed=not failures,
        used_labels=used,
        available_labels=available,
        failures=tuple(failures),
    )


def _chunk(content: str, *, path: str, index: int) -> Chunk:
    provenance = Provenance(
        source="github",
        repository="tukemen-rgb/sidra-ai",
        path=path,
        commit_sha="e" * 40,
        timestamp=datetime(2026, 8, 15, tzinfo=timezone.utc),
        source_type=SourceType.DOCS,
        trust_level=TrustLevel.INTERNAL_REPO,
        license="proprietary",
    )
    return Chunk(
        content=content,
        provenance=provenance,
        document_id=f"eval-{index}",
        index=index,
    )


def run_grounding_suite() -> tuple[EvalOutcome, ...]:
    """Run deterministic end-to-end grounding checks with the offline backend."""

    model = EchoModelAdapter()
    chunks = (
        _chunk(
            "SIDRA AI uses GitHub read-only ingestion and preserves provenance for every chunk.",
            path="docs/ARCHITECTURE.md",
            index=0,
        ),
        _chunk(
            "The private API binds to loopback by default and does not require a paid LLM API.",
            path="docs/SECURITY.md",
            index=1,
        ),
    )
    data_context, citations = build_data_context(chunks)
    generation = model.generate(
        GenerationRequest(
            system_prompt="Answer only from DATA and cite every source used.",
            user_message="What safety properties are documented?",
            data_context=data_context,
        )
    )
    grounded = evaluate_grounding(generation.text, citations)

    no_evidence = model.generate(
        GenerationRequest(
            system_prompt="Answer only from DATA and cite every source used.",
            user_message="What is the production revenue today?",
            data_context="",
        )
    )
    abstention = evaluate_grounding(no_evidence.text, [])

    conflicting_citations = (
        {
            "label": "S1",
            "repository": "tukemen-rgb/sidra-ai",
            "path": "docs/POLICY.md",
            "commit_sha": "1" * 40,
        },
        {
            "label": "S2",
            "repository": "tukemen-rgb/sidra-ai",
            "path": "docs/POLICY.md",
            "commit_sha": "2" * 40,
        },
    )
    conflicting = evaluate_grounding(
        "The current policy allows public binding. [S1]",
        conflicting_citations,
    )
    conflict_guard_passed = (
        not conflicting.passed
        and any("multiple versions" in failure for failure in conflicting.failures)
    )

    return (
        EvalOutcome(
            case_name="rag_citation_integrity",
            passed=grounded.passed,
            detail=f"used={grounded.used_labels}; available={grounded.available_labels}",
            failures=grounded.failures,
        ),
        EvalOutcome(
            case_name="rag_no_evidence_abstention",
            passed=abstention.passed,
            detail="no evidence",
            failures=abstention.failures,
        ),
        EvalOutcome(
            case_name="rag_conflicting_source_versions_fail_closed",
            passed=conflict_guard_passed,
            detail="same repository/path at two commit SHAs must force abstention",
            failures=() if conflict_guard_passed else conflicting.failures,
        ),
    )
