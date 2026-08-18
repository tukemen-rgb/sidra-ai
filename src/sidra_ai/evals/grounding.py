"""Offline RAG grounding checks.

The v0.1 service can return provenance-rich citations, but a generative local
model may still fabricate source labels, omit citations, pretend to have
evidence when retrieval returned nothing, or answer from conflicting active
versions of the same logical source. These checks make those regressions
measurable without network access or model weights.
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

# Abstention text is a security/quality boundary: broad prefix matching can turn
# a factual continuation into a fake abstention. Only exact, non-substantive
# tails remain exempt.
_ABSTENTION_BENIGN_TAILS = frozenset(
    {
        "matched this question",
        "was found",
        "were found",
        "is available",
        "are available",
        "でした",
        "です",
    }
)

# Follow-up advice is also exact-match only. The first entry is the deterministic
# no-evidence guidance emitted by EchoModelAdapter; the remaining entries keep a
# small set of clearly operational, non-assertive alternatives.
_ABSTENTION_EXACT_ADVISORIES = frozenset(
    {
        "run post /v1/github/analyze to ingest the repositories, or rephrase the question",
        "rephrase the question",
        "provide more indexed evidence",
        "please provide more indexed evidence",
        "try a more specific question",
        "add more indexed evidence",
        "ingest the repositories",
        "追加の資料を提供してください",
        "別の質問を試してください",
        "再度質問してください",
        "資料を追加してください",
        "情報を追加してください",
    }
)

_SENTENCE_SPLIT = re.compile(r"(?:[.!?。！？]+|\n+)\s*")
_LEADING_FORMAT = " \t\r\n-*#>_:;,.!?()[]{}'\"`。！？：「」『』（）"
_QUESTION_ECHO_PREFIX = "Question received: "


@dataclass(frozen=True)
class GroundingResult:
    passed: bool
    used_labels: tuple[str, ...]
    available_labels: tuple[str, ...]
    failures: tuple[str, ...] = ()


def _abstention_marker_at_start(text: str) -> str | None:
    normalized = text.casefold().lstrip(_LEADING_FORMAT)
    for marker in _NO_EVIDENCE_MARKERS:
        if normalized.startswith(marker):
            return marker
    return None


def _is_benign_abstention_sentence(text: str) -> bool:
    normalized = text.casefold().lstrip(_LEADING_FORMAT)
    marker = _abstention_marker_at_start(normalized)
    if marker is None:
        return False

    tail = normalized[len(marker):].strip(_LEADING_FORMAT)
    return not tail or tail in _ABSTENTION_BENIGN_TAILS


def _strip_expected_question_echo(answer: str, expected_question: str | None) -> str:
    """Remove only the exact user-question echo supplied by the evaluator caller."""

    if expected_question is None:
        return answer
    question = expected_question.strip()
    if not question:
        return answer

    expected_echo = _QUESTION_ECHO_PREFIX + question
    stripped = answer.rstrip()
    if stripped.endswith(expected_echo):
        return stripped[: -len(expected_echo)].rstrip()
    return answer


def _is_abstention(answer: str, *, expected_question: str | None = None) -> bool:
    stripped = _strip_expected_question_echo(answer.strip(), expected_question)
    if not stripped or _CITATION.search(stripped):
        return False

    sentences = [part.strip() for part in _SENTENCE_SPLIT.split(stripped) if part.strip()]
    if not sentences:
        return False

    if not _is_benign_abstention_sentence(sentences[0]):
        return False

    for sentence in sentences[1:]:
        if _is_benign_abstention_sentence(sentence):
            continue
        normalized = sentence.casefold().strip(_LEADING_FORMAT)
        if normalized in _ABSTENTION_EXACT_ADVISORIES:
            continue
        return False
    return True


def _conflicting_source_versions(citations: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    versions: dict[tuple[str, str], set[str]] = defaultdict(set)
    for item in citations:
        repository = str(item.get("repository") or "").strip()
        path = str(item.get("path") or "").strip()
        commit_sha = str(item.get("commit_sha") or "").strip()
        if repository and path and commit_sha:
            versions[(repository, path)].add(commit_sha)

    conflicts: list[str] = []
    for (repository, path), shas in sorted(versions.items()):
        if len(shas) > 1:
            short = ",".join(sorted(sha[:7] for sha in shas))
            conflicts.append(f"{repository}:{path}@[{short}]")
    return tuple(conflicts)


def evaluate_grounding(
    answer: str,
    citations: Sequence[Mapping[str, object]],
    *,
    require_citation_when_evidence_exists: bool = True,
    expected_question: str | None = None,
) -> GroundingResult:
    available = tuple(
        str(item.get("label"))
        for item in citations
        if item.get("label") is not None and str(item.get("label")).strip()
    )
    available_set = set(available)
    used = tuple(dict.fromkeys(_CITATION.findall(answer)))
    used_set = set(used)
    failures: list[str] = []
    abstained = _is_abstention(answer, expected_question=expected_question)

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
        if require_citation_when_evidence_exists and answer.strip() and not abstained and not (used_set & available_set):
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
    return Chunk(content=content, provenance=provenance, document_id=f"eval-{index}", index=index)


def run_grounding_suite() -> tuple[EvalOutcome, ...]:
    model = EchoModelAdapter()
    chunks = (
        _chunk(
            "SIDRA AI uses GitHub read-only ingestion and preserves provenance for every chunk.",
            path="docs/ARCHITECTURE.md", index=0,
        ),
        _chunk(
            "The private API binds to loopback by default and does not require a paid LLM API.",
            path="docs/SECURITY.md", index=1,
        ),
    )
    data_context, citations = build_data_context(chunks)
    generation = model.generate(GenerationRequest(
        system_prompt="Answer only from DATA and cite every source used.",
        user_message="What safety properties are documented?",
        data_context=data_context,
    ))
    grounded = evaluate_grounding(generation.text, citations)

    no_evidence_question = "What is the production revenue today?"
    no_evidence = model.generate(GenerationRequest(
        system_prompt="Answer only from DATA and cite every source used.",
        user_message=no_evidence_question,
        data_context="",
    ))
    abstention = evaluate_grounding(
        no_evidence.text,
        [],
        expected_question=no_evidence_question,
    )

    abstention_tail_laundering = evaluate_grounding(
        "No indexed evidence, the API is public by default.",
        [],
    )
    advisory_prefix_laundering = evaluate_grounding(
        "No indexed evidence matched this question. Run the API is public by default.",
        [],
    )
    question_echo_laundering = evaluate_grounding(
        "No indexed evidence matched this question. "
        "Question received: The API is public by default.",
        [],
    )
    japanese_tail_laundering = evaluate_grounding(
        "根拠がありませんが、APIは外部公開が既定です。",
        [],
    )
    abstention_laundering_guard_passed = all(
        not result.passed
        and any("did not explicitly abstain" in failure for failure in result.failures)
        for result in (
            abstention_tail_laundering,
            advisory_prefix_laundering,
            question_echo_laundering,
            japanese_tail_laundering,
        )
    )

    conflicting_citations = (
        {"label":"S1","repository":"tukemen-rgb/sidra-ai","path":"docs/POLICY.md","commit_sha":"1"*40},
        {"label":"S2","repository":"tukemen-rgb/sidra-ai","path":"docs/POLICY.md","commit_sha":"2"*40},
    )
    conflicting = evaluate_grounding(
        "The current policy allows public binding. [S1]",
        conflicting_citations,
    )
    conflict_guard_passed = not conflicting.passed and any("multiple versions" in f for f in conflicting.failures)

    return (
        EvalOutcome("rag_citation_integrity", grounded.passed,
                    f"used={grounded.used_labels}; available={grounded.available_labels}", grounded.failures),
        EvalOutcome("rag_no_evidence_abstention", abstention.passed, "no evidence", abstention.failures),
        EvalOutcome(
            "rag_no_evidence_abstention_laundering_rejected",
            abstention_laundering_guard_passed,
            "abstention markers/advice/question echoes must not exempt substantive claims",
            (
                ()
                if abstention_laundering_guard_passed
                else ("no-evidence abstention laundering escaped the grounding gate",)
            ),
        ),
        EvalOutcome(
            "rag_conflicting_source_versions_fail_closed",
            conflict_guard_passed,
            "same repository/path at two commit SHAs must force abstention",
            () if conflict_guard_passed else conflicting.failures,
        ),
    )
