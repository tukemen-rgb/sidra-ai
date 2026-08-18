import socket
import ssl
import time

import pytest

from sidra_ai.fetch import (
    FetchPolicy,
    FetchPolicyError,
    FetchTransportError,
    PinnedHttpsTransport,
    ValidatedFetchTarget,
)
import sidra_ai.fetch.transport as transport_module


PUBLIC_V4_A = "93.184.216.34"
PUBLIC_V4_B = "142.250.191.132"


def policy(**kwargs):
    return FetchPolicy(allowed_hosts=frozenset({"docs.example.com"}), **kwargs)


def target(*ips: str, url: str = "https://docs.example.com/reference"):
    return policy().validate_target(url, ips or (PUBLIC_V4_A,))


class _FakeRawSocket:
    def __init__(self):
        self.timeouts = []
        self.connected = None
        self.closed = False

    def settimeout(self, value):
        self.timeouts.append(value)

    def connect(self, endpoint):
        self.connected = endpoint

    def close(self):
        self.closed = True


class _FakeTlsSocket:
    def __init__(self, raw):
        self.raw = raw
        self.timeouts = []
        self.closed = False

    def settimeout(self, value):
        self.timeouts.append(value)

    def close(self):
        self.closed = True


class _FakeTlsContext:
    check_hostname = True
    verify_mode = ssl.CERT_REQUIRED

    def __init__(self):
        self.server_hostname = None
        self.raw = None

    def wrap_socket(self, raw, *, server_hostname):
        self.raw = raw
        self.server_hostname = server_hostname
        return _FakeTlsSocket(raw)


def test_dial_connects_to_validated_ip_but_keeps_original_hostname_for_tls(monkeypatch):
    raw = _FakeRawSocket()
    context = _FakeTlsContext()

    def socket_factory(family, sock_type, proto):
        assert family == socket.AF_INET
        assert sock_type == socket.SOCK_STREAM
        assert proto == socket.IPPROTO_TCP
        return raw

    monkeypatch.setattr(transport_module.socket, "socket", socket_factory)
    monkeypatch.setattr(transport_module.ssl, "create_default_context", lambda: context)

    configured = policy()
    validated = configured.validate_target("https://docs.example.com/guide", [PUBLIC_V4_A])
    tls = transport_module._dial_pinned_tls(
        validated,
        PUBLIC_V4_A,
        connect_timeout_seconds=2.0,
    )

    assert raw.connected == (PUBLIC_V4_A, 443)
    assert context.server_hostname == "docs.example.com"
    assert context.raw is raw
    assert tls.raw is raw


def test_transport_revalidates_target_instead_of_trusting_constructed_dataclass(monkeypatch):
    forged = ValidatedFetchTarget(
        url="https://docs.example.com/",
        host="docs.example.com",
        port=443,
        resolved_ips=("127.0.0.1",),
    )
    called = False

    def should_not_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network request should not run")

    monkeypatch.setattr(transport_module, "_request_to_ip", should_not_run)
    with pytest.raises(FetchPolicyError, match="unsafe"):
        PinnedHttpsTransport().get(forged, policy=policy())
    assert called is False


def test_get_request_has_pinned_host_identity_and_no_ambient_credentials():
    configured = policy()
    validated = configured.validate_target(
        "https://docs.example.com/a b",
        [PUBLIC_V4_A],
    )
    request = transport_module._build_get_request(validated, policy=configured).decode("ascii")

    assert request.startswith("GET /a%20b HTTP/1.1\r\n")
    assert "\r\nHost: docs.example.com\r\n" in request
    assert "\r\nAccept-Encoding: identity\r\n" in request
    assert "Authorization:" not in request
    assert "Cookie:" not in request
    assert "Proxy-Authorization:" not in request
    assert request.endswith("\r\n\r\n")


def test_transport_retries_only_ips_from_validated_answer_set(monkeypatch):
    configured = policy()
    validated = configured.validate_target(
        "https://docs.example.com/",
        [PUBLIC_V4_A, PUBLIC_V4_B],
    )
    attempted = []

    def fake_request(target_arg, ip, **kwargs):
        attempted.append(ip)
        if ip == PUBLIC_V4_A:
            raise transport_module._EndpointUnavailable("first endpoint unavailable")
        return transport_module._WireResponse(
            status=200,
            headers=(("content-type", "text/plain"),),
            body=b"ok",
        )

    monkeypatch.setattr(transport_module, "_request_to_ip", fake_request)
    result = PinnedHttpsTransport().get(validated, policy=configured)

    assert attempted == [PUBLIC_V4_A, PUBLIC_V4_B]
    assert result.connected_ip == PUBLIC_V4_B
    assert result.body == b"ok"
    assert result.content_type == "text/plain"


def test_transport_does_not_follow_redirects(monkeypatch):
    configured = policy(max_redirects=3)
    validated = configured.validate_target("https://docs.example.com/a", [PUBLIC_V4_A])
    calls = 0

    def fake_request(*args, **kwargs):
        nonlocal calls
        calls += 1
        return transport_module._WireResponse(
            status=302,
            headers=(("location", "/b"),),
            body=b"",
        )

    monkeypatch.setattr(transport_module, "_request_to_ip", fake_request)
    result = PinnedHttpsTransport().get(validated, policy=configured)

    assert calls == 1
    assert result.status == 302
    assert result.header_values("Location") == ("/b",)
    assert result.body == b""
    assert result.content_type is None


def test_transport_rejects_encoded_final_response(monkeypatch):
    configured = policy()
    validated = configured.validate_target("https://docs.example.com/", [PUBLIC_V4_A])

    monkeypatch.setattr(
        transport_module,
        "_request_to_ip",
        lambda *args, **kwargs: transport_module._WireResponse(
            status=200,
            headers=(("content-type", "text/plain"), ("content-encoding", "gzip")),
            body=b"compressed",
        ),
    )

    with pytest.raises(FetchTransportError, match="encoding"):
        PinnedHttpsTransport().get(validated, policy=configured)


class _FakeBodyResponse:
    def __init__(self, body: bytes):
        self._body = bytearray(body)

    def read(self, size: int) -> bytes:
        if not self._body:
            return b""
        chunk = bytes(self._body[:size])
        del self._body[:size]
        return chunk


class _TimeoutRecorder:
    def __init__(self):
        self.values = []

    def settimeout(self, value):
        self.values.append(value)


def test_streamed_body_aborts_when_actual_bytes_exceed_limit():
    response = _FakeBodyResponse(b"abcde")
    tls_socket = _TimeoutRecorder()

    with pytest.raises(FetchTransportError, match="byte limit"):
        transport_module._read_bounded_body(
            response,
            tls_socket,
            max_bytes=4,
            read_timeout_seconds=1.0,
            deadline=time.monotonic() + 5.0,
        )

    assert tls_socket.values


def test_streamed_body_rejects_truncated_declared_content_length():
    response = _FakeBodyResponse(b"abc")
    tls_socket = _TimeoutRecorder()

    with pytest.raises(FetchTransportError, match="Content-Length"):
        transport_module._read_bounded_body(
            response,
            tls_socket,
            max_bytes=10,
            read_timeout_seconds=1.0,
            deadline=time.monotonic() + 5.0,
            expected_bytes=4,
        )


def test_streamed_body_rejects_more_bytes_than_declared_content_length():
    response = _FakeBodyResponse(b"abcde")
    tls_socket = _TimeoutRecorder()

    with pytest.raises(FetchTransportError, match="Content-Length"):
        transport_module._read_bounded_body(
            response,
            tls_socket,
            max_bytes=10,
            read_timeout_seconds=1.0,
            deadline=time.monotonic() + 5.0,
            expected_bytes=4,
        )


def test_content_length_is_strict_bounded_and_returns_expected_size():
    assert transport_module._validate_content_length((("content-length", "4"),), 4) == 4
    assert transport_module._validate_content_length((), 4) is None

    with pytest.raises(FetchTransportError, match="byte limit"):
        transport_module._validate_content_length((("content-length", "5"),), 4)
    with pytest.raises(FetchTransportError, match="conflicting"):
        transport_module._validate_content_length(
            (("content-length", "4"), ("content-length", "5")),
            10,
        )
    with pytest.raises(FetchTransportError, match="invalid"):
        transport_module._validate_content_length((("content-length", "+4"),), 10)


def test_response_header_selection_discards_cookies_and_server_metadata():
    selected = transport_module._select_response_headers(
        (
            ("content-type", "text/plain"),
            ("location", "/next"),
            ("set-cookie", "session=secret"),
            ("server", "private-runtime-name"),
            ("x-internal-debug", "diagnostic"),
        )
    )

    assert selected == (("content-type", "text/plain"), ("location", "/next"))
