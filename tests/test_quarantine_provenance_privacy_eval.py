"""Release-gate regression for quarantine provenance privacy."""

from sidra_ai.evals.quarantine_provenance_privacy import (
    run_quarantine_provenance_privacy_suite,
)


def test_quarantine_provenance_privacy_release_gate_passes_offline() -> None:
    outcomes = run_quarantine_provenance_privacy_suite()
    assert {outcome.case_name for outcome in outcomes} == {
        "security_rejected_provenance_quarantine_privacy",
        "security_oversized_block_provenance_privacy",
        "security_allowlisted_quarantine_attribution",
    }
    assert all(outcome.passed for outcome in outcomes), [
        outcome.failures for outcome in outcomes if not outcome.passed
    ]
