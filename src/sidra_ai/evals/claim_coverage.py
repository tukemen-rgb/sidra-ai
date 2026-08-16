"""Deterministic claim-level citation coverage checks.

Citation integrity at answer level is not enough: a model can cite one supported
sentence and then append an uncited hallucination. This module adds a narrow,
offline regression floor requiring every factual sentence in a partially cited
answer to carry at least one citation label that actually exists in the retrieved
context.

It intentionally does not judge semantic entailment. Other evaluators handle
literal support and selected policy-polarity reversals. This check only closes
the mixed cited/uncited-answer gap without requiring a paid judge model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from sidra_ai.evals.cases import EvalOutcome

_CITATION = re.compile(r"\[(S\d+)\]")
_SENTENCE_SPLIT = re.compile(r"(?:[.!?。！？]+|\n+)\s*")
_MEANINGFUL_TEXT = re.compile(r"[A-Za-z0-9\u3040-\u30ff\u3400-\u9fff]")
_LEADING_FORMAT = " \t\r\n-*#>_:;,.!?()[]{}'\"`。！？：「」『』（）"

_NONCLAIM_PREFIXES = (
    "question received:",
    "cited sources:",
    "sources:",
    "source:",
    "answering from indexed repository data",
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

_TRAILING_CITATIONS = re.compile(
    r"([.!?。！？])\s*((?:\[(?:S\d+)\]\s*)+)(?=$|[A-Za-z0-9\u3040-\u30ff\u3400-\u9fff])"
)


@dataclass(frozen=True)
class ClaimCitationCoverageResult:
    passed: bool
    checked_sentences: int
    uncited_sentences: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()


def _available_labels(citations: Sequence[Mapping[str, object]]) -> set[str]:
    return {
        str(item.get("label"))
        for item in citations
        if item.get("label") is not None and str(item.get("label")).strip()
    }


def _sentences(answer: str) -> tuple[str, ...]:
    normalized = _TRAILING_CITATIONS.sub(r" \2\1 ", answer)
    return tuple(
        part.strip()
        for part in _SENTENCE_SPLIT.split(normalized)
        if part.strip()
    )


def _is_nonclaim(sentence: str) -> bool:
    without_citations = _CITATION.sub("", sentence).strip(_LEADING_FORMAT)
    if not without_citations:
        return True
    if not _MEANINGFUL_TEXT.search(without_citations):
        return True
    normalized = without_citations.casefold()
    return any(normalized.startswith(prefix) for prefix in _NONCLAIM_PREFIXES)


def evaluate_claim_citation_coverage(
    answer: str,
    citations: Sequence[Mapping[str, object]],
) -> ClaimCitationCoverageResult:
    """Require claim-local citations once an answer uses retrieved evidence."""

    available = _available_labels(citations)
    if not available or not answer.strip():
        return ClaimCitationCoverageResult(passed=True, checked_sentences=0)

    used_valid = set(_CITATION.findall(answer)) & available
    if not used_valid:
        return ClaimCitationCoverageResult(passed=True, checked_sentences=0)

    uncited: list[str] = []
    checked = 0
    for sentence in _sentences(answer):
        if _is_nonclaim(sentence):
            continue
        checked += 1
        local_labels = set(_CITATION.findall(sentence)) & available
        if not local_labels:
            uncited.append(sentence)

    failures: tuple[str, ...] = ()
    if uncited:
        failures = (
            "answer contains factual sentence(s) without a valid local citation: "
            + " | ".join(sentence[:160] for sentence in uncited),
        )

    return ClaimCitationCoverageResult(
        passed=not uncited,
        checked_sentences=checked,
        uncited_sentences=tuple(uncited),
        failures=failures,
    )


def run_claim_citation_coverage_suite() -> tuple[EvalOutcome, ...]:
    citations = (
        {"label": "S1", "citation": "repo@aaaaaaa:docs/ARCHITECTURE.md"},
        {"label": "S2", "citation": "repo@aaaaaaa:docs/SECURITY.md"},
    )

    supported = evaluate_claim_citation_coverage(
        "GitHub access is read-only [S1]. The API binds to loopback by default [S2].",
        citations,
    )
    partial = evaluate_claim_citation_coverage(
        "GitHub access is read-only [S1]. The API is public by default.",
        citations,
    )
    japanese_partial = evaluate_claim_citation_coverage(
        "GitHubは読み取り専用です[S1]。APIは公開バインドが既定です。",
        citations,
    )

    partial_guard_passed = (
        not partial.passed
        and bool(partial.uncited_sentences)
        and any("API is public" in sentence for sentence in partial.uncited_sentences)
    )
    japanese_guard_passed = (
        not japanese_partial.passed
        and bool(japanese_partial.uncited_sentences)
        and any("公開バインド" in sentence for sentence in japanese_partial.uncited_sentences)
    )

    return (
        EvalOutcome(
            case_name="rag_claim_local_citations_supported",
            passed=supported.passed,
            detail=f"checked_sentences={supported.checked_sentences}",
            failures=supported.failures,
        ),
        EvalOutcome(
            case_name="rag_partial_citation_hallucination_rejected",
            passed=partial_guard_passed,
            detail="cited first sentence must not cover an uncited second claim",
            failures=() if partial_guard_passed else partial.failures,
        ),
        EvalOutcome(
            case_name="rag_japanese_partial_citation_hallucination_rejected",
            passed=japanese_guard_passed,
            detail="Japanese sentence boundary without whitespace remains claim-local",
            failures=() if japanese_guard_passed else japanese_partial.failures,
        ),
    )
