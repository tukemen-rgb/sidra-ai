from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from sidra_ai.fetch.broker import FetchBroker, FetchBrokerError
from sidra_ai.fetch.policy import FetchPolicy, FetchPolicyError, ValidatedFetchTarget
from sidra_ai.fetch.transport import PinnedFetchResponse


@dataclass
class FakeResolver:
    answers: dict[str, tuple[str, ...]]
    calls: list[tuple[str, int]] = field(default_factory=list)

    def resolve(self, host: str, *, port: int = 443) -> tuple[str, ...]:
        self.calls.append((host, port))
        return self.answers[host]


@dataclass
class FakeTransport:
    responses: dict[str, PinnedFetchResponse]
    targets: list[ValidatedFetchTarget] = field(default_factory=list)

    def get(
        self, target: ValidatedFetchTarget, *, policy: FetchPolicy
    ) -> PinnedFetchResponse:
        self.targets.append(target)
        return self.responses[target.url]


def redirect(url: str, location: str, *, connected_ip: str = "1.1.1.1") -> PinnedFetchResponse:
    return PinnedFetchResponse(
        url=url,
        status=302,
        headers=(("location", location),),
        body=b"",
        connected_ip=connected_ip,
        content_type=None,
    )


def ok(url: str, *, connected_ip: str) -> PinnedFetchResponse:
    return PinnedFetchResponse(
        url=url,
        status=200,
        headers=(("content-type", "text/plain"),),
        body=b"safe body",
        connected_ip=connected_ip,
        content_type="text/plain",
    )


def test_redirect_is_reresolved_revalidated_and_repinned() -> None:
    policy = FetchPolicy(allowed_hosts=frozenset({"docs.example", "cdn.example"}))
    resolver = FakeResolver(
        {
            "docs.example": ("1.1.1.1",),
            "cdn.example": ("8.8.8.8",),
        }
    )
    transport = FakeTransport(
        {
            "https://docs.example/start": redirect(
                "https://docs.example/start", "https://cdn.example/final"
            ),
            "https://cdn.example/final": ok(
                "https://cdn.example/final", connected_ip="8.8.8.8"
            ),
        }
    )

    response = FetchBroker(policy, resolver, transport).fetch("https://DOCS.EXAMPLE./start")

    assert response.body == b"safe body"
    assert resolver.calls == [("docs.example", 443), ("cdn.example", 443)]
    assert [(target.host, target.resolved_ips) for target in transport.targets] == [
        ("docs.example", ("1.1.1.1",)),
        ("cdn.example", ("8.8.8.8",)),
    ]


def test_unallowlisted_redirect_is_rejected_before_dns() -> None:
    policy = FetchPolicy(allowed_hosts=frozenset({"docs.example"}))
    resolver = FakeResolver({"docs.example": ("1.1.1.1",)})
    transport = FakeTransport(
        {
            "https://docs.example/start": redirect(
                "https://docs.example/start", "https://evil.example/steal"
            )
        }
    )

    with pytest.raises(FetchPolicyError, match="allowlisted"):
        FetchBroker(policy, resolver, transport).fetch("https://docs.example/start")

    assert resolver.calls == [("docs.example", 443)]
    assert len(transport.targets) == 1


def test_redirect_with_mixed_unsafe_dns_answers_fails_closed() -> None:
    policy = FetchPolicy(allowed_hosts=frozenset({"docs.example", "cdn.example"}))
    resolver = FakeResolver(
        {
            "docs.example": ("1.1.1.1",),
            "cdn.example": ("8.8.8.8", "127.0.0.1"),
        }
    )
    transport = FakeTransport(
        {
            "https://docs.example/start": redirect(
                "https://docs.example/start", "https://cdn.example/final"
            )
        }
    )

    with pytest.raises(FetchPolicyError, match="unsafe address"):
        FetchBroker(policy, resolver, transport).fetch("https://docs.example/start")

    assert resolver.calls == [("docs.example", 443), ("cdn.example", 443)]
    assert len(transport.targets) == 1


def test_redirect_loop_is_rejected_before_re_resolving_seen_url() -> None:
    policy = FetchPolicy(allowed_hosts=frozenset({"docs.example"}))
    resolver = FakeResolver({"docs.example": ("1.1.1.1",)})
    transport = FakeTransport(
        {
            "https://docs.example/a": redirect("https://docs.example/a", "/b"),
            "https://docs.example/b": redirect("https://docs.example/b", "/a"),
        }
    )

    with pytest.raises(FetchBrokerError, match="redirect loop"):
        FetchBroker(policy, resolver, transport).fetch("https://docs.example/a")

    assert resolver.calls == [("docs.example", 443), ("docs.example", 443)]


def test_redirect_limit_is_enforced_before_extra_dns_work() -> None:
    policy = FetchPolicy(allowed_hosts=frozenset({"docs.example"}), max_redirects=1)
    resolver = FakeResolver({"docs.example": ("1.1.1.1",)})
    transport = FakeTransport(
        {
            "https://docs.example/a": redirect("https://docs.example/a", "/b"),
            "https://docs.example/b": redirect("https://docs.example/b", "/c"),
        }
    )

    with pytest.raises(FetchPolicyError, match="redirect limit"):
        FetchBroker(policy, resolver, transport).fetch("https://docs.example/a")

    assert resolver.calls == [("docs.example", 443), ("docs.example", 443)]


def test_initial_unallowlisted_target_never_triggers_dns() -> None:
    policy = FetchPolicy(allowed_hosts=frozenset({"docs.example"}))
    resolver = FakeResolver({})
    transport = FakeTransport({})

    with pytest.raises(FetchPolicyError, match="allowlisted"):
        FetchBroker(policy, resolver, transport).fetch("https://evil.example/")

    assert resolver.calls == []
    assert transport.targets == []


def test_non_redirect_non_200_status_is_rejected() -> None:
    policy = FetchPolicy(allowed_hosts=frozenset({"docs.example"}))
    resolver = FakeResolver({"docs.example": ("1.1.1.1",)})
    response = PinnedFetchResponse(
        url="https://docs.example/missing",
        status=404,
        headers=(),
        body=b"",
        connected_ip="1.1.1.1",
        content_type=None,
    )
    transport = FakeTransport({response.url: response})

    with pytest.raises(FetchBrokerError, match="status"):
        FetchBroker(policy, resolver, transport).fetch(response.url)
