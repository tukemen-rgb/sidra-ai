"""C-1647: quarantine show --content must scrub terminal-hostile characters."""

from __future__ import annotations

from sidra_ai.evals.quarantine_show_scrubs_terminal_controls import (
    evaluate_quarantine_show_scrubs_terminal_controls,
)


def test_quarantine_show_scrubs_terminal_controls():
    result = evaluate_quarantine_show_scrubs_terminal_controls()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
