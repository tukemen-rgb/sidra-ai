"""Release-gate registration for ingestion cursor filesystem safety."""

from sidra_ai.evals.runner import run_all
from sidra_ai.evals.state_path_safety import run_state_path_safety_suite


def test_state_path_safety_suite_passes() -> None:
    outcomes = run_state_path_safety_suite()
    assert outcomes
    assert all(outcome.passed for outcome in outcomes), [
        failure
        for outcome in outcomes
        for failure in outcome.failures
    ]


def test_state_path_safety_suite_is_registered_in_release_gate() -> None:
    report = run_all(())
    names = {outcome.case_name for outcome in report.outcomes}
    assert "ingestion_state_cursor_filesystem_boundary" in names
