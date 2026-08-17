from __future__ import annotations

from threading import Event
import socket

import pytest

from sidra_ai.fetch.policy import FetchPolicy, FetchPolicyError
from sidra_ai.fetch.resolver import BoundedDnsResolver, FetchDnsError


def _v4(address: str) -> tuple:
    return (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))


def _v6(address: str) -> tuple:
    return (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443, 0, 0))


def test_resolver_returns_complete_deduplicated_a_aaaa_set() -> None:
    calls: list[tuple] = []

    def lookup(host: str, port: int, family: int, socktype: int, proto: int) -> list[tuple]:
        calls.append((host, port, family, socktype, proto))
        return [_v4("8.8.8.8"), _v4("8.8.8.8"), _v6("2606:4700:4700::1111")]

    resolver = BoundedDnsResolver(lookup=lookup)

    assert resolver.resolve("allowed.example") == ("8.8.8.8", "2606:4700:4700::1111")
    assert calls == [
        (
            "allowed.example",
            443,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
        )
    ]


def test_resolver_rejects_noncanonical_or_ip_literal_host() -> None:
    resolver = BoundedDnsResolver(lookup=lambda *_args: [_v4("8.8.8.8")])

    with pytest.raises(FetchDnsError, match="canonical"):
        resolver.resolve("Allowed.Example.")
    with pytest.raises(FetchDnsError, match="IP literal"):
        resolver.resolve("8.8.8.8")


def test_resolver_fails_closed_instead_of_truncating_answer_set() -> None:
    resolver = BoundedDnsResolver(
        max_addresses=2,
        lookup=lambda *_args: [_v4("8.8.8.8"), _v4("1.1.1.1"), _v4("9.9.9.9")],
    )

    with pytest.raises(FetchDnsError, match="exceeds limit"):
        resolver.resolve("allowed.example")


def test_policy_still_rejects_mixed_public_private_dns_answers() -> None:
    resolver = BoundedDnsResolver(
        lookup=lambda *_args: [_v4("8.8.8.8"), _v4("10.0.0.10")],
    )
    policy = FetchPolicy(allowed_hosts=frozenset({"allowed.example"}))

    addresses = resolver.resolve("allowed.example")
    with pytest.raises(FetchPolicyError, match="unsafe address"):
        policy.validate_target("https://allowed.example/", addresses)


def test_timeout_keeps_capacity_reserved_until_stuck_lookup_exits() -> None:
    release = Event()

    def lookup(*_args: object) -> list[tuple]:
        release.wait(timeout=1.0)
        return [_v4("8.8.8.8")]

    resolver = BoundedDnsResolver(timeout_seconds=0.02, max_inflight=1, lookup=lookup)

    with pytest.raises(FetchDnsError, match="timed out"):
        resolver.resolve("allowed.example")
    with pytest.raises(FetchDnsError, match="busy"):
        resolver.resolve("allowed.example")

    release.set()


def test_resolver_sanitizes_lookup_failures() -> None:
    def lookup(*_args: object) -> list[tuple]:
        raise OSError("resolver leaked internal marker SECRET-DNS-DIAGNOSTIC")

    resolver = BoundedDnsResolver(lookup=lookup)

    with pytest.raises(FetchDnsError) as caught:
        resolver.resolve("allowed.example")
    assert str(caught.value) == "DNS resolution failed"
    assert "SECRET-DNS-DIAGNOSTIC" not in str(caught.value)
