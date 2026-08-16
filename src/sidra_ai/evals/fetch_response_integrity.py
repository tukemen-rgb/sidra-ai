"""Offline release-gate checks for bounded Fetch Plane response integrity."""

from __future__ import annotations

import time

from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.fetch.transport import FetchTransportError, _read_bounded_body


class _ResponseStub:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self._offset = 0

    def read(self, size: int) -> bytes:
        if size <= 0 or self._offset >= len(self._body):
            return b""
        end = min(self._offset + size, len(self._body))
        chunk = self._body[self._offset:end]
        self._offset = end
        return chunk


class _SocketStub:
    def settimeout(self, timeout: float) -> None:
        if timeout <= 0:
            raise AssertionError("fetch eval received a non-positive read timeout")


def _read(body: bytes, *, expected_bytes: int | None, max_bytes: int) -> bytes:
    return _read_bounded_body(
        _ResponseStub(body),
        _SocketStub(),
        max_bytes=max_bytes,
        read_timeout_seconds=1.0,
        deadline=time.monotonic() + 5.0,
        expected_bytes=expected_bytes,
    )


def run_fetch_response_integrity_suite() -> tuple[EvalOutcome, ...]:
    """Require truncated, overlong, and over-limit fetch bodies to fail closed."""

    failures: list[str] = []

    try:
        exact = _read(b"data", expected_bytes=4, max_bytes=16)
    except FetchTransportError as exc:
        failures.append(f"exact Content-Length body was rejected: {type(exc).__name__}")
    else:
        if exact != b"data":
            failures.append("exact Content-Length body was altered")

    for label, body, expected, maximum in (
        ("truncated", b"dat", 4, 16),
        ("overlong", b"data!", 4, 16),
        ("byte_limit", b"data!", None, 4),
    ):
        try:
            _read(body, expected_bytes=expected, max_bytes=maximum)
        except FetchTransportError:
            continue
        failures.append(f"{label} fetch response was accepted")

    return (
        EvalOutcome(
            case_name="fetch_response_integrity_fails_closed",
            passed=not failures,
            detail="Content-Length and streaming byte ceilings checked offline",
            failures=tuple(failures),
        ),
    )
