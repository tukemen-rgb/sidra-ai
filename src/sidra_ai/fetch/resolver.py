from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
from queue import Empty, Queue
import socket
import threading
from typing import Callable, Iterable, Sequence


class FetchDnsError(RuntimeError):
    """Raised when DNS resolution cannot produce one bounded, trustworthy answer set."""


_GetAddrInfo = Callable[[str, int, int, int, int], Sequence[tuple]]


@dataclass(slots=True)
class BoundedDnsResolver:
    """Resolve one canonical hostname without allowing unbounded DNS work.

    The resolver deliberately does not decide whether an address is safe to fetch.
    It returns the complete bounded A/AAAA set to ``FetchPolicy``, which must reject
    the whole request if any usable address is unsafe.

    ``socket.getaddrinfo`` has no portable per-call timeout, so each lookup runs in a
    daemon worker behind a bounded semaphore. A timed-out worker keeps its permit
    until it actually exits. Repeated stuck lookups therefore degrade to fail-closed
    "busy" errors instead of creating an unbounded number of resolver threads.
    """

    timeout_seconds: float = 2.0
    max_addresses: int = 16
    max_inflight: int = 2
    lookup: _GetAddrInfo = socket.getaddrinfo
    _permits: threading.BoundedSemaphore = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise FetchDnsError("DNS timeout must be positive")
        if self.max_addresses <= 0:
            raise FetchDnsError("DNS address limit must be positive")
        if self.max_inflight <= 0:
            raise FetchDnsError("DNS inflight limit must be positive")
        self._permits = threading.BoundedSemaphore(self.max_inflight)

    def resolve(self, host: str, *, port: int = 443) -> tuple[str, ...]:
        """Return the bounded canonical A/AAAA answer set for one validated host.

        ``host`` must already be the normalized ASCII hostname produced by the Fetch
        policy layer. This method rejects inputs that would make the resolver apply a
        second, potentially different normalization rule.
        """

        canonical_host = _require_canonical_host(host)
        if port != 443:
            raise FetchDnsError("DNS resolver only supports port 443")
        if not self._permits.acquire(blocking=False):
            raise FetchDnsError("DNS resolver is busy")

        result: Queue[tuple[bool, object]] = Queue(maxsize=1)

        def worker() -> None:
            try:
                rows = self.lookup(
                    canonical_host,
                    port,
                    socket.AF_UNSPEC,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                )
            except Exception as exc:  # pragma: no cover - exact resolver failures vary by OS
                payload: tuple[bool, object] = (False, exc)
            else:
                payload = (True, rows)
            finally:
                self._permits.release()
            try:
                result.put_nowait(payload)
            except Exception:
                # The caller may already have timed out. The result must not keep the
                # daemon worker alive or turn a DNS failure into a process-lifetime leak.
                pass

        thread = threading.Thread(target=worker, name="sidra-fetch-dns", daemon=True)
        thread.start()
        thread.join(self.timeout_seconds)
        if thread.is_alive():
            raise FetchDnsError("DNS resolution timed out")

        try:
            ok, payload = result.get_nowait()
        except Empty as exc:  # defensive: a completed worker must publish exactly once
            raise FetchDnsError("DNS resolution failed") from exc
        if not ok:
            raise FetchDnsError("DNS resolution failed")

        return _extract_addresses(payload, max_addresses=self.max_addresses)


def _require_canonical_host(host: str) -> str:
    if not isinstance(host, str) or not host:
        raise FetchDnsError("DNS hostname is required")
    if host != host.strip().lower().rstrip("."):
        raise FetchDnsError("DNS hostname must already be canonical")
    try:
        host.encode("ascii")
    except UnicodeEncodeError as exc:
        raise FetchDnsError("DNS hostname must be ASCII") from exc
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise FetchDnsError("DNS hostname cannot be an IP literal")


def _extract_addresses(rows: object, *, max_addresses: int) -> tuple[str, ...]:
    if not isinstance(rows, Iterable):
        raise FetchDnsError("DNS resolver returned an invalid result")

    addresses: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, tuple) or len(row) < 5:
            raise FetchDnsError("DNS resolver returned an invalid result")
        family = row[0]
        sockaddr = row[4]
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        if not isinstance(sockaddr, tuple) or not sockaddr or not isinstance(sockaddr[0], str):
            raise FetchDnsError("DNS resolver returned an invalid result")
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except ValueError as exc:
            raise FetchDnsError("DNS resolver returned an invalid address") from exc
        if family == socket.AF_INET and not isinstance(address, ipaddress.IPv4Address):
            raise FetchDnsError("DNS resolver returned an address-family mismatch")
        if family == socket.AF_INET6 and not isinstance(address, ipaddress.IPv6Address):
            raise FetchDnsError("DNS resolver returned an address-family mismatch")

        text = str(address)
        if text in seen:
            continue
        seen.add(text)
        addresses.append(text)
        if len(addresses) > max_addresses:
            # Never truncate: an ignored later answer could be private/metadata and the
            # policy contract requires the entire usable answer set to be checked.
            raise FetchDnsError("DNS answer set exceeds limit")

    if not addresses:
        raise FetchDnsError("DNS answer set is empty")
    return tuple(addresses)
