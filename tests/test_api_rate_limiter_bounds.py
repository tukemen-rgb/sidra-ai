"""Bounded client-state regression tests for the private API rate limiter."""

from __future__ import annotations

import pytest

from sidra_ai.api.app import RateLimiter


def test_rate_limiter_fails_closed_for_new_client_when_capacity_is_full() -> None:
    limiter = RateLimiter(per_minute=10, max_clients=2)

    assert limiter.check("10.0.0.1") is True
    assert limiter.check("10.0.0.2") is True
    assert limiter.check("10.0.0.3") is False

    assert list(limiter._hits) == ["10.0.0.1", "10.0.0.2"]
    assert limiter.check("10.0.0.1") is True


def test_rate_limiter_reclaims_expired_client_before_rejecting_new_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr("sidra_ai.api.app.time.monotonic", lambda: clock[0])
    limiter = RateLimiter(per_minute=1, max_clients=1)

    assert limiter.check("10.0.0.1") is True
    assert limiter.check("10.0.0.2") is False

    clock[0] = 61.0
    assert limiter.check("10.0.0.2") is True
    assert list(limiter._hits) == ["10.0.0.2"]


def test_rate_limiter_rejects_non_positive_client_capacity() -> None:
    with pytest.raises(ValueError, match="max_clients must be positive"):
        RateLimiter(per_minute=1, max_clients=0)
