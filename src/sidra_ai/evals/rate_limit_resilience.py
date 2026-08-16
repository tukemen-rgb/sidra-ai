"""Offline regression for bounded API rate-limiter client state.

This eval exercises the real in-process ``RateLimiter`` without opening a
socket. It protects the availability invariant that source-IP churn cannot
cause unbounded client-state growth and cannot evict an active client in a way
that resets that client's rate-limit history.
"""

from __future__ import annotations

from unittest.mock import patch

from sidra_ai.api.app import RateLimiter
from sidra_ai.evals.cases import EvalOutcome


def _bounded_client_state_fails_closed_without_reset() -> EvalOutcome:
    failures: list[str] = []
    clock = [0.0]

    with patch("sidra_ai.api.app.time.monotonic", side_effect=lambda: clock[0]):
        limiter = RateLimiter(per_minute=1, max_clients=2)

        if not limiter.check("10.0.0.1"):
            failures.append("first tracked client was unexpectedly rejected")
        if not limiter.check("10.0.0.2"):
            failures.append("second tracked client was unexpectedly rejected")

        if limiter.check("10.0.0.3"):
            failures.append("unseen client was admitted after active client budget saturated")

        if len(limiter._hits) != 2 or "10.0.0.3" in limiter._hits:
            failures.append("rate-limiter state exceeded max_clients under source-IP churn")

        if limiter.check("10.0.0.1"):
            failures.append(
                "capacity pressure reset an active client's rate-limit history"
            )

        clock[0] = 61.0
        if not limiter.check("10.0.0.3"):
            failures.append("expired client state was not reclaimed for a new client")

        if len(limiter._hits) > 2:
            failures.append("rate-limiter state exceeded max_clients after reclamation")

    return EvalOutcome(
        case_name="api_rate_limiter_client_state_bounded",
        passed=not failures,
        detail=(
            "client-key state must stay bounded, reject unseen clients at saturation, "
            "preserve active history, and reclaim expired capacity"
        ),
        failures=tuple(failures),
    )


def run_rate_limit_resilience_suite() -> list[EvalOutcome]:
    """Run bounded rate-limiter regressions without network or model activity."""

    return [_bounded_client_state_fails_closed_without_reset()]
