from __future__ import annotations

from sidra_ai.evals.grounding import evaluate_grounding, run_grounding_suite


def test_no_evidence_marker_cannot_launder_same_sentence_claim() -> None:
    result = evaluate_grounding(
        "No indexed evidence, the API is public by default.",
        [],
    )

    assert result.passed is False
    assert any("did not explicitly abstain" in failure for failure in result.failures)


def test_operational_advisory_prefix_cannot_launder_claim() -> None:
    result = evaluate_grounding(
        "No indexed evidence matched this question. "
        "Run the API is public by default.",
        [],
    )

    assert result.passed is False
    assert any("did not explicitly abstain" in failure for failure in result.failures)


def test_question_received_prefix_is_not_trusted_without_expected_question() -> None:
    result = evaluate_grounding(
        "No indexed evidence matched this question. "
        "Question received: The API is public by default.",
        [],
    )

    assert result.passed is False
    assert any("did not explicitly abstain" in failure for failure in result.failures)


def test_exact_expected_question_echo_remains_valid_abstention() -> None:
    question = "Is production revenue indexed? If not, why?"
    answer = (
        "No indexed evidence matched this question. "
        "Run POST /v1/github/analyze to ingest the repositories, or rephrase the question.\n\n"
        f"Question received: {question}"
    )

    result = evaluate_grounding(answer, [], expected_question=question)

    assert result.passed is True, result.failures


def test_question_echo_with_substantive_extension_is_rejected() -> None:
    question = "Is production revenue indexed?"
    result = evaluate_grounding(
        "No indexed evidence matched this question. "
        f"Question received: {question} The API is public by default.",
        [],
        expected_question=question,
    )

    assert result.passed is False
    assert any("did not explicitly abstain" in failure for failure in result.failures)


def test_japanese_abstention_tail_cannot_launder_claim() -> None:
    result = evaluate_grounding(
        "根拠がありませんが、APIは外部公開が既定です。",
        [],
    )

    assert result.passed is False
    assert any("did not explicitly abstain" in failure for failure in result.failures)


def test_release_suite_contains_no_evidence_laundering_guard() -> None:
    outcomes = run_grounding_suite()
    by_name = {outcome.case_name: outcome for outcome in outcomes}

    assert by_name["rag_no_evidence_abstention_laundering_rejected"].passed is True
