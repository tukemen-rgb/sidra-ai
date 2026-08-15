"""Deterministic citation-local policy-polarity regressions.

Exact-literal grounding catches fabricated concrete values, but a model can still
reverse the meaning of a cited policy without inventing any literal. Examples
include "GitHub write is enabled" cited to evidence that says read-only, or
"paid external LLM API is required" cited to evidence that says the opposite.

This module intentionally covers only a small set of security/cost invariants
where high-precision phrase matching is preferable to a heavyweight judge
model. It is a regression floor, not general semantic entailment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from sidra_ai.evals.cases import EvalOutcome

_CITATION = re.compile(r"\[(S\d+)\]")
_TRAILING_CITATIONS = re.compile(r"([.!?。！？])\s*((?:\[(?:S\d+)\]\s*)+)")
_CLAIM_SPLIT = re.compile(r"(?<=[。！？])|(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class _PolicyRule:
    name: str
    positive: tuple[re.Pattern[str], ...]
    negative: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class PolicyPolarityResult:
    passed: bool
    checked_claims: int
    failures: tuple[str, ...] = ()


def _patterns(*values: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(value, re.IGNORECASE) for value in values)


_RULES = (
    _PolicyRule(
        name="github_write",
        negative=_patterns(
            r"github.{0,40}read[- ]only",
            r"github.{0,40}読み取り専用",
            r"\bno\b.{0,30}github.{0,30}(?:write|mutation)",
            r"github.{0,30}(?:write|mutation).{0,25}(?:disabled|forbidden|not allowed|cannot|can't)",
            r"github.{0,30}書き込み.{0,25}(?:不可|禁止|無効|できない)",
        ),
        positive=_patterns(
            r"github.{0,30}(?:write|mutation).{0,25}(?:enabled|allowed|available|supported|possible|can\b)",
            r"github.{0,30}書き込み.{0,25}(?:可能|許可|有効|できる)",
        ),
    ),
    _PolicyRule(
        name="public_bind",
        negative=_patterns(
            r"(?:public\s+(?:bind|binding)|公開(?:バインド|接続)|外部公開).{0,30}(?:disabled|forbidden|not allowed|cannot|can't|禁止|不可|無効|できない)",
            r"(?:loopback|localhost|127\.0\.0\.1).{0,25}(?:only|default|既定|デフォルト|のみ)",
            r"0\.0\.0\.0.{0,25}(?:disabled|forbidden|not allowed|禁止|不可|無効)",
        ),
        positive=_patterns(
            r"(?:public\s+(?:bind|binding)|公開(?:バインド|接続)|外部公開).{0,30}(?:enabled|allowed|available|supported|possible|default|許可|可能|有効|デフォルト)",
            r"(?:binds?|listen(?:s|ing)?).{0,20}0\.0\.0\.0",
        ),
    ),
    _PolicyRule(
        name="paid_external_llm_api",
        negative=_patterns(
            r"(?:\bno\b|\bnot\b|\bwithout\b|\bdoes\s+not\b|\bdo\s+not\b).{0,30}(?:paid|external).{0,25}(?:llm\s*)?api",
            r"(?:paid|external).{0,25}(?:llm\s*)?api.{0,25}(?:not required|unnecessary|disabled|forbidden)",
            r"(?:有料|外部).{0,20}(?:llm)?api.{0,25}(?:不要|必須ではない|必要ない|使用しない|使わない|禁止)",
            r"(?:外部|有料).{0,20}(?:llm)?api.{0,20}依存(?:なし|ゼロ|0)",
        ),
        positive=_patterns(
            r"(?:paid|external).{0,25}(?:llm\s*)?api.{0,25}(?:required|enabled|used|needed|mandatory)",
            r"(?:requires?|uses?|depends?\s+on).{0,25}(?:paid|external).{0,25}(?:llm\s*)?api",
            r"(?:有料|外部).{0,20}(?:llm)?api.{0,25}(?:必要|必須|使用|有効)",
        ),
    ),
)


def _claim_units(answer: str) -> tuple[str, ...]:
    normalized = _TRAILING_CITATIONS.sub(
        lambda match: f" {match.group(2).strip()}{match.group(1)} ",
        answer.strip(),
    )
    return tuple(
        part.strip()
        for part in _CLAIM_SPLIT.split(normalized)
        if part.strip()
    )


def _polarity(text: str, rule: _PolicyRule) -> int | None:
    """Return -1/1 only for a high-confidence matched policy polarity."""

    if any(pattern.search(text) for pattern in rule.negative):
        return -1
    if any(pattern.search(text) for pattern in rule.positive):
        return 1
    return None


def evaluate_policy_polarity(
    answer: str,
    evidence_by_label: Mapping[str, str],
) -> PolicyPolarityResult:
    """Reject citation-local reversals of selected security/cost policies.

    Only claim sentences that contain a citation and match a high-confidence
    positive/negative rule are checked. If the cited evidence does not express a
    recognized polarity for that same rule, this evaluator stays neutral rather
    than guessing. Missing citations remain the grounding evaluator's job.
    """

    failures: list[str] = []
    checked = 0

    for claim in _claim_units(answer):
        labels = tuple(dict.fromkeys(_CITATION.findall(claim)))
        if not labels:
            continue
        evidence = "\n".join(
            str(evidence_by_label.get(label, ""))
            for label in labels
            if label in evidence_by_label
        )
        if not evidence:
            continue

        for rule in _RULES:
            claim_polarity = _polarity(claim, rule)
            if claim_polarity is None:
                continue
            evidence_polarity = _polarity(evidence, rule)
            if evidence_polarity is None:
                continue

            checked += 1
            if claim_polarity != evidence_polarity:
                failures.append(
                    f"{rule.name} policy polarity contradicts locally cited evidence"
                )

    return PolicyPolarityResult(
        passed=not failures,
        checked_claims=checked,
        failures=tuple(failures),
    )


def run_policy_polarity_suite() -> tuple[EvalOutcome, ...]:
    evidence = {
        "S1": "GitHub access is read-only and no GitHub write capability exists.",
        "S2": "The API is loopback-only by default. Public binding is not allowed by default.",
        "S3": "No paid external LLM API is required for normal operation.",
    }

    supported = evaluate_policy_polarity(
        "GitHub write capability is disabled. [S1]",
        evidence,
    )
    reversed_write = evaluate_policy_polarity(
        "GitHub write capability is enabled. [S1]",
        evidence,
    )
    reversed_bind = evaluate_policy_polarity(
        "Public binding is allowed by default. [S2]",
        evidence,
    )
    reversed_cost = evaluate_policy_polarity(
        "External paid LLM API is required. [S3]",
        evidence,
    )
    japanese_reversal = evaluate_policy_polarity(
        "GitHub書き込みは可能です。[S1]",
        evidence,
    )

    failures: list[str] = []
    if not supported.passed:
        failures.append("supported read-only policy was rejected")
    if reversed_write.passed:
        failures.append("reversed GitHub write policy escaped citation-local polarity check")
    if reversed_bind.passed:
        failures.append("reversed public-bind policy escaped citation-local polarity check")
    if reversed_cost.passed:
        failures.append("reversed paid-API policy escaped citation-local polarity check")
    if japanese_reversal.passed:
        failures.append("Japanese reversed GitHub write policy escaped polarity check")

    return (
        EvalOutcome(
            case_name="rag_policy_polarity_support",
            passed=not failures,
            detail=(
                "security/cost policy claims must not reverse the polarity of "
                "their locally cited evidence"
            ),
            failures=tuple(failures),
        ),
    )
