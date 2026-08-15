"""Offline RAG grounding checks.

The v0.1 service can return provenance-rich citations, but a generative local
model may still fabricate source labels (for example ``[S99]``), omit citations
entirely while making factual claims, or pretend to have evidence when retrieval
returned nothing. These checks make those regressions measurable without a
network connection or model weights.

This evaluator intentionally checks *citation integrity and abstention*, not
semantic truth. Semantic entailment needs a stronger judge/model later; v0.1
must first guarantee that cited labels actually came from the retrieval context.
"""

from __future__ import annotations

import re
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
    "insufficient evidence",
    "not enough evidence",
    "根拠がありません",
    "十分な根拠がありません",
    "情報がありません",
)


@dataclass(frozen=True)
class GroundingResult:
    """Citation-level grounding verdict for one generated answer."""

    passed: bool
    used_labels: tuple[str, ...]
    available_labels: tuple[str, ...]
    failures: tuple[str, ...] = ()


def evaluate_grounding(
    answer: str,
    citations: Sequence[Mapping[str, object]],
    *,
    require_citation_when_evidence_exists: bool = True,
) -> GroundingResult:
    """Validate that an answer only cites retrieved labels and abstains safely.

    Rules:
    - every ``[S#]`` label used by the answer must exist in ``citations``;
    - when retrieval returned evidence, a non-empty answer must cite at least one
      available label (unless the caller explicitly disables this requirement);
    - when retrieval returned no evidence, the answer must not invent a source
      label and must explicitly indicate that evidence is unavailable.
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

    invented = sorted(used_set - available_set)
    if invented:
        failures.append("invented citation labels: " + ", ".join(invented))

    if available_set:
        if require_citation_when_evidence_exists and answer.strip() and not (used_set & available_set):
            failures.append("answer used retrieved evidence but cited none of the available labels")
    else:
        if used:
            failures.append("answer cited a source even though retrieval returned no evidence")
        lowered = answer.lower()
        if answer.strip() and not any(marker in lowered for marker in _NO_EVIDENCE_MARKERS):
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
    )
