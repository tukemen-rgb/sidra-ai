"""Release-gate regression for bearer-attempt throttling."""

from __future__ import annotations

from sidra_ai.evals.auth_attempt_resilience import run_auth_attempt_resilience_suite


def test_auth_attempt_resilience_release_gate_passes_offline() -> None:
    outcomes = run_auth_attempt_resilience_suite()
    assert {outcome.case_name for outcome in outcomes} == {
        "api_invalid_bearer_attempts_throttled_before_auth",
        "api_auth_attempt_budget_isolated_from_health",
    }
    assert all(outcome.passed for outcome in outcomes), [
        outcome.failures for outcome in outcomes if not outcome.passed
    ]
