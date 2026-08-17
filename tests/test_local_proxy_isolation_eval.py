from __future__ import annotations

from sidra_ai.evals.local_proxy_isolation import run_local_proxy_isolation_suite


def test_local_proxy_isolation_release_gate_passes() -> None:
    outcomes = run_local_proxy_isolation_suite()

    assert outcomes
    assert all(outcome.passed for outcome in outcomes), [
        (outcome.case_name, outcome.failures) for outcome in outcomes if not outcome.passed
    ]
