"""Release-gate coverage for model backend diagnostic privacy."""

from sidra_ai.evals.model_failure_privacy import run_model_failure_privacy_suite
from sidra_ai.evals.runner import run_all


def test_model_failure_privacy_suite_passes_offline() -> None:
    outcomes = run_model_failure_privacy_suite()
    assert {outcome.case_name for outcome in outcomes} == {
        "model_failure_diagnostics_private_at_api_boundary",
    }
    assert all(outcome.passed for outcome in outcomes), [
        outcome.failures for outcome in outcomes if not outcome.passed
    ]


def test_model_failure_privacy_case_is_registered_in_release_gate() -> None:
    report = run_all()
    names = {outcome.case_name for outcome in report.outcomes}
    assert "model_failure_diagnostics_private_at_api_boundary" in names
