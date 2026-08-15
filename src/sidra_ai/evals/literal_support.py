"""Deterministic exact-literal grounding checks.

Citation-label integrity is necessary but not sufficient: a model can cite a real
source while inventing a concrete value such as an IP address, port, date,
percentage, currency amount, version, or commit SHA. Those values are especially
risky because operators tend to treat them as executable facts.

This module provides a conservative offline regression floor. It does not try to
judge semantic entailment. It rejects protected exact literals that are absent
from the evidence cited by the same claim sentence, so a model cannot launder a
value through an unrelated citation elsewhere in the answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from sidra_ai.evals.cases import EvalOutcome

_CITATION = re.compile(r"\[(S\d+)\]")
_LITERAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d{2,5})?\b"),
    re.compile(r"\blocalhost:\d{2,5}\b", re.IGNORECASE),
    re.compile(r"https?://[^\s\]\[<>]+", re.IGNORECASE),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"(?<![\w.])\d+(?:\.\d+)?%(?!\w)"),
    re.compile(r"(?:[$¥￥]\s?\d[\d,]*(?:\.\d+)?)"),
    re.compile(r"\b\d+/\d+\b"),
    re.compile(r"(?<![\w.])v?\d+\.\d+(?:\.\d+)?(?![\w.])", re.IGNORECASE),
    re.compile(r"\b[0-9a-f]{7,40}\b", re.IGNORECASE),
)
_TRAILING_CITATIONS = re.compile(r"([.!?。！？])\s*((?:\[(?:S\d+)\]\s*)+)")
# Japanese prose commonly has no whitespace after 。！？. Split zero-width after
# those terminators so two adjacent Japanese claim sentences cannot pool their
# citations. Western punctuation still requires whitespace to avoid splitting
# decimals and dotted identifiers such as 3.14 or 127.0.0.1.
_CLAIM_SPLIT = re.compile(r"(?<=[。！？])|(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class LiteralSupportResult:
    """Verdict for exact literals in a citation-bearing answer."""

    passed: bool
    checked_literals: tuple[str, ...]
    unsupported_literals: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()


def _extract_literals(text: str) -> tuple[str, ...]:
    found: list[str] = []
    seen: set[str] = set()
    for pattern in _LITERAL_PATTERNS:
        for match in pattern.finditer(text):
            literal = match.group(0).rstrip(".,;:!?)]}\"'")
            key = literal.casefold()
            if literal and key not in seen:
                seen.add(key)
                found.append(literal)
    return tuple(found)


def _claim_units(answer: str) -> tuple[str, ...]:
    """Split an answer into claim-sized sentences while keeping citations local.

    Models often format citations after terminal punctuation, for example
    ``"... 127.0.0.1:8787. [S1]"``. Before splitting, move those trailing labels
    inside the preceding sentence boundary. This keeps the evaluator compatible
    with both ``claim [S1].`` and ``claim. [S1]`` without letting a citation from
    the next sentence support the previous one.

    Japanese sentence terminators are also boundaries even when followed
    immediately by the next sentence, which is standard Japanese typography.
    """

    normalized = _TRAILING_CITATIONS.sub(
        lambda match: f" {match.group(2).strip()}{match.group(1)} ",
        answer.strip(),
    )
    return tuple(
        part.strip()
        for part in _CLAIM_SPLIT.split(normalized)
        if part.strip()
    )


def _dedupe_casefold(values: list[str]) -> tuple[str, ...]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return tuple(deduped)


def evaluate_literal_support(
    answer: str,
    evidence_by_label: Mapping[str, str],
) -> LiteralSupportResult:
    """Reject protected literals absent from each claim's local cited evidence.

    Citation support is sentence-local. If an answer cites ``S1`` and ``S2`` in
    different sentences, a literal in the first sentence must exist in ``S1``;
    merely appearing in ``S2`` elsewhere in the answer is not enough. This blocks
    a citation-laundering failure where all values exist somewhere in the global
    evidence set but are attached to the wrong claims.

    If the answer contains no citations at all, this evaluator remains neutral;
    the main grounding evaluator owns the missing-citation failure. Once the
    answer cites at least one source, however, any protected literal in a claim
    without a local citation is unsupported.
    """

    used_labels = tuple(dict.fromkeys(_CITATION.findall(answer)))
    literals = _extract_literals(answer)
    if not used_labels or not literals:
        return LiteralSupportResult(passed=True, checked_literals=literals)

    unsupported_list: list[str] = []
    uncited_list: list[str] = []
    for claim in _claim_units(answer):
        claim_literals = _extract_literals(claim)
        if not claim_literals:
            continue

        local_labels = tuple(dict.fromkeys(_CITATION.findall(claim)))
        if not local_labels:
            unsupported_list.extend(claim_literals)
            uncited_list.extend(claim_literals)
            continue

        local_evidence = "\n".join(
            str(evidence_by_label.get(label, ""))
            for label in local_labels
            if label in evidence_by_label
        ).casefold()
        unsupported_list.extend(
            literal
            for literal in claim_literals
            if literal.casefold() not in local_evidence
        )

    unsupported = _dedupe_casefold(unsupported_list)
    uncited = set(_dedupe_casefold(uncited_list))
    failures: list[str] = []
    if unsupported:
        failures.append("unsupported exact literals in locally cited claims: " + ", ".join(unsupported))
    if uncited:
        failures.append("protected literals appeared in claims without a local citation: " + ", ".join(sorted(uncited)))

    return LiteralSupportResult(
        passed=not unsupported,
        checked_literals=literals,
        unsupported_literals=unsupported,
        failures=tuple(failures),
    )


def run_literal_support_suite() -> tuple[EvalOutcome, ...]:
    """Run deterministic positive/negative exact-literal grounding regressions."""

    evidence = {
        "S1": (
            "The private API binds to 127.0.0.1:8787 by default. "
            "The integration checkpoint is commit 902b37e."
        ),
        "S2": "The security evaluation reports 15/15 cases passing on 2026-08-15.",
    }

    supported = evaluate_literal_support(
        "The API binds to 127.0.0.1:8787 and checkpoint 902b37e is documented. [S1]",
        evidence,
    )
    invented_endpoint = evaluate_literal_support(
        "The API is available at 0.0.0.0:8787. [S1]",
        evidence,
    )
    invented_eval_count = evaluate_literal_support(
        "The security evaluation passed 16/16 cases on 2026-08-15. [S2]",
        evidence,
    )
    citation_laundering = evaluate_literal_support(
        (
            "The private API binds to 15/15. [S1] "
            "The security evaluation reports checkpoint 902b37e. [S2]"
        ),
        evidence,
    )
    japanese_citation_laundering = evaluate_literal_support(
        "評価結果は15/15 [S1]。統合checkpointは902b37e [S2]。",
        evidence,
    )

    failures: list[str] = []
    if not supported.passed:
        failures.append("supported literals were rejected")
    if invented_endpoint.passed or "0.0.0.0:8787" not in invented_endpoint.unsupported_literals:
        failures.append("invented endpoint escaped exact-literal grounding")
    if invented_eval_count.passed or "16/16" not in invented_eval_count.unsupported_literals:
        failures.append("invented evaluation count escaped exact-literal grounding")
    if citation_laundering.passed:
        failures.append("cross-sentence citation laundering escaped exact-literal grounding")
    if japanese_citation_laundering.passed:
        failures.append("Japanese no-whitespace citation laundering escaped exact-literal grounding")

    return (
        EvalOutcome(
            case_name="rag_exact_literal_support",
            passed=not failures,
            detail=(
                "cited IP/port, commit, date, and fraction literals must exist in "
                "the evidence cited by the same claim sentence"
            ),
            failures=tuple(failures),
        ),
    )
