"""GitHub answers 403 for "slow down" and for "you may not read this".

Retrying the second one cannot succeed. It spends the retry budget, delays the
report by the full backoff, and then tells the operator a rate-limit story for
what is actually a permissions problem - which sends them to look at quota
dashboards instead of at the token's scope.

Throttling announces itself in headers: an exhausted quota sets
`X-RateLimit-Remaining: 0`, and a secondary limit sets `Retry-After`. A refusal
carries neither *signal* - but it does carry the quota headers, with the quota
unspent, because GitHub answers a refusal like it answers anything else. The
two cases are therefore separable from headers alone, without guessing at
message text.

That distinction is not pedantry. Until 2026-08-23 the refusal message read
"not authorized (no rate-limit headers on the response)", which is what a
blocked request looks like, not what a scope failure looks like; a live
diagnosis of a 403 carrying `x-ratelimit-remaining: 4900` went looking for an
intermediary because of that sentence. The classifier was right the whole time.
The tests at the bottom of this file pin what the message is allowed to claim.

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


# ------------------------------------------- the message reports what it saw
#
# The classification above is decided by headers; these hold the sentence the
# operator actually reads. A message that describes a response other than the
# one that arrived costs a diagnosis, which is exactly what it did.


def _refusal_message(headers: dict[str, str] | None = None) -> str:
    client = _client(CountingTransport(403, headers))
    with pytest.raises(GitHubAPIError) as caught:
        client.get_repository(REPOSITORY)
    return str(caught.value)


def test_a_refusal_with_quota_left_names_the_quota_it_saw() -> None:
    """The ordinary shape: GitHub answered, and the answer was "no"."""

    message = _refusal_message({"X-RateLimit-Remaining": "4900"})

    assert "not authorized" in message
    assert "4900" in message, "the header that decided this is not in the message"
    assert "quota is not spent" in message
    assert "rate limit" not in message.lower()


def test_a_refusal_does_not_claim_headers_that_arrived_were_absent() -> None:
    """The defect this file's docstring describes, held down directly.

    Any wording is fine as long as it does not deny the header that is sitting
    on the response - the reader who believes that denial goes looking for a
    proxy and finds nothing, because there is no proxy.
    """

    message = _refusal_message({"X-RateLimit-Remaining": "4900"}).lower()

    assert "no rate-limit headers" not in message
    assert "no x-ratelimit-remaining" not in message


def test_a_headerless_refusal_says_so_and_names_the_other_possibility() -> None:
    """Here the absence is real, and it has two causes worth distinguishing."""

    message = _refusal_message().lower()

    assert "no throttling signal at all" in message
    assert "blocked before" in message, (
        "a 403 with no headers at all may never have reached GitHub; the "
        "message is the only place that can say so"
    )


def test_an_unreadable_quota_header_is_quoted_rather_than_summarised() -> None:
    """Fails fast either way, but the operator should see the odd value."""

    message = _refusal_message({"X-RateLimit-Remaining": "not-a-number"})

    assert "not-a-number" in message
    assert "not a number" in message


def test_the_two_refusals_do_not_read_alike() -> None:
    """The point of the change: one sentence used to serve both cases."""

    assert _refusal_message({"X-RateLimit-Remaining": "4900"}) != _refusal_message()
