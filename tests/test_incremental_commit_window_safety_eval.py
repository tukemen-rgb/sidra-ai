"""Release-gate regression for incremental commit-window completeness."""

from sidra_ai.evals.incremental_commit_window_safety import (
    run_incremental_commit_window_safety_suite,
)


def test_incremental_commit_window_safety_release_gate_passes_offline() -> None:
    outcomes = run_incremental_commit_window_safety_suite()
    assert {outcome.case_name for outcome in outcomes} == {
        "rag_incremental_commit_window_budget_preserves_snapshot",
        "rag_truncated_compare_preserves_snapshot",
    }
    assert all(outcome.passed for outcome in outcomes), [
        outcome.failures for outcome in outcomes if not outcome.passed
    ]
