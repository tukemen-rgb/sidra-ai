"""C-1698: the DATA envelope must defang the supported backends' chat delimiters."""

from __future__ import annotations

from sidra_ai.evals.data_envelope_neutralizes_model_delimiters import (
    evaluate_data_envelope_neutralizes_model_delimiters,
)


def test_data_envelope_neutralizes_model_delimiters():
    result = evaluate_data_envelope_neutralizes_model_delimiters()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
