"""C-1740: an out-of-range SIDRA_PORT must name the valid range."""

from __future__ import annotations

from sidra_ai.evals.config_port_out_of_range_is_named import (
    evaluate_config_port_out_of_range_is_named,
)


def test_config_port_out_of_range_is_named():
    result = evaluate_config_port_out_of_range_is_named()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
