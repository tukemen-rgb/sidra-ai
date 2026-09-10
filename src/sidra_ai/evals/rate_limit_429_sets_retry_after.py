"""Does a 429 (rate limit) carry a usable ``Retry-After`` header?

C-1639. RFC 6585 §4 says a 429 response SHOULD include ``Retry-After`` so a
client knows how long to wait. SIDRA itself depends on that header the other way
round - ``ingestion/github_client.py`` uses its presence to tell a GitHub rate
limit from a permission failure - yet SIDRA's own API returned 429 without it,
leaving a rate-limited client (its own CLI included) to guess.

The limiter is a fixed window, so the exact wait is computable from the oldest
hit still in the window. The checks drive the real app with a low limit, trip
429 on both an authenticated ``/v1`` route and the unauthenticated ``/health``
probe, and read the header.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass


def _client():
    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.echo import EchoModelAdapter

    settings = Settings(data_dir=tempfile.mkdtemp(), rate_limit_per_minute=5)
    service = SidraService(settings, model=EchoModelAdapter())
    return TestClient(create_app(service, settings))


def _trip(api, path: str):
    """Hammer `path` until a 429 comes back; return that response (or the last)."""
    last = None
    for _ in range(12):
        last = api.get(path)
        if last.status_code == 429:
            return last
    return last


@dataclass(frozen=True)
class RateLimitRetryAfterResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_rate_limit_429_sets_retry_after() -> RateLimitRetryAfterResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    def header(resp) -> str | None:
        for k, v in resp.headers.items():
            if k.lower() == "retry-after":
                return v
        return None

    # --- /health (unauthenticated, health_limiter) ---
    api = _client()
    h = _trip(api, "/health")
    add(h.status_code == 429, f"/health did not reach 429: {h.status_code}")
    hv = header(h)
    add(hv is not None, "/health 429 missing Retry-After")
    add(hv is not None and hv.isdigit() and int(hv) >= 1,
        f"/health Retry-After not a positive int: {hv!r}")
    add(hv is not None and hv.isdigit() and int(hv) <= 60,
        f"/health Retry-After exceeds window (60s): {hv!r}")
    # detail unchanged
    add(h.json().get("detail") == "rate limit exceeded",
        f"/health 429 detail changed: {h.json().get('detail')!r}")

    # --- /v1/index (authenticated route, auth+rate limiters) ---
    api2 = _client()
    v = _trip(api2, "/v1/index")
    add(v.status_code == 429, f"/v1/index did not reach 429: {v.status_code}")
    vv = header(v)
    add(vv is not None, "/v1/index 429 missing Retry-After")
    add(vv is not None and vv.isdigit() and 1 <= int(vv) <= 60,
        f"/v1/index Retry-After out of range: {vv!r}")

    # --- a 200 (before the limit) does not carry Retry-After ---
    api3 = _client()
    ok = api3.get("/health")
    add(ok.status_code == 200 and header(ok) is None,
        f"200 response carried Retry-After: {ok.status_code} {header(ok)!r}")

    total = 5 + 3 + 1
    return RateLimitRetryAfterResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["RateLimitRetryAfterResult", "evaluate_rate_limit_429_sets_retry_after"]
