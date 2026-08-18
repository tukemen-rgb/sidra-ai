"""Regression coverage for exact-literal evidence boundaries."""

from sidra_ai.evals.literal_support import evaluate_literal_support


def test_ip_literal_cannot_match_inside_a_longer_private_address() -> None:
    evidence = {"S1": "A private test fixture binds to 10.0.0.0:8787."}

    result = evaluate_literal_support(
        "The API is publicly reachable at 0.0.0.0:8787. [S1]",
        evidence,
    )

    assert not result.passed
    assert "0.0.0.0:8787" in result.unsupported_literals


def test_port_literal_cannot_match_a_longer_port_prefix() -> None:
    evidence = {"S1": "The fixture binds to 127.0.0.1:87870."}

    result = evaluate_literal_support(
        "The fixture binds to 127.0.0.1:8787. [S1]",
        evidence,
    )

    assert not result.passed
    assert "127.0.0.1:8787" in result.unsupported_literals


def test_exact_endpoint_literal_remains_supported() -> None:
    evidence = {"S1": "The private API binds to 127.0.0.1:8787 by default."}

    result = evaluate_literal_support(
        "The private API binds to 127.0.0.1:8787 by default. [S1]",
        evidence,
    )

    assert result.passed


def test_short_commit_sha_remains_supported_by_longer_same_sha() -> None:
    full_sha = "902b37e" + "1" * 33
    evidence = {"S1": f"The canonical integration checkpoint is {full_sha}."}

    result = evaluate_literal_support(
        "The integration checkpoint is 902b37e. [S1]",
        evidence,
    )

    assert result.passed


def test_count_literal_cannot_match_inside_a_larger_count() -> None:
    evidence = {"S1": "The integration gate completed with 1,593 tests."}

    result = evaluate_literal_support(
        "The integration gate completed with 593 tests. [S1]",
        evidence,
    )

    assert not result.passed
    assert "593 tests" in result.unsupported_literals
