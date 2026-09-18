"""Mirror test for the C-1961 eval: a PGP private key block must be caught."""

from __future__ import annotations

from sidra_ai.evals.output_guard_blocks_pgp_private_key import (
    evaluate_output_guard_blocks_pgp_private_key,
)


def test_output_guard_blocks_pgp_private_key() -> None:
    result = evaluate_output_guard_blocks_pgp_private_key()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total
