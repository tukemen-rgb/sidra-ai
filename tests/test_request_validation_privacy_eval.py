"""Release-gate regression for request-validation response privacy."""

from sidra_ai.evals.request_validation_privacy import (
    run_request_validation_privacy_suite,
)


def test_request_validation_privacy_release_gate_passes_offline() -> None:
    outcomes = run_request_validation_privacy_suite()
    assert {outcome.case_name for outcome in outcomes} == {
        "api_request_validation_response_privacy",
    }
    assert all(outcome.passed for outcome in outcomes), [
        outcome.failures for outcome in outcomes if not outcome.passed
    ]
