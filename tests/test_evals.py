"""The eval suite must pass, and must keep covering every required family."""

from __future__ import annotations

from sidra_ai.evals.cases import GATE_CASES
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
