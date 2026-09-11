"""C-1675: sidra-ask refusal guidance must match the refusal reason."""

from __future__ import annotations

from sidra_ai.evals.ask_refusal_message_matches_reason import (
    evaluate_ask_refusal_message_matches_reason,
)


def test_ask_refusal_message_matches_reason():
    result = evaluate_ask_refusal_message_matches_reason()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
