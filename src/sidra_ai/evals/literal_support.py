"""Deterministic exact-literal grounding checks.

Citation-label integrity is necessary but not sufficient: a model can cite a real
source while inventing a concrete value such as an IP address, port, date,
percentage, currency amount, version, or commit SHA. Those values are especially
risky because operators tend to treat them as executable facts.

This module provides a conservative offline regression floor. It does not try to
judge semantic entailment. It only rejects protected exact literals that appear
in an answer but nowhere in the evidence attached to the labels the answer cited.
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
    re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b", re.IGNORECASE),
    re.compile(r"\b[0-9a-f]{7,40}\b", re.IGNORECASE),
)


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


def evaluate_literal_support(
    answer: str,
    evidence_by_label: Mapping[str, str],
) -> LiteralSupportResult:
    """Reject protected literals absent from the answer's cited evidence.

    Only evidence for labels actually cited in ``answer`` is considered. If the
    answer contains no citations, this evaluator is intentionally neutral; the
    main grounding evaluator owns missing/invented-citation failures.
    """

    used_labels = tuple(dict.fromkeys(_CITATION.findall(answer)))
    literals = _extract_literals(answer)
    if not used_labels or not literals:
        return LiteralSupportResult(passed=True, checked_literals=literals)

    cited_evidence = "\n".join(
        str(evidence_by_label.get(label, ""))
        for label in used_labels
        if label in evidence_by_label
    ).casefold()

    unsupported = tuple(
        literal
        for literal in literals
        if literal.casefold() not in cited_evidence
    )
    failures = (
        ("unsupported exact literals in cited answer: " + ", ".join(unsupported),)
        if unsupported
        else ()
    )
    return LiteralSupportResult(
        passed=not unsupported,
        checked_literals=literals,
        unsupported_literals=unsupported,
        failures=failures,
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

    failures: list[str] = []
    if not supported.passed:
        failures.append("supported literals were rejected")
    if invented_endpoint.passed or "0.0.0.0:8787" not in invented_endpoint.unsupported_literals:
        failures.append("invented endpoint escaped exact-literal grounding")
    if invented_eval_count.passed or "16/16" not in invented_eval_count.unsupported_literals:
        failures.append("invented evaluation count escaped exact-literal grounding")

    return (
        EvalOutcome(
            case_name="rag_exact_literal_support",
            passed=not failures,
            detail="cited IP/port, commit, date, and fraction literals must exist in cited evidence",
            failures=tuple(failures),
        ),
    )
