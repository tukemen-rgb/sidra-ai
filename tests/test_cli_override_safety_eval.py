"""Release-gate regression for explicit CLI override semantics."""

from __future__ import annotations

from sidra_ai.evals.cli_override_safety import run_cli_override_safety_suite


def test_cli_override_safety_release_gate_passes_offline() -> None:
    outcomes = run_cli_override_safety_suite()
    assert {outcome.case_name for outcome in outcomes} == {
        "api_cli_explicit_zero_port_fails_prebind",
        "api_cli_explicit_empty_host_fails_prebind",
        "api_cli_valid_port_override_reaches_exact_bind",
    }
    assert all(outcome.passed for outcome in outcomes), [
        outcome.failures for outcome in outcomes if not outcome.passed
    ]
