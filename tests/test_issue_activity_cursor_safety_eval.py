"""Release-gate regression for mutable Issue activity cursor integrity."""

from sidra_ai.evals.issue_activity_cursor_safety import (
    run_issue_activity_cursor_safety_suite,
)


def test_issue_activity_cursor_safety_release_gate_passes_offline() -> None:
    outcomes = run_issue_activity_cursor_safety_suite()
    assert {outcome.case_name for outcome in outcomes} == {
        "rag_issue_activity_cursor_preserves_verified_snapshot",
    }
    assert all(outcome.passed for outcome in outcomes), [
        outcome.failures for outcome in outcomes if not outcome.passed
    ]
