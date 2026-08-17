import time

import pytest

import sidra_ai.fetch.transport as transport_module
from sidra_ai.fetch import FetchTransportError


class _FakeTlsSocket:
    def __init__(self):
        self.timeouts = []
        self.shutdown_calls = []
        self.closed = False

    def settimeout(self, value):
        self.timeouts.append(value)

    def shutdown(self, how):
        self.shutdown_calls.append(how)
        self.closed = True

    def close(self):
        self.closed = True


class _HeaderResponse:
    def __init__(self, sock, *, fail_when_closed=False):
        self.sock = sock
        self.fail_when_closed = fail_when_closed
        self.begun = False

    def begin(self):
        self.begun = True
        if self.fail_when_closed and self.sock.closed:
            raise OSError("socket closed by deadline watchdog")


class _ImmediateTimer:
    instances = []

    def __init__(self, interval, function):
        self.interval = interval
        self.function = function
        self.daemon = False
        self.cancelled = False
        type(self).instances.append(self)

    def start(self):
        self.function()

    def cancel(self):
        self.cancelled = True


class _RecordingTimer:
    instances = []

    def __init__(self, interval, function):
        self.interval = interval
        self.function = function
        self.daemon = False
        self.started = False
        self.cancelled = False
        type(self).instances.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


def test_header_phase_watchdog_fails_closed_when_absolute_deadline_fires(monkeypatch):
    _ImmediateTimer.instances.clear()
    monkeypatch.setattr(transport_module.threading, "Timer", _ImmediateTimer)
    sock = _FakeTlsSocket()
    response = _HeaderResponse(sock, fail_when_closed=True)

    with pytest.raises(FetchTransportError, match="overall fetch timeout exceeded"):
        transport_module._begin_response_with_deadline(
            response,
            sock,
            read_timeout_seconds=10.0,
            deadline=time.monotonic() + 5.0,
        )

    assert response.begun is True
    assert sock.closed is True
    assert sock.shutdown_calls == [transport_module.socket.SHUT_RDWR]
    assert len(_ImmediateTimer.instances) == 1
    timer = _ImmediateTimer.instances[0]
    assert 0 < timer.interval <= 5.0
    assert timer.daemon is True
    assert timer.cancelled is True


def test_header_phase_cancels_watchdog_after_successful_parse(monkeypatch):
    _RecordingTimer.instances.clear()
    monkeypatch.setattr(transport_module.threading, "Timer", _RecordingTimer)
    sock = _FakeTlsSocket()
    response = _HeaderResponse(sock)

    transport_module._begin_response_with_deadline(
        response,
        sock,
        read_timeout_seconds=1.0,
        deadline=time.monotonic() + 5.0,
    )

    assert response.begun is True
    assert sock.closed is False
    assert sock.timeouts
    assert 0 < sock.timeouts[-1] <= 1.0
    assert len(_RecordingTimer.instances) == 1
    timer = _RecordingTimer.instances[0]
    assert timer.started is True
    assert timer.daemon is True
    assert timer.cancelled is True
