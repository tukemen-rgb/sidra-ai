from sidra_ai.evals.audit_startup_privacy import run_audit_startup_privacy_suite


def test_audit_startup_privacy_release_gate_passes_offline() -> None:
    outcomes = run_audit_startup_privacy_suite()
    assert {outcome.case_name for outcome in outcomes} == {
        "api_startup_audit_storage_failure_prebind_privacy",
    }
    assert all(outcome.passed for outcome in outcomes), [
        outcome.failures for outcome in outcomes if not outcome.passed
    ]
