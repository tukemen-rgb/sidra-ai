"""C-1679: the sidra-api banner URL must be valid for an IPv6 host."""

from __future__ import annotations

from sidra_ai.evals.banner_url_is_valid_for_ipv6_host import (
    evaluate_banner_url_is_valid_for_ipv6_host,
)


def test_banner_url_is_valid_for_ipv6_host():
    result = evaluate_banner_url_is_valid_for_ipv6_host()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
