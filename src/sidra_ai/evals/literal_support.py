"""Deterministic exact-literal grounding checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from sidra_ai.evals.cases import EvalOutcome

_CITATION = re.compile(r"\[(S\d+)\]")
_LITERAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![A-Za-z0-9_])(?:\d{1,3}\.){3}\d{1,3}(?::\d{2,5})?(?![A-Za-z0-9_])"),
    re.compile(r"(?<![A-Za-z0-9_])localhost:\d{2,5}(?![A-Za-z0-9_])", re.IGNORECASE),
    re.compile(r"https?://[^\s\]\[<>]+", re.IGNORECASE),
    re.compile(r"(?<![0-9])\d{4}-\d{2}-\d{2}(?![0-9])"),
    re.compile(r"(?<![A-Za-z0-9_.])\d+(?:\.\d+)?%(?![A-Za-z0-9_])"),
    re.compile(r"(?:[$¥￥]\s?\d[\d,]*(?:\.\d+)?)"),
    re.compile(r"(?<![A-Za-z0-9_])\d+/\d+(?![A-Za-z0-9_])"),
    re.compile(r"(?<![A-Za-z0-9_.])v?\d+\.\d+(?:\.\d+)?(?![A-Za-z0-9_.])", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9_])[0-9a-f]{7,40}(?![A-Za-z0-9_])", re.IGNORECASE),
    re.compile(
        r"(?<![A-Za-z0-9_./:-])\d[\d,]*\s+"
        r"(?:pull requests?|prs?|tests?|cases?|checks?|commits?|files?|"
        r"repositories?|repos?|models?|routes?|issues?|distributions?|"
        r"documents?|chunks?|sources?)(?![A-Za-z0-9_])",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![A-Za-z0-9_./:-])\d[\d,]*\s+"
        r"(?:passed|failed|errors?|warnings?|skipped|xfailed|xpassed)"
        r"(?![A-Za-z0-9_])",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![A-Za-z0-9_./:-])\d[\d,]*\s*"
        r"(?:件(?:の)?(?:テスト|ケース|チェック|コミット|ファイル|リポジトリ|"
        r"モデル|ルート|課題|ソース|ドキュメント|チャンク)|"
        r"(?:テスト|ケース|チェック|コミット|ファイル|リポジトリ|モデル|"
        r"ルート|課題|ソース|ドキュメント|チャンク))"
        r"(?![A-Za-z0-9_])"
    ),
)
_SHA_LITERAL = re.compile(r"[0-9a-f]{7,40}\Z", re.IGNORECASE)
_TRAILING_CITATIONS = re.compile(r"([.!?。！？])\s*((?:\[(?:S\d+)\]\s*)+)")
_CLAIM_SPLIT = re.compile(r"(?<=[。！？])|(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class LiteralSupportResult:
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
    normalized = _TRAILING_CITATIONS.sub(
        lambda match: f" {match.group(2).strip()}{match.group(1)} ", answer.strip()
    )
    return tuple(part.strip() for part in _CLAIM_SPLIT.split(normalized) if part.strip())


def _dedupe_casefold(values: list[str]) -> tuple[str, ...]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(value)
    return tuple(deduped)


def _literal_is_supported(literal: str, evidence_literals: tuple[str, ...]) -> bool:
    """Require a complete protected literal, not an arbitrary evidence substring.

    Git commit hashes are the one intentional prefix exception: a conventional
    7+ character short SHA may cite a longer hash from the same local evidence.
    """
    key = literal.casefold()
    evidence_keys = tuple(item.casefold() for item in evidence_literals)
    if key in evidence_keys:
        return True
    if not _SHA_LITERAL.fullmatch(key):
        return False
    return any(
        len(candidate) > len(key)
        and candidate.startswith(key)
        and _SHA_LITERAL.fullmatch(candidate)
        for candidate in evidence_keys
    )


def evaluate_literal_support(answer: str, evidence_by_label: Mapping[str, str]) -> LiteralSupportResult:
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
        )
        local_evidence_literals = _extract_literals(local_evidence)
        unsupported_list.extend(
            literal
            for literal in claim_literals
            if not _literal_is_supported(literal, local_evidence_literals)
        )

    unsupported = _dedupe_casefold(unsupported_list)
    uncited = set(_dedupe_casefold(uncited_list))
    failures: list[str] = []
    if unsupported:
        failures.append("unsupported exact literals in locally cited claims: " + ", ".join(unsupported))
    if uncited:
        failures.append(
            "protected literals appeared in claims without a local citation: "
            + ", ".join(sorted(uncited))
        )
    return LiteralSupportResult(not unsupported, literals, unsupported, tuple(failures))


def run_literal_support_suite() -> tuple[EvalOutcome, ...]:
    evidence = {
        "S1": "The private API binds to 127.0.0.1:8787 by default. The integration checkpoint is commit 902b37e.",
        "S2": "The security evaluation reports 15/15 cases passing on 2026-08-15.",
        "S3": "The exact integration gate completed with 591 tests, 57 cases, and 21 distributions.",
        "S4": "統合ゲートでは591件のテストが通過しました。",
        "S5": "Pytest completed with 591 passed, 2 skipped, and 1 warning.",
        "S6": "A private test fixture binds to 10.0.0.0:8787.",
    }
    supported = evaluate_literal_support(
        "The API binds to 127.0.0.1:8787 and checkpoint 902b37e is documented. [S1]", evidence
    )
    invented_endpoint = evaluate_literal_support("The API is available at 0.0.0.0:8787. [S1]", evidence)
    overlapping_endpoint = evaluate_literal_support(
        "The API is publicly reachable at 0.0.0.0:8787. [S6]", evidence
    )
    invented_eval_count = evaluate_literal_support(
        "The security evaluation passed 16/16 cases on 2026-08-15. [S2]", evidence
    )
    citation_laundering = evaluate_literal_support(
        "The private API binds to 15/15. [S1] The security evaluation reports checkpoint 902b37e. [S2]",
        evidence,
    )
    japanese_citation_laundering = evaluate_literal_support(
        "評価結果は15/15 [S1]。統合checkpointは902b37e [S2]。", evidence
    )
    supported_counts = evaluate_literal_support(
        "The exact integration gate completed with 591 tests, 57 cases, and 21 distributions. [S3]",
        evidence,
    )
    invented_test_count = evaluate_literal_support(
        "The exact integration gate completed with 593 tests, 57 cases, and 21 distributions. [S3]",
        evidence,
    )
    cross_metric_count_laundering = evaluate_literal_support(
        "The exact integration gate completed with 57 tests and 591 cases. [S3]", evidence
    )
    japanese_invented_test_count = evaluate_literal_support(
        "統合ゲートでは593件のテストが通過しました。[S4]", evidence
    )
    supported_ci_status_counts = evaluate_literal_support(
        "Pytest completed with 591 passed, 2 skipped, and 1 warning. [S5]", evidence
    )
    invented_ci_pass_count = evaluate_literal_support(
        "Pytest completed with 593 passed, 2 skipped, and 1 warning. [S5]", evidence
    )
    cross_status_count_laundering = evaluate_literal_support(
        "Pytest completed with 591 passed, 2 failed, and 1 warning. [S5]", evidence
    )

    failures: list[str] = []
    if not supported.passed:
        failures.append("supported literals were rejected")
    if invented_endpoint.passed or "0.0.0.0:8787" not in invented_endpoint.unsupported_literals:
        failures.append("invented endpoint escaped exact-literal grounding")
    if overlapping_endpoint.passed or "0.0.0.0:8787" not in overlapping_endpoint.unsupported_literals:
        failures.append("overlapping endpoint substring escaped exact-literal grounding")
    if invented_eval_count.passed or "16/16" not in invented_eval_count.unsupported_literals:
        failures.append("invented evaluation count escaped exact-literal grounding")
    if citation_laundering.passed:
        failures.append("cross-sentence citation laundering escaped exact-literal grounding")
    if japanese_citation_laundering.passed:
        failures.append("Japanese no-whitespace citation laundering escaped exact-literal grounding")
    if not supported_counts.passed:
        failures.append("supported repository/status counts were rejected")
    if invented_test_count.passed or "593 tests" not in invented_test_count.unsupported_literals:
        failures.append("invented ordinary test count escaped exact-literal grounding")
    if cross_metric_count_laundering.passed:
        failures.append("same-number cross-metric count laundering escaped exact-literal grounding")
    if (
        japanese_invented_test_count.passed
        or "593件のテスト" not in japanese_invented_test_count.unsupported_literals
    ):
        failures.append("Japanese invented ordinary test count escaped exact-literal grounding")
    if not supported_ci_status_counts.passed:
        failures.append("supported CI status counts were rejected")
    if invented_ci_pass_count.passed or "593 passed" not in invented_ci_pass_count.unsupported_literals:
        failures.append("invented bare CI pass count escaped exact-literal grounding")
    if cross_status_count_laundering.passed or "2 failed" not in cross_status_count_laundering.unsupported_literals:
        failures.append("same-number cross-status count laundering escaped exact-literal grounding")

    return (
        EvalOutcome(
            "rag_exact_literal_support",
            not failures,
            "cited IP/port, commit, date, fraction and repository/CI count literals must match complete same-claim evidence literals",
            tuple(failures),
        ),
    )
