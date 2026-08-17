"""Release-gate coverage for Security finding-evidence privacy."""

from sidra_ai.evals.finding_evidence_privacy import run_finding_evidence_privacy_suite


def test_finding_evidence_privacy_eval_passes() -> None:
    outcomes = run_finding_evidence_privacy_suite()
    assert outcomes
    assert all(outcome.passed for outcome in outcomes), outcomes
