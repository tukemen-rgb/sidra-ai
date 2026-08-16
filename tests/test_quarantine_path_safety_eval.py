"""Release-gate coverage for the Security quarantine filesystem boundary."""

from sidra_ai.evals.quarantine_path_safety import run_quarantine_path_safety_suite
from sidra_ai.evals.runner import run_all


def test_quarantine_path_safety_suite_passes_offline() -> None:
    outcomes = run_quarantine_path_safety_suite()
    assert {outcome.case_name for outcome in outcomes} == {
        "security_quarantine_path_filesystem_boundary",
    }
    assert all(outcome.passed for outcome in outcomes), [
        outcome.failures for outcome in outcomes if not outcome.passed
    ]


def test_release_runner_keeps_quarantine_path_safety_case() -> None:
    report = run_all()
    names = {outcome.case_name for outcome in report.outcomes}
    assert "security_quarantine_path_filesystem_boundary" in names
