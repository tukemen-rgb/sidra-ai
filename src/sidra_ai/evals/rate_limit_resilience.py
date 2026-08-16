"""Offline regression for bounded API rate-limiter client state."""

from __future__ import annotations

from sidra_ai.api.app import RateLimiter
from sidra_ai.evals.cases import EvalOutcome


def run_rate_limit_resilience_suite() -> tuple[EvalOutcome, ...]:
    """Prove source-IP churn cannot grow limiter state or reset active limits."""

    failures: list[str] = []
    limiter = RateLimiter(per_minute=1, max_clients=2)

    if limiter.check("10.0.0.1") is not True:
        failures.append("first tracked client was unexpectedly rejected")
    if limiter.check("10.0.0.2") is not True:
        failures.append("second tracked client was unexpectedly rejected")

    if limiter.check("10.0.0.3") is not False:
        failures.append("unseen client was admitted after active-client capacity saturated")

    tracked = tuple(limiter._hits)
    if tracked != ("10.0.0.1", "10.0.0.2"):
        failures.append(f"active client history changed after saturation: {tracked!r}")
    if len(limiter._hits) > limiter.max_clients:
        failures.append(
            f"tracked client state exceeded configured bound: {len(limiter._hits)} > {limiter.max_clients}"
        )

    # Capacity pressure must not evict an active client and thereby reset that
    # client's per-minute allowance.  A second request from the first client
    # must still be limited after the unseen client was rejected.
    if limiter.check("10.0.0.1") is not False:
        failures.append("capacity pressure reset an active client's rate-limit history")

    return (
        EvalOutcome(
            case_name="api_rate_limiter_client_state_bounded",
            passed=not failures,
            detail=f"tracked={len(limiter._hits)}; max_clients={limiter.max_clients}",
            failures=tuple(failures),
        ),
    )
