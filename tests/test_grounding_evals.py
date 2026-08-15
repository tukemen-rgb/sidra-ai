"""RAG grounding regressions: citations must come from retrieved evidence."""

from __future__ import annotations

from sidra_ai.evals.grounding import evaluate_grounding, run_grounding_suite


def _citations(*labels: str) -> list[dict[str, str]]:
    return [{"label": label, "citation": f"repo@aaaaaaa:{label}.md"} for label in labels]


def test_grounding_suite_passes_offline() -> None:
    outcomes = run_grounding_suite()
    assert outcomes
    assert all(outcome.passed for outcome in outcomes), [
        outcome.failures for outcome in outcomes if not outcome.passed
    ]


def test_valid_retrieved_citation_passes() -> None:
    result = evaluate_grounding("The API is local by default [S1].", _citations("S1", "S2"))
    assert result.passed
    assert result.used_labels == ("S1",)


def test_fabricated_citation_label_fails() -> None:
    result = evaluate_grounding(
        "The repository says this is approved [S99].",
        _citations("S1", "S2"),
    )
    assert not result.passed
    assert any("invented citation" in failure for failure in result.failures)


def test_answer_with_evidence_but_no_citation_fails() -> None:
    result = evaluate_grounding(
        "The API is local by default.",
        _citations("S1"),
    )
    assert not result.passed
    assert any("cited none" in failure for failure in result.failures)


def test_no_evidence_must_abstain() -> None:
    grounded = evaluate_grounding("No indexed evidence matched this question.", [])
    assert grounded.passed

    hallucinated = evaluate_grounding("The answer is definitely 42.", [])
    assert not hallucinated.passed
    assert any("did not explicitly abstain" in failure for failure in hallucinated.failures)


def test_no_evidence_cannot_invent_a_source() -> None:
    result = evaluate_grounding("No indexed evidence, but perhaps [S1].", [])
    assert not result.passed
    assert any("retrieval returned no evidence" in failure for failure in result.failures)


def test_duplicate_citation_labels_are_normalized() -> None:
    result = evaluate_grounding("Supported [S1], repeated [S1].", _citations("S1"))
    assert result.passed
    assert result.used_labels == ("S1",)
