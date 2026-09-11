"""C-1655: /v1/index must surface the background refresher's health."""

from __future__ import annotations

from sidra_ai.evals.index_surfaces_refresh_status import (
    evaluate_index_surfaces_refresh_status,
)


def test_index_surfaces_refresh_status():
    result = evaluate_index_surfaces_refresh_status()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
