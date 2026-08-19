"""Keep the index current without a human poking it.

Until now the index only advanced when somebody called
``POST /v1/github/analyze``. A self-hosted assistant answering from "whatever
was true the last time someone remembered" is the failure this closes.

Three properties are deliberate:

*It never invokes the model.* The endpoint summarizes what changed; this
refresher only ingests. A background job that quietly spends inference on a
summary nobody reads is worse than no refresher, and "skips the model when
nothing changed" is a weaker promise than "cannot reach the model at all".

*It is off unless configured.* ``ingest_interval_seconds`` defaults to 0.
Outbound polling that starts because a server was upgraded is a surprise.

*It cannot take the API down with it.* Ingestion runs on its own thread, and
every failure is caught and counted rather than raised. An API that stops
serving because a background refresh failed has traded a stale answer for no
answer, which is the worse trade.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RefreshStatus:
    """What the refresher has done, in metadata only.

    Deliberately free of repository names, paths and exception text: this is
    read by callers that may be less trusted than the ingestion path itself,
    and a status object is a poor place to learn the topology. The error
    *type* is kept because "it is failing" and "it is failing this way" are
    different operational facts; the message is not.
    """

    enabled: bool = False
    running: bool = False
    interval_seconds: int = 0
    runs: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    last_run_at: str = ""
    last_success_at: str = ""
    last_error_type: str = ""
    repositories_changed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "running": self.running,
            "interval_seconds": self.interval_seconds,
            "runs": self.runs,
            "failures": self.failures,
            "consecutive_failures": self.consecutive_failures,
            "last_run_at": self.last_run_at,
            "last_success_at": self.last_success_at,
            "last_error_type": self.last_error_type,
            "repositories_changed": self.repositories_changed,
        }


@dataclass
class BackgroundRefresher:
    """Run differential ingestion on an interval, on its own thread.

    A thread rather than an asyncio task because ingestion is blocking I/O
    plus CPU-bound screening; on the event loop it would stall every request
    for the length of a fetch.
    """

    ingest: Callable[[], Any]
    """Called once per tick. Must ingest only - never reach the model."""

    interval_seconds: int
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _status: RefreshStatus = field(default_factory=RefreshStatus, repr=False)

    def __post_init__(self) -> None:
        self._status.enabled = self.interval_seconds > 0
        self._status.interval_seconds = self.interval_seconds

    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self.interval_seconds > 0

    def status(self) -> RefreshStatus:
        """A snapshot, so a caller cannot observe a half-updated tick."""

        with self._lock:
            return RefreshStatus(**vars(self._status))

    # ------------------------------------------------------------------
    def start(self) -> bool:
        """Start the loop. Returns whether a thread is now running.

        Disabled is a normal outcome, not an error: the API must come up the
        same way either way.
        """

        if not self.enabled or self._thread is not None:
            return self._thread is not None
        self._stop.clear()
        thread = threading.Thread(
            target=self._loop, name="sidra-ingest-refresher", daemon=True
        )
        self._thread = thread
        with self._lock:
            self._status.running = True
        thread.start()
        return True

    def stop(self, timeout: float = 5.0) -> None:
        """Ask the loop to finish the current tick and exit."""

        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=timeout)
        with self._lock:
            self._status.running = False

    # ------------------------------------------------------------------
    def _loop(self) -> None:
        # Wait before the first tick. Startup is when a supervisor is most
        # likely to be restarting repeatedly, and a refresh on every start
        # would turn a crash loop into a request flood.
        while not self._stop.wait(self.interval_seconds):
            self.run_once()

    def run_once(self) -> RefreshStatus:
        """One tick. Never raises: a failed refresh is recorded, not fatal."""

        changed = 0
        error_type = ""
        try:
            report = self.ingest()
            changed = sum(
                1 for r in getattr(report, "repositories", ()) if getattr(r, "changed", False)
            )
        except Exception as exc:  # noqa: BLE001 - the loop must outlive a failure
            error_type = type(exc).__name__

        now = _utcnow().isoformat()
        with self._lock:
            self._status.runs += 1
            self._status.last_run_at = now
            if error_type:
                self._status.failures += 1
                self._status.consecutive_failures += 1
                self._status.last_error_type = error_type
            else:
                self._status.consecutive_failures = 0
                self._status.last_error_type = ""
                self._status.last_success_at = now
                self._status.repositories_changed += changed
            return RefreshStatus(**vars(self._status))
