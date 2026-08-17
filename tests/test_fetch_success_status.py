import time

import pytest

from sidra_ai.fetch import FetchPolicy, FetchTransportError, PinnedHttpsTransport
import sidra_ai.fetch.transport as transport_module


PUBLIC_V4 = "93.184.216.34"


def _policy():
    return FetchPolicy(allowed_hosts=frozenset({"docs.example.com"}))


def _target():
    configured = _policy()
    return configured, configured.validate_target(
        "https://docs.example.com/reference",
        [PUBLIC_V4],
    )


@pytest.mark.parametrize("status", [201, 202, 204, 206])
def test_transport_rejects_non_200_success_statuses(monkeypatch, status):
    configured, validated = _target()

    monkeypatch.setattr(
        transport_module,
        "_request_to_ip",
        lambda *args, **kwargs: transport_module._WireResponse(
            status=status,
            headers=(("content-type", "text/plain"),),
            body=b"partial-or-unsupported",
        ),
    )

    with pytest.raises(FetchTransportError, match="non-200 success"):
        PinnedHttpsTransport().get(validated, policy=configured)


class _FakeTlsSocket:
    def __init__(self):
        self.sent = []
        self.timeouts = []
        self.closed = False

    def settimeout(self, value):
        self.timeouts.append(value)

    def sendall(self, value):
        self.sent.append(value)

    def close(self):
        self.closed = True


class _FakePartialResponse:
    status = 206

    def __init__(self, *args, **kwargs):
        self.closed = False
        self.read_called = False

    def begin(self):
        return None

    def getheaders(self):
        return (("Content-Type", "text/plain"), ("Content-Length", "4"))

    def read(self, size):
        self.read_called = True
        raise AssertionError("partial 2xx body must not be consumed")

    def close(self):
        self.closed = True


def test_pinned_request_rejects_206_before_reading_body(monkeypatch):
    configured, validated = _target()
    tls = _FakeTlsSocket()
    response = _FakePartialResponse()

    monkeypatch.setattr(transport_module, "_dial_pinned_tls", lambda *args, **kwargs: tls)
    monkeypatch.setattr(transport_module.http.client, "HTTPResponse", lambda *args, **kwargs: response)

    with pytest.raises(FetchTransportError, match="non-200 success"):
        transport_module._request_to_ip(
            validated,
            PUBLIC_V4,
            policy=configured,
            connect_timeout_seconds=1.0,
            read_timeout_seconds=1.0,
            deadline=time.monotonic() + 5.0,
        )

    assert response.read_called is False
    assert tls.sent
    assert tls.closed is True
