"""Regression coverage for citation-local repository and CI count grounding."""

from sidra_ai.evals.literal_support import evaluate_literal_support


def test_invented_test_count_is_not_supported_by_other_exact_counts() -> None:
    evidence = {
        "S1": "The exact integration gate completed with 591 tests, 57 cases, and 21 distributions."
    }

    result = evaluate_literal_support(
        "The exact integration gate completed with 593 tests, 57 cases, and 21 distributions. [S1]",
        evidence,
    )

    assert not result.passed
    assert "593 tests" in result.unsupported_literals


def test_same_number_for_different_metric_cannot_launder_count() -> None:
    evidence = {"S1": "The run covered 57 cases and 591 tests."}

    result = evaluate_literal_support(
        "The run covered 57 tests and 591 cases. [S1]",
        evidence,
    )

    assert not result.passed
    assert "57 tests" in result.unsupported_literals
    assert "591 cases" in result.unsupported_literals


def test_supported_english_repository_counts_remain_allowed() -> None:
    evidence = {
        "S1": "The gate completed with 1,024 tests, 4 files, and 21 distributions."
    }

    result = evaluate_literal_support(
        "The gate completed with 1,024 tests, 4 files, and 21 distributions. [S1]",
        evidence,
    )

    assert result.passed
    assert "1,024 tests" in result.checked_literals
    assert "4 files" in result.checked_literals
    assert "21 distributions" in result.checked_literals


def test_japanese_invented_test_count_is_rejected() -> None:
    evidence = {"S1": "統合ゲートでは591件のテストが通過しました。"}

    result = evaluate_literal_support(
        "統合ゲートでは593件のテストが通過しました。[S1]",
        evidence,
    )

    assert not result.passed
    assert "593件のテスト" in result.unsupported_literals


def test_invented_bare_pytest_pass_count_is_rejected() -> None:
    evidence = {"S1": "Pytest completed with 595 passed, 2 skipped, and 1 warning."}

    result = evaluate_literal_support(
        "Pytest completed with 596 passed, 2 skipped, and 1 warning. [S1]",
        evidence,
    )

    assert not result.passed
    assert "596 passed" in result.unsupported_literals


def test_same_number_for_different_ci_status_cannot_launder_count() -> None:
    evidence = {"S1": "Pytest completed with 595 passed and 2 skipped."}

    result = evaluate_literal_support(
        "Pytest completed with 595 passed and 2 failed. [S1]",
        evidence,
    )

    assert not result.passed
    assert "2 failed" in result.unsupported_literals


def test_supported_ci_status_counts_remain_allowed() -> None:
    evidence = {
        "S1": "Pytest completed with 595 passed, 2 skipped, 1 warning, and 0 errors."
    }

    result = evaluate_literal_support(
        "Pytest completed with 595 passed, 2 skipped, 1 warning, and 0 errors. [S1]",
        evidence,
    )

    assert result.passed
    assert "595 passed" in result.checked_literals
    assert "2 skipped" in result.checked_literals
    assert "1 warning" in result.checked_literals
    assert "0 errors" in result.checked_literals
