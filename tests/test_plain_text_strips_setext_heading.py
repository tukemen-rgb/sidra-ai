"""C-1709: answer/evidence flattening must strip a setext = underline, not leave it."""

from __future__ import annotations

from sidra_ai.evals.plain_text_strips_setext_heading import (
    evaluate_plain_text_strips_setext_heading,
)


def test_plain_text_strips_setext_heading():
    result = evaluate_plain_text_strips_setext_heading()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
