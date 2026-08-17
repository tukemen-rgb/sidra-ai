from __future__ import annotations

from sidra_ai.evals.ollama_context_parity import run_ollama_context_parity_suite


def test_ollama_context_parity_release_gate_passes() -> None:
    outcomes = run_ollama_context_parity_suite()

    assert outcomes
    assert all(outcome.passed for outcome in outcomes), [
        (outcome.case_name, outcome.failures) for outcome in outcomes if not outcome.passed
    ]
