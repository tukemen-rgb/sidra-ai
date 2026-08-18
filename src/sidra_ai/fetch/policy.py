from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
from typing import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit


class FetchPolicyError(ValueError):
    """Raised when a Web fetch target violates the offline Fetch Plane policy."""


_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_DEFAULT_CONTENT_TYPES = frozenset({"text/plain", "text/html", "application/json"})


@dataclass(frozen=True, slots=True)
class ValidatedFetchTarget:
    """A normalized target whose supplied DNS answers all passed IP policy."""

    url: str
    host: str
    port: int
    resolved_ips: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FetchPolicy:
    """Pure, network-free policy for the future read-only FetchBroker.

    This module deliberately performs no DNS lookup and opens no socket. The transport
    phase must inject the exact A/AAAA answers it intends to pin and connect to.
    """

    allowed_hosts: frozenset[str] = frozenset()
    max_redirects: int = 3
    max_response_bytes: int = 2 * 1024 * 1024
    allowed_content_types: frozenset[str] = _DEFAULT_CONTENT_TYPES

    def __post_init__(self) -> None:
        normalized_hosts = frozenset(_normalize_hostname(host) for host in self.allowed_hosts)
        normalized_types = frozenset(_normalize_content_type(value) for value in self.allowed_content_types)
        if self.max_redirects < 0:
            raise FetchPolicyError("max_redirects must be non-negative")
        if self.max_response_bytes <= 0:
            raise FetchPolicyError("max_response_bytes must be positive")
        if not normalized_types:
            raise FetchPolicyError("at least one content type must be allowed")
        object.__setattr__(self, "allowed_hosts", normalized_hosts)
        object.__setattr__(self, "allowed_content_types", normalized_types)

    def canonicalize_url(self, url: str) -> tuple[str, str]:
        """Validate static URL policy before any DNS lookup and return URL + host.

        FetchBroker uses this boundary before calling a resolver so an unallowlisted or
        malformed hostname can never trigger DNS work merely by being supplied as input
        or as a redirect Location.
        """

        return self._normalize_url(url)

    def validate_target(self, url: str, resolved_ips: Iterable[str]) -> ValidatedFetchTarget:
        """Validate one HTTPS target and the exact DNS answers to be pinned.

        Every supplied answer must be globally routable. Mixed public/private answer
        sets are rejected instead of filtering out only the unsafe address.
        """

        canonical_url, host = self.canonicalize_url(url)
        addresses = _validate_resolved_ips(resolved_ips)
        return ValidatedFetchTarget(
            url=canonical_url,
            host=host,
            port=443,
            resolved_ips=addresses,
        )

    def validate_redirect(
        self,
        current_url: str,
        location: str,
        resolved_ips: Iterable[str],
        *,
        redirects_taken: int,
    ) -> ValidatedFetchTarget:
        """Resolve and fully revalidate one manual redirect target."""

        if redirects_taken >= self.max_redirects:
            raise FetchPolicyError("redirect limit exceeded")
        if not isinstance(location, str) or not location.strip():
            raise FetchPolicyError("redirect Location is missing")
        redirected = urljoin(current_url, location)
        return self.validate_target(redirected, resolved_ips)

    def validate_content_type(self, value: str) -> str:
        content_type = _normalize_content_type(value)
        if content_type not in self.allowed_content_types:
            raise FetchPolicyError("response content type is not allowed")
        return content_type

    def validate_body_size(self, byte_count: int) -> int:
        if byte_count < 0:
            raise FetchPolicyError("response byte count cannot be negative")
        if byte_count > self.max_response_bytes:
            raise FetchPolicyError("response exceeds byte limit")
        return byte_count

    def _normalize_url(self, url: str) -> tuple[str, str]:
        if not isinstance(url, str) or not url.strip():
            raise FetchPolicyError("fetch URL is required")
        try:
            parsed = urlsplit(url)
        except ValueError as exc:
            raise FetchPolicyError("fetch URL is invalid") from exc

        if parsed.scheme.lower() != "https":
            raise FetchPolicyError("only https URLs are allowed")
        if parsed.username is not None or parsed.password is not None:
            raise FetchPolicyError("URL userinfo is not allowed")
        if parsed.query:
            # v0.1 intentionally refuses query-bearing URLs. Query parameters often
            # carry bearer tokens, email addresses, session identifiers, or signed
            # access material. Persisting the canonical URL into provenance/citations
            # would create a secondary secret/PII channel before content redaction.
            raise FetchPolicyError("URL query strings are not allowed")
        if parsed.fragment:
            raise FetchPolicyError("URL fragments are not allowed")
        if parsed.hostname is None:
            raise FetchPolicyError("URL hostname is required")

        try:
            port = parsed.port
        except ValueError as exc:
            raise FetchPolicyError("URL port is invalid") from exc
        if port not in (None, 443):
            raise FetchPolicyError("only port 443 is allowed")

        host = _normalize_hostname(parsed.hostname)
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise FetchPolicyError("IP-literal URLs are not allowed")

        if host not in self.allowed_hosts:
            raise FetchPolicyError("hostname is not allowlisted")

        path = parsed.path or "/"
        canonical = urlunsplit(("https", host, path, "", ""))
        return canonical, host


def _normalize_hostname(host: str) -> str:
    if not isinstance(host, str):
        raise FetchPolicyError("hostname must be text")
    normalized = host.strip().lower().rstrip(".")
    if not normalized:
        raise FetchPolicyError("hostname is empty")
    try:
        normalized.encode("ascii")
    except UnicodeEncodeError as exc:
        # Phase 1 intentionally rejects Unicode host input rather than guessing IDNA
        # equivalence. A reviewed punycode hostname can be allowlisted explicitly.
        raise FetchPolicyError("non-ASCII hostname input is not allowed") from exc
    if len(normalized) > 253:
        raise FetchPolicyError("hostname is too long")
    labels = normalized.split(".")
    if any(not _HOST_LABEL.fullmatch(label) for label in labels):
        raise FetchPolicyError("hostname is not canonical DNS syntax")
    return normalized


def _normalize_content_type(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FetchPolicyError("response content type is required")
    media_type = value.split(";", 1)[0].strip().lower()
    if not media_type or "/" not in media_type:
        raise FetchPolicyError("response content type is invalid")
    return media_type


def _validate_resolved_ips(values: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str) or not raw.strip():
            raise FetchPolicyError("DNS answer contains an invalid address")
        try:
            address = ipaddress.ip_address(raw.strip())
        except ValueError as exc:
            raise FetchPolicyError("DNS answer contains an invalid address") from exc

        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            if not address.ipv4_mapped.is_global:
                raise FetchPolicyError("DNS answer contains an unsafe address")
        elif not address.is_global:
            raise FetchPolicyError("DNS answer contains an unsafe address")

        text = str(address)
        if text not in seen:
            seen.add(text)
            normalized.append(text)

    if not normalized:
        raise FetchPolicyError("DNS answer set is empty")
    return tuple(normalized)
