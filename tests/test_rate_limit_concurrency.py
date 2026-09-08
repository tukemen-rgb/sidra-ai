"""A limit that only holds when requests arrive one at a time is not a limit.

The chat route is a synchronous endpoint, so requests are served from a thread
pool and several can be inside ``check`` at once. Its shape is check-then-act:
read how many hits are in the window, decide, then append. The interpreter may
switch threads between the reading and the appending, and every thread that
read the length before any of them appended is let through.

Measured on the unlocked version by shortening the interpreter's switch
interval - which does not create the window, only makes it likely enough to
observe: **64 threads against a limit of 60 let 100 requests through**.

The switch interval is restored afterwards. Leaving it short would make every
later test in the same process slower and flakier, which is a good way to turn
one honest test into a suite nobody trusts.

**How reliable this is, measured rather than hoped.** With the lock in place
these passed six runs out of six. With the lock removed they failed on about
two runs in three - the race is probabilistic, so a test for it is too. That
asymmetry is the one that matters: a test that never fails on correct code and
usually fails on broken code is worth having; the reverse would not be.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.api.app import RateLimiter  # noqa: E402

_LIMIT = 60
_THREADS = 64
_EACH = 40


@pytest.fixture
def preemptive():
    """Make thread switches frequent enough for the window to show."""

    original = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        yield
    finally:
        sys.setswitchinterval(original)


def _hammer(limiter: RateLimiter, client: str) -> int:
    allowed = [0]
    guard = threading.Lock()
    ready = threading.Barrier(_THREADS)

    def run() -> None:
        ready.wait(timeout=30)
        mine = 0
        for _ in range(_EACH):
            if limiter.check(client):
                mine += 1
        with guard:
            allowed[0] += mine

    threads = [threading.Thread(target=run) for _ in range(_THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return allowed[0]


def test_the_limit_holds_when_every_request_arrives_at_once(preemptive) -> None:
    limiter = RateLimiter(_LIMIT)

    assert _hammer(limiter, "one-client") <= _LIMIT


def test_the_window_never_holds_more_hits_than_the_limit(preemptive) -> None:
    """The counter itself, not only what it returned - an over-full window
    would keep refusing afterwards for longer than it should."""

    limiter = RateLimiter(_LIMIT)
    _hammer(limiter, "one-client")

    assert len(limiter._hits["one-client"]) <= _LIMIT


def test_the_client_map_stays_bounded_under_concurrent_new_clients(
    preemptive,
) -> None:
    """The bound is what keeps an unknown client from growing memory; it is
    decided by the same read-then-write shape."""

    limiter = RateLimiter(_LIMIT, max_clients=50)
    errors: list[str] = []
    ready = threading.Barrier(16)

    def run(worker: int) -> None:
        try:
            ready.wait(timeout=30)
            for i in range(80):
                limiter.check(f"c{worker}-{i}")
        except Exception as exc:  # noqa: BLE001 - a raise here is the finding
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=run, args=(w,)) for w in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors
    assert len(limiter._hits) <= 50


def test_one_client_at_a_time_is_unaffected() -> None:
    """The fix must not change the behaviour everything else relies on."""

    limiter = RateLimiter(3)

    assert [limiter.check("solo") for _ in range(5)] == [
        True,
        True,
        True,
        False,
        False,
    ]
