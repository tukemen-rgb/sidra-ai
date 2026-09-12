"""C-1727: a revision 'not found' reply must disclose when its title list is cut."""

from __future__ import annotations

from sidra_ai.evals.revision_not_found_lists_all_titles import (
    evaluate_revision_not_found_lists_all_titles,
)


def test_revision_not_found_lists_all_titles():
    result = evaluate_revision_not_found_lists_all_titles()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
