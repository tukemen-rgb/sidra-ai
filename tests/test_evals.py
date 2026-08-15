"""The eval suite must pass, and must keep covering every required family."""

from __future__ import annotations

from sidra_ai.evals.cases import GATE_CASES
from sidra_ai.evals.grounding import evaluate_grounding
from sidra_ai.evals.literal_support import evaluate_literal_support
from sidra_ai.evals.retrieval_quality import RETRIEVAL_CASES, evaluate_retrieval_quality
from sidra_ai.evals.runner import run_all
from sidra_ai.security.decisions import FindingCategory


def test_all_gate_evals_pass() -> None:
    report = run_all()
    assert report.ok, report.to_dict()["failures"]


def test_every_required_detector_family_has_a_case() -> None:
    covered = {
        category
        for case in GATE_CASES
        for category in case.expected_categories
    }
    required = {
        FindingCategory.SECRET,
        FindingCategory.PII,
        FindingCategory.PROMPT_INJECTION,
        FindingCategory.OVERSIZED_INPUT,
        FindingCategory.UNPERMITTED_SOURCE,
    }
    assert required <= covered, f"eval suite lost coverage of {required - covered}"


def test_eval_suite_includes_negative_cases() -> None:
    """Without these the gate could pass by blocking everything."""

    from sidra_ai.security.decisions import Decision

    allow_cases = [c for c in GATE_CASES if c.expected_decision is Decision.ALLOW]
    assert len(allow_cases) >= 3


def test_runner_reports_failures_with_detail() -> None:
    from sidra_ai.evals.cases import GateCase
    from sidra_ai.evals.runner import run_gate_case
    from sidra_ai.security.decisions import Decision

    impossible = GateCase(
        name="deliberately_failing",
        content="ordinary text",
        expected_decision=Decision.BLOCK,
    )
    outcome = run_gate_case(impossible)
    assert outcome.passed is False
    assert outcome.failures


def test_eval_cases_contain_no_real_credentials() -> None:
    """The suite must not be the thing that leaks a key."""

    import re
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "sidra_ai" / "evals" / "cases.py"
    ).read_text(encoding="utf-8")

    # Every synthetic credential is built by repetition, never pasted whole.
    for match in re.finditer(r'"(gh[pousr]_|sk-ant-|AKIA)[A-Za-z0-9]{12,}"', source):
        raise AssertionError(f"literal credential-shaped string in evals: {match.group()[:12]}...")


def test_multilingual_retrieval_quality_regression_passes() -> None:
    result = evaluate_retrieval_quality()
    assert result.passed, result.failures
    assert result.mean_reciprocal_rank == 1.0
    assert result.recall_at_3 == 1.0


def test_retrieval_eval_covers_japanese_english_and_no_evidence() -> None:
    queries = [case.query for case in RETRIEVAL_CASES]
    assert any("GitHub write" in query for query in queries)
    assert any("差分取得" in query for query in queries)
    assert any(case.expected_path is None for case in RETRIEVAL_CASES)


def test_grounding_rejects_conflicting_versions_of_same_source() -> None:
    citations = [
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
    ]

    result = evaluate_grounding(
        "The current policy allows public binding. [S1]",
        citations,
    )

    assert result.passed is False
    assert any("multiple versions" in failure for failure in result.failures)


def test_grounding_allows_abstention_when_versions_conflict() -> None:
    citations = [
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
    ]

    result = evaluate_grounding("十分な根拠がありません", citations)

    assert result.passed is True, result.failures


def test_grounding_rejects_claim_before_abstention_phrase() -> None:
    result = evaluate_grounding(
        "The answer is definitely 42. There is insufficient evidence.",
        [],
    )

    assert result.passed is False
    assert any("did not explicitly abstain" in failure for failure in result.failures)


def test_grounding_rejects_hedged_claim_when_versions_conflict() -> None:
    citations = [
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
    ]

    result = evaluate_grounding(
        "Insufficient evidence, but the current policy allows public binding. [S1]",
        citations,
    )

    assert result.passed is False
    assert any("multiple versions" in failure for failure in result.failures)


def test_grounding_keeps_clear_operational_abstention_valid() -> None:
    result = evaluate_grounding(
        "No indexed evidence matched this question. Rephrase the question.",
        [],
    )

    assert result.passed is True, result.failures


def test_literal_grounding_rejects_invented_endpoint_with_real_citation() -> None:
    result = evaluate_literal_support(
        "The private API binds to 0.0.0.0:8787. [S1]",
        {"S1": "The private API binds to 127.0.0.1:8787 by default."},
    )

    assert result.passed is False
    assert "0.0.0.0:8787" in result.unsupported_literals


def test_literal_grounding_accepts_exact_values_present_in_cited_evidence() -> None:
    result = evaluate_literal_support(
        "Checkpoint 902b37e and 15/15 evals are documented. [S1]",
        {"S1": "Checkpoint 902b37e reports 15/15 evals passing."},
    )

    assert result.passed is True, result.failures
