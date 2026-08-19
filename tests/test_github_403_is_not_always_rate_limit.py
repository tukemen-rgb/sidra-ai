"""GitHub answers 403 for "slow down" and for "you may not read this".

Retrying the second one cannot succeed. It spends the retry budget, delays the
report by the full backoff, and then tells the operator a rate-limit story for
what is actually a permissions problem - which sends them to look at quota
dashboards instead of at the token's scope.

Throttling always announces itself in headers: an exhausted quota sets
`X-RateLimit-Remaining: 0`, and a secondary limit sets `Retry-After`. A refusal
sets neither. The two cases are therefore separable from headers alone, without
guessing at message text.

A correction worth keeping, because it nearly became the justification for this
file. A 403 observed through `curl` on 2026-08-19 carried no rate-limit headers
at all, and was read as "this is what GitHub's refusal looks like". It was not
GitHub's: the client sets `trust_env=False`, so it bypasses the ambient proxy
that `curl` uses, and the two were talking to different servers. Against real
GitHub the same call returned 403 with `x-ratelimit-limit: 60,
x-ratelimit-remaining: 0` - a genuine exhausted anonymous quota, which the old
code was right to retry. The rule below is unchanged by that, because a
headerless 403 should fail fast whoever sent it, but the evidence for it is not
what it first appeared to be.

The bias is deliberate: an ambiguous 403 reads as a refusal and fails fast. A
request that can never succeed is cheaper to abandon than to retry, and the
status code still reaches the caller either way.
"""

from __future__ import annotations

import pytest

from sidra_ai.config.settings import Settings
from sidra_ai.ingestion.github_client import (
    GitHubAPIError,
    GitHubReadOnlyClient,
    Response,
)

REPOSITORY = "tukemen-rgb/sidra-ai"


class CountingTransport:
    """Answers every request identically and counts the attempts."""

    def __init__(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.headers = headers or {}
        self.calls = 0

    def __call__(self, method, url, headers, timeout):  # noqa: D102 - protocol
        self.calls += 1
        return Response(status=self.status, headers=dict(self.headers), body={})


def _client(transport: CountingTransport) -> GitHubReadOnlyClient:
    slept: list[float] = []
    client = GitHubReadOnlyClient(
        Settings(allowed_repositories=(REPOSITORY,)),
        transport=transport,
        sleep=slept.append,
    )
    client._slept = slept  # type: ignore[attr-defined]
    return client


# ------------------------------------------------------- refusal: fail fast


def test_a_403_without_rate_limit_headers_is_not_retried() -> None:
    """The shape an intermediary returns when it refuses before GitHub."""

    transport = CountingTransport(403)
    client = _client(transport)

    with pytest.raises(GitHubAPIError) as caught:
        client.get_repository(REPOSITORY)

    assert transport.calls == 1, "an unauthorized 403 was retried"
    assert caught.value.status == 403
    assert "not authorized" in str(caught.value)


def test_a_refusal_does_not_sleep() -> None:
    """Backoff on a permanent refusal is pure delay."""

    client = _client(CountingTransport(403))

    with pytest.raises(GitHubAPIError):
        client.get_repository(REPOSITORY)

    assert client._slept == []


def test_the_refusal_message_does_not_blame_rate_limiting() -> None:
    """The old wording sent the reader to the wrong dashboard."""

    client = _client(CountingTransport(403))

    with pytest.raises(GitHubAPIError) as caught:
        client.get_repository(REPOSITORY)

    assert "rate limit" not in str(caught.value).lower()


# ---------------------------------------------------- throttling: still retry


def test_a_primary_rate_limit_is_still_retried() -> None:
    """`X-RateLimit-Remaining: 0` is GitHub's primary-limit signal."""

    transport = CountingTransport(403, {"X-RateLimit-Remaining": "0"})
    client = _client(transport)

    with pytest.raises(GitHubAPIError) as caught:
        client.get_repository(REPOSITORY)

    assert transport.calls == 3, "the primary rate limit stopped being retried"
    assert client._slept == [1, 2]
    assert "rate limited" in str(caught.value)


def test_a_secondary_rate_limit_is_still_retried() -> None:
    """`Retry-After` is the secondary-limit signal and carries no quota header."""

    transport = CountingTransport(403, {"Retry-After": "60"})
    client = _client(transport)

    with pytest.raises(GitHubAPIError):
        client.get_repository(REPOSITORY)

    assert transport.calls == 3


def test_429_is_always_retried() -> None:
    """Whatever headers accompany it, 429 means throttled."""

    transport = CountingTransport(429)
    client = _client(transport)

    with pytest.raises(GitHubAPIError):
        client.get_repository(REPOSITORY)

    assert transport.calls == 3


def test_quota_remaining_means_the_403_is_a_refusal() -> None:
    """Headers present and quota unspent: throttling is not the explanation."""

    transport = CountingTransport(403, {"X-RateLimit-Remaining": "4999"})
    client = _client(transport)

    with pytest.raises(GitHubAPIError) as caught:
        client.get_repository(REPOSITORY)

    assert transport.calls == 1
    assert "not authorized" in str(caught.value)


@pytest.mark.parametrize("value", ["", "   ", "not-a-number", "nan"])
def test_an_unreadable_quota_header_fails_fast(value: str) -> None:
    """Ambiguity resolves to refusal, not to a retry that cannot succeed."""

    transport = CountingTransport(403, {"X-RateLimit-Remaining": value})
    client = _client(transport)

    with pytest.raises(GitHubAPIError):
        client.get_repository(REPOSITORY)

    assert transport.calls == 1


def test_header_matching_ignores_case() -> None:
    """Header casing varies by proxy; the decision must not."""

    transport = CountingTransport(403, {"x-ratelimit-remaining": "0"})
    client = _client(transport)

    with pytest.raises(GitHubAPIError):
        client.get_repository(REPOSITORY)

    assert transport.calls == 3, "a lowercase quota header was read as a refusal"
