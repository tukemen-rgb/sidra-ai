from __future__ import annotations

from dataclasses import dataclass
import http.client
import ipaddress
import socket
import ssl
import time
from typing import Iterable
from urllib.parse import quote, urlsplit

from .policy import FetchPolicy, FetchPolicyError, ValidatedFetchTarget


class FetchTransportError(RuntimeError):
    """Raised when the pinned HTTPS transport cannot safely complete a GET."""


_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_EXPOSED_RESPONSE_HEADERS = frozenset(
    {"content-type", "content-length", "content-encoding", "location"}
)
_READ_CHUNK_BYTES = 64 * 1024
_USER_AGENT = "SIDRA-FetchBroker/0.1"


@dataclass(frozen=True, slots=True)
class PinnedFetchResponse:
    """One response obtained by connecting only to a validated destination IP.

    Redirects are intentionally *not* followed here. The future FetchBroker must
    resolve and revalidate every redirect before calling the transport again.
    Only response headers required by that broker/policy boundary are retained;
    cookies and unrelated server metadata are discarded.
    """

    url: str
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    connected_ip: str
    content_type: str | None

    def header_values(self, name: str) -> tuple[str, ...]:
        wanted = name.strip().lower()
        return tuple(value for key, value in self.headers if key == wanted)


@dataclass(frozen=True, slots=True)
class PinnedHttpsTransport:
    """GET-only HTTPS transport that never reconnects by hostname.

    The caller supplies a ``ValidatedFetchTarget`` produced by ``FetchPolicy``.
    This class revalidates that target defensively, then opens a TCP socket to an
    exact validated IP while preserving the original hostname for TLS SNI,
    certificate verification, and the HTTP Host header.

    No proxy, cookie jar, ambient Authorization header, .netrc lookup, client
    certificate, request body, or redirect-following capability exists here.
    """

    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 10.0
    overall_timeout_seconds: float = 20.0

    def __post_init__(self) -> None:
        if self.connect_timeout_seconds <= 0:
            raise FetchTransportError("connect timeout must be positive")
        if self.read_timeout_seconds <= 0:
            raise FetchTransportError("read timeout must be positive")
        if self.overall_timeout_seconds <= 0:
            raise FetchTransportError("overall timeout must be positive")

    def get(self, target: ValidatedFetchTarget, *, policy: FetchPolicy) -> PinnedFetchResponse:
        """Perform exactly one pinned HTTPS GET without following redirects."""

        try:
            revalidated = policy.validate_target(target.url, target.resolved_ips)
        except FetchPolicyError:
            raise
        if revalidated != target:
            raise FetchTransportError("fetch target does not match canonical policy output")

        deadline = time.monotonic() + self.overall_timeout_seconds
        last_unavailable: _EndpointUnavailable | None = None
        for ip in target.resolved_ips:
            try:
                wire = _request_to_ip(
                    target,
                    ip,
                    policy=policy,
                    connect_timeout_seconds=self.connect_timeout_seconds,
                    read_timeout_seconds=self.read_timeout_seconds,
                    deadline=deadline,
                )
            except _EndpointUnavailable as exc:
                last_unavailable = exc
                continue

            content_type: str | None = None
            if 200 <= wire.status < 300:
                encoding = _single_header(wire.headers, "content-encoding")
                if encoding is not None and encoding.lower() != "identity":
                    raise FetchTransportError("response content encoding is not allowed")
                raw_content_type = _single_header(wire.headers, "content-type", required=True)
                assert raw_content_type is not None
                content_type = policy.validate_content_type(raw_content_type)
                policy.validate_body_size(len(wire.body))

            return PinnedFetchResponse(
                url=target.url,
                status=wire.status,
                headers=wire.headers,
                body=wire.body,
                connected_ip=ip,
                content_type=content_type,
            )

        if last_unavailable is not None:
            raise FetchTransportError("validated HTTPS endpoints are unavailable") from last_unavailable
        raise FetchTransportError("validated HTTPS target has no destination IP")


@dataclass(frozen=True, slots=True)
class _WireResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


class _EndpointUnavailable(OSError):
    """Internal marker for network/TLS/protocol failures that may try another safe IP."""


def _request_to_ip(
    target: ValidatedFetchTarget,
    ip: str,
    *,
    policy: FetchPolicy,
    connect_timeout_seconds: float,
    read_timeout_seconds: float,
    deadline: float,
) -> _WireResponse:
    tls_socket: ssl.SSLSocket | None = None
    response: http.client.HTTPResponse | None = None
    try:
        remaining = _remaining(deadline)
        tls_socket = _dial_pinned_tls(
            target,
            ip,
            connect_timeout_seconds=min(connect_timeout_seconds, remaining),
        )
        tls_socket.settimeout(min(read_timeout_seconds, _remaining(deadline)))
        tls_socket.sendall(_build_get_request(target, policy=policy))

        response = http.client.HTTPResponse(tls_socket, method="GET")
        response.begin()
        raw_headers = tuple(
            (name.strip().lower(), value.strip()) for name, value in response.getheaders()
        )

        if response.status in _REDIRECT_STATUSES:
            _single_header(raw_headers, "location", required=True)
            return _WireResponse(
                status=response.status,
                headers=_select_response_headers(raw_headers),
                body=b"",
            )

        if not 200 <= response.status < 300:
            return _WireResponse(
                status=response.status,
                headers=_select_response_headers(raw_headers),
                body=b"",
            )

        _validate_content_length(raw_headers, policy.max_response_bytes)
        body = _read_bounded_body(
            response,
            tls_socket,
            max_bytes=policy.max_response_bytes,
            read_timeout_seconds=read_timeout_seconds,
            deadline=deadline,
        )
        return _WireResponse(
            status=response.status,
            headers=_select_response_headers(raw_headers),
            body=body,
        )
    except FetchTransportError:
        raise
    except (OSError, ssl.SSLError, http.client.HTTPException, ValueError) as exc:
        raise _EndpointUnavailable("validated endpoint request failed") from exc
    finally:
        if response is not None:
            response.close()
        if tls_socket is not None:
            tls_socket.close()


def _dial_pinned_tls(
    target: ValidatedFetchTarget,
    ip: str,
    *,
    connect_timeout_seconds: float,
) -> ssl.SSLSocket:
    """Connect to an IP literal while validating TLS for the original hostname."""

    if ip not in target.resolved_ips:
        raise FetchTransportError("connection IP is not in the validated DNS set")
    try:
        address = ipaddress.ip_address(ip)
    except ValueError as exc:
        raise FetchTransportError("connection IP is invalid") from exc

    family = socket.AF_INET6 if isinstance(address, ipaddress.IPv6Address) else socket.AF_INET
    endpoint: tuple[object, ...]
    if family == socket.AF_INET6:
        endpoint = (str(address), target.port, 0, 0)
    else:
        endpoint = (str(address), target.port)

    raw_socket = socket.socket(family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    try:
        raw_socket.settimeout(connect_timeout_seconds)
        raw_socket.connect(endpoint)
        context = ssl.create_default_context()
        if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
            raise FetchTransportError("TLS verification is not strict")
        tls_socket = context.wrap_socket(raw_socket, server_hostname=target.host)
    except Exception:
        raw_socket.close()
        raise
    return tls_socket


def _build_get_request(target: ValidatedFetchTarget, *, policy: FetchPolicy) -> bytes:
    parsed = urlsplit(target.url)
    path = parsed.path or "/"
    query = parsed.query
    if _has_control_character(path) or _has_control_character(query):
        raise FetchTransportError("request target contains control characters")

    encoded_path = quote(path, safe="/:@-._~!$&'()*+,;=%")
    encoded_query = quote(query, safe="=&?/:@-._~!$'()*+,;%")
    request_target = encoded_path + (f"?{encoded_query}" if encoded_query else "")
    accept = ", ".join(sorted(policy.allowed_content_types))

    lines = (
        f"GET {request_target} HTTP/1.1",
        f"Host: {target.host}",
        f"User-Agent: {_USER_AGENT}",
        f"Accept: {accept}",
        "Accept-Encoding: identity",
        "Connection: close",
        "",
        "",
    )
    return "\r\n".join(lines).encode("ascii")


def _read_bounded_body(
    response: http.client.HTTPResponse,
    tls_socket: ssl.SSLSocket,
    *,
    max_bytes: int,
    read_timeout_seconds: float,
    deadline: float,
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        tls_socket.settimeout(min(read_timeout_seconds, _remaining(deadline)))
        remaining_capacity = max_bytes - total
        if remaining_capacity == 0:
            extra = response.read(1)
            if extra:
                raise FetchTransportError("response exceeds byte limit")
            break
        chunk = response.read(min(_READ_CHUNK_BYTES, remaining_capacity))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def _validate_content_length(headers: Iterable[tuple[str, str]], max_bytes: int) -> None:
    values = tuple(value for key, value in headers if key == "content-length")
    if not values:
        return
    if len(set(values)) != 1:
        raise FetchTransportError("response has conflicting Content-Length values")
    raw = values[0]
    if not raw.isascii() or not raw.isdigit():
        raise FetchTransportError("response Content-Length is invalid")
    size = int(raw)
    if size > max_bytes:
        raise FetchTransportError("response exceeds byte limit")


def _select_response_headers(
    headers: Iterable[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    """Retain only headers required by redirect/body policy; discard cookies."""

    return tuple((key, value) for key, value in headers if key in _EXPOSED_RESPONSE_HEADERS)


def _single_header(
    headers: Iterable[tuple[str, str]],
    name: str,
    *,
    required: bool = False,
) -> str | None:
    wanted = name.strip().lower()
    values = tuple(value for key, value in headers if key == wanted)
    if len(values) > 1:
        raise FetchTransportError(f"response has multiple {wanted} headers")
    if not values:
        if required:
            raise FetchTransportError(f"response {wanted} header is required")
        return None
    return values[0]


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise FetchTransportError("overall fetch timeout exceeded")
    return remaining


def _has_control_character(value: str) -> bool:
    return any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
