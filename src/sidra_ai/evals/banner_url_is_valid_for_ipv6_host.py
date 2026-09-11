"""Does the ``sidra-api`` startup banner print a valid URL for an IPv6 host?

C-1679. ``::1`` is an accepted loopback host, but ``_print_banner`` built the
address as ``f"http://{host}:{port}"`` - so it printed ``http://::1:8000``, which
no browser can parse (IPv6 needs brackets). The ask CLI's ``base_url`` already
brackets it (``http://[::1]:8000``); the banner is the "open this address" line
a user copies right after starting the server, so it must be a valid URL too.

The checks drive ``_print_banner`` and pull its first line: an IPv6 host must be
bracketed and parse back to that host, an IPv4 host must be unchanged, and the
banner URL must agree with ``base_url``.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass
from urllib.parse import urlsplit


def _banner_url(host: str, port: int = 8000) -> str:
    from sidra_ai.api.server import _print_banner
    from sidra_ai.config.settings import Settings

    settings = Settings(host=host, port=port, model_backend="echo")
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        _print_banner(settings)
    first = out.getvalue().splitlines()[0]
    # "SIDRA AI  http://<addr>  (scope)" -> the http token
    for token in first.split():
        if token.startswith("http://"):
            return token
    return ""


@dataclass(frozen=True)
class BannerUrlResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_banner_url_is_valid_for_ipv6_host() -> BannerUrlResult:
    from sidra_ai.api.ask_cli import base_url
    from sidra_ai.config.settings import Settings

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    def _hostname(u):
        try:
            return urlsplit(u).hostname
        except ValueError:
            return None

    def _port(u):
        try:
            return urlsplit(u).port
        except ValueError:  # a malformed URL (unbracketed IPv6) cannot be parsed
            return None

    # --- (A) an IPv6 host is bracketed and parses back to ::1 ---
    url = _banner_url("::1")
    add("[::1]" in url, f"A: IPv6 host not bracketed: {url!r}")
    add(_hostname(url) == "::1", f"A: IPv6 URL does not parse to ::1: {url!r}")
    add(_port(url) == 8000, f"A: IPv6 URL lost its port (unparseable): {url!r}")

    # --- (B) an IPv4 host is unchanged (no brackets) ---
    url4 = _banner_url("127.0.0.1")
    add(url4 == "http://127.0.0.1:8000",
        f"B: IPv4 banner URL changed: {url4!r}")

    # --- (C) the banner agrees with the CLI's base_url ---
    s6 = Settings(host="::1", port=8000, model_backend="echo")
    add(_banner_url("::1") == base_url(s6, None),
        f"C: banner {_banner_url('::1')!r} != base_url {base_url(s6, None)!r}")
    s4 = Settings(host="127.0.0.1", port=8000, model_backend="echo")
    add(_banner_url("127.0.0.1") == base_url(s4, None),
        f"C: banner {_banner_url('127.0.0.1')!r} != base_url {base_url(s4, None)!r}")

    total = 6
    return BannerUrlResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["BannerUrlResult", "evaluate_banner_url_is_valid_for_ipv6_host"]
