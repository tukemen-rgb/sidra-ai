"""Is a --url without a scheme caught as bad usage, not a transport failure?

C-1936, one knob along from C-1673. ``--top-k``/``--timeout``/``--repository``
are each checked before a request is built, so a bad value names the knob and
exits 2 (bad usage) instead of being sent and misread. ``--url`` was the one
client-visible knob left out: ``base_url`` passes a schemeless value through
unchanged, httpx raises ``UnsupportedProtocol`` at request time, and that fell
into the generic ``httpx.HTTPError`` branch beside real transport failures -
printing 「通信に失敗した…（UnsupportedProtocol）」 at exit 1. So a host:port a
user pasted without the ``http://`` read as a backend outage (exit 1, the code a
monitor pages on), with a message about a dropped connection when nothing was
sent, and the fix (add a scheme) never named.

This drives the real ``main`` with a real client for the schemeless cases (so
the pre-fix ``UnsupportedProtocol`` path is exercised, not mocked away) and a
stub client for the valid-scheme controls, asserting a schemeless --url exits 2
and names the scheme fix, while a well-formed --url (any case) and the default
host:port path are untouched.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass

#: Values a user reaches for that lack a usable scheme: a pasted host:port, a
#: bare host, and a scheme httpx does not speak.
SCHEMELESS: tuple[str, ...] = (
    "example.com:1234",
    "127.0.0.1:8787",
    "myhost",
    "ftp://host:21",
)

#: Well-formed targets, including an upper-case scheme httpx accepts - the fix
#: must not reject these.
WELL_FORMED: tuple[str, ...] = (
    "http://host:9999",
    "https://host",
    "HTTP://host:9999",
)

#: A fragment unique to the new scheme message, used to assert it is/ isn't shown.
_SCHEME_HINT = "http:// か https://"
_TRANSPORT_LINE = "通信に失敗した"


@dataclass(frozen=True)
class CliUrlSchemeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


class _Resp:
    status_code = 200

    def json(self) -> dict:
        return {"refused": False, "answer": "回答です。", "refusal": "",
                "security": {"decision": "allow"}, "model": {"backend": "echo"},
                "citations": []}


class _StubClient:
    """Answers any request 200 - the valid-scheme controls must not hit a network."""

    def __init__(self) -> None:
        self.headers: dict = {}

    def post(self, *a, **k) -> _Resp:
        return _Resp()

    def close(self) -> None:
        pass


def _run(argv: list[str], client) -> tuple[int, str]:
    from sidra_ai.api import ask_cli
    from sidra_ai.config.settings import Settings

    original = ask_cli.get_settings
    ask_cli.get_settings = lambda: Settings(
        data_dir="/tmp/sidra-c1936", host="127.0.0.1", port=8787
    )
    err = io.StringIO()
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = ask_cli.main(argv, client=client)
    finally:
        ask_cli.get_settings = original
    return code, err.getvalue()


def evaluate_cli_url_without_scheme_is_caught() -> CliUrlSchemeResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # (A) a schemeless --url is bad usage: exit 2, name the scheme fix, and do
    #     not surface it as a transport failure. Real client so the pre-fix
    #     UnsupportedProtocol path is genuinely exercised (not stubbed away).
    for u in SCHEMELESS:
        code, err = _run(["q", "--url", u], None)
        add(code == 2, f"A: {u!r} exit {code} (want 2, bad usage)")
        add(_SCHEME_HINT in err, f"A: {u!r} does not name the scheme fix: 「{err.strip()[:120]}」")
        add(_TRANSPORT_LINE not in err and "UnsupportedProtocol" not in err,
            f"A: {u!r} still reads as a transport failure: 「{err.strip()[:120]}」")

    # (B) a well-formed --url (any case) is untouched: it proceeds past the check
    #     to the request (stub answers 200 -> exit 0), and never sees the hint.
    for u in WELL_FORMED:
        code, err = _run(["q", "--url", u], _StubClient())
        add(code == 0, f"B: {u!r} exit {code} (want 0, should proceed)")
        add(_SCHEME_HINT not in err, f"B: {u!r} wrongly rejected: 「{err.strip()[:120]}」")

    # (C) no --url: the settings host:port path is well-formed and untouched.
    code, err = _run(["q"], _StubClient())
    add(code == 0, f"C: default path exit {code} (want 0)")
    add(_SCHEME_HINT not in err, "C: default path wrongly rejected")

    total = len(SCHEMELESS) * 3 + len(WELL_FORMED) * 2 + 2
    return CliUrlSchemeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "CliUrlSchemeResult",
    "evaluate_cli_url_without_scheme_is_caught",
]
