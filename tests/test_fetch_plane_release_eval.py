from __future__ import annotations

from sidra_ai.evals.fetch_plane_release import run_fetch_plane_release_suite


def test_fetch_plane_release_suite_passes() -> None:
    outcomes = run_fetch_plane_release_suite()

    assert {outcome.case_name for outcome in outcomes} == {
        "fetch_mixed_dns_ssrf_fail_closed",
        "fetch_query_secret_rejected_before_dns",
        "fetch_redirect_dns_revalidation_fail_closed",
        "fetch_external_provenance_allow_only_retrieval",
        "fetch_prompt_injection_never_retrievable",
    }
    assert all(outcome.passed for outcome in outcomes), {
        outcome.case_name: outcome.failures
        for outcome in outcomes
        if not outcome.passed
    }
