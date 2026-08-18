from __future__ import annotations

from sidra_ai.evals.claim_coverage import (
    evaluate_claim_citation_coverage,
    run_claim_citation_coverage_suite,
)

_CITATIONS = (
    {"label": "S1", "citation": "repo@aaaaaaa:docs/ARCHITECTURE.md"},
    {"label": "S2", "citation": "repo@aaaaaaa:docs/SECURITY.md"},
)


def test_abstention_prefix_does_not_launder_uncited_english_claim() -> None:
    result = evaluate_claim_citation_coverage(
        "GitHub access is read-only [S1]. "
        "No indexed evidence, the API is public by default.",
        _CITATIONS,
    )

    assert result.passed is False
    assert any("API is public" in sentence for sentence in result.uncited_sentences)


def test_benign_looking_preposition_cannot_extend_abstention_exemption() -> None:
    result = evaluate_claim_citation_coverage(
        "GitHub access is read-only [S1]. "
        "No indexed evidence for this question, but the API is public by default.",
        _CITATIONS,
    )

    assert result.passed is False
    assert any("API is public" in sentence for sentence in result.uncited_sentences)


def test_about_preposition_cannot_extend_abstention_exemption() -> None:
    result = evaluate_claim_citation_coverage(
        "GitHub access is read-only [S1]. "
        "No indexed evidence about this request; the API is public by default.",
        _CITATIONS,
    )

    assert result.passed is False
    assert any("API is public" in sentence for sentence in result.uncited_sentences)


def test_abstention_prefix_does_not_launder_uncited_japanese_claim() -> None:
    result = evaluate_claim_citation_coverage(
        "GitHubは読み取り専用です[S1]。"
        "根拠がありませんが、APIは外部公開が既定です。",
        _CITATIONS,
    )

    assert result.passed is False
    assert any("外部公開" in sentence for sentence in result.uncited_sentences)


def test_exact_benign_no_evidence_tail_remains_nonclaim() -> None:
    result = evaluate_claim_citation_coverage(
        "GitHub access is read-only [S1]. "
        "No indexed evidence matched this question.",
        _CITATIONS,
    )

    assert result.passed is True, result.failures


def test_exact_japanese_benign_tail_remains_nonclaim() -> None:
    result = evaluate_claim_citation_coverage(
        "GitHubは読み取り専用です[S1]。"
        "根拠がありませんでした。",
        _CITATIONS,
    )

    assert result.passed is True, result.failures


def test_release_suite_contains_abstention_prefix_guard() -> None:
    outcomes = run_claim_citation_coverage_suite()
    matching = [
        outcome
        for outcome in outcomes
        if outcome.case_name == "rag_abstention_prefix_claim_laundering_rejected"
    ]

    assert len(matching) == 1
    assert matching[0].passed is True, matching[0].failures
