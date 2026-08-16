"""Release-gate coverage for bounded API repository scopes."""

from sidra_ai.evals.repository_scope_boundary import run_repository_scope_boundary_suite
from sidra_ai.evals.runner import run_all


def test_repository_scope_boundary_eval_passes_offline() -> None:
    outcomes = run_repository_scope_boundary_suite()
    assert {outcome.case_name for outcome in outcomes} == {
        "api_repository_scope_request_boundary",
    }
    assert all(outcome.passed for outcome in outcomes), [
        outcome.failures for outcome in outcomes if not outcome.passed
    ]


def test_repository_scope_boundary_remains_in_release_gate() -> None:
    report = run_all()
    assert any(
        outcome.case_name == "api_repository_scope_request_boundary"
        for outcome in report.outcomes
    )
