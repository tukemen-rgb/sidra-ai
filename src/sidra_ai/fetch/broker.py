from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin

from .policy import FetchPolicy, FetchPolicyError, ValidatedFetchTarget
from .transport import PinnedFetchResponse


class FetchBrokerError(RuntimeError):
    """Raised when the broker cannot complete one bounded, policy-safe fetch."""


_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class FetchResolver(Protocol):
    def resolve(self, host: str, *, port: int = 443) -> tuple[str, ...]: ...


class FetchTransport(Protocol):
    def get(
        self, target: ValidatedFetchTarget, *, policy: FetchPolicy
    ) -> PinnedFetchResponse: ...


@dataclass(slots=True)
class FetchBroker:
    """Compose URL policy, bounded DNS, and pinned HTTPS with manual redirects.

    The broker deliberately returns only the bounded transport response. It does not
    create RAG documents and is not wired into the API. A later ingestion bridge must
    attach provenance, mark fetched content as untrusted DATA, run SecurityGate, and
    index only ALLOW content.

    Every redirect is resolved and validated from scratch before another network call.
    No redirect target can trigger DNS unless its static URL/allowlist policy passes.
    """

    policy: FetchPolicy
    resolver: FetchResolver
    transport: FetchTransport

    def fetch(self, url: str) -> PinnedFetchResponse:
        target = self._resolve_target(url)
        visited = {target.url}
        redirects_taken = 0

        while True:
            response = self.transport.get(target, policy=self.policy)
            if response.url != target.url:
                raise FetchBrokerError("transport response URL does not match requested target")

            if response.status == 200:
                return response

            if response.status not in _REDIRECT_STATUSES:
                raise FetchBrokerError("fetch response status is not allowed")

            if redirects_taken >= self.policy.max_redirects:
                raise FetchPolicyError("redirect limit exceeded")

            locations = response.header_values("location")
            if len(locations) != 1 or not locations[0].strip():
                raise FetchBrokerError("redirect response must contain one Location header")

            redirected_url = urljoin(target.url, locations[0])
            canonical_url, host = self.policy.canonicalize_url(redirected_url)
            if canonical_url in visited:
                raise FetchBrokerError("redirect loop detected")

            # DNS is deliberately performed only after static redirect URL policy passes.
            resolved_ips = self.resolver.resolve(host, port=443)
            target = self.policy.validate_redirect(
                target.url,
                locations[0],
                resolved_ips,
                redirects_taken=redirects_taken,
            )
            if target.url != canonical_url:
                raise FetchBrokerError("redirect canonicalization changed across policy checks")

            visited.add(target.url)
            redirects_taken += 1

    def _resolve_target(self, url: str) -> ValidatedFetchTarget:
        canonical_url, host = self.policy.canonicalize_url(url)
        resolved_ips = self.resolver.resolve(host, port=443)
        target = self.policy.validate_target(canonical_url, resolved_ips)
        if target.url != canonical_url:
            raise FetchBrokerError("target canonicalization changed across policy checks")
        return target
