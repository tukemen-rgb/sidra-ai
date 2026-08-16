"""Release-gate coverage for Fetch Plane response integrity."""

from __future__ import annotations

from sidra_ai.evals.fetch_response_integrity import run_fetch_response_integrity_suite


def test_fetch_response_integrity_release_gate_passes_offline() -> None:
    outcomes = run_fetch_response_integrity_suite()
    assert {outcome.case_name for outcome in outcomes} == {
        "fetch_response_integrity_fails_closed",
    }
    assert all(outcome.passed for outcome in outcomes), [
        outcome.failures for outcome in outcomes if not outcome.passed
    ]
