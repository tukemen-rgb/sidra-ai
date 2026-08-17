"""Release-gate regression for repository rejection response privacy."""

from sidra_ai.evals.repository_rejection_privacy import (
    run_repository_rejection_privacy_suite,
)


def test_repository_rejection_privacy_release_gate_passes_offline() -> None:
    outcomes = run_repository_rejection_privacy_suite()
    assert {outcome.case_name for outcome in outcomes} == {
        "api_repository_rejection_response_privacy",
    }
    assert all(outcome.passed for outcome in outcomes), [
        outcome.failures for outcome in outcomes if not outcome.passed
    ]
