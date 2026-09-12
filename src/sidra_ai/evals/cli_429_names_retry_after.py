"""Does the ask CLI tell the reader *how long* to wait on a rate limit?

C-1718. On a 429 the server sends a ``Retry-After`` header with the exact number
of seconds until the client may retry (``app.py`` rate limiter). But ``sidra-ask``
printed a flat 「レート制限に当たった。少し待って再試行する。（HTTP 429）」 - it threw
the number away, so the reader could not tell a 2-second wait from a 60-second one,
and a script had nothing to ``sleep`` on. The CLI now names the seconds when the
header carries them, and keeps the vague wording only when it does not.

The checks drive ``main`` with a mock 429: the retry seconds are named, the code is
still shown, a missing or malformed ``Retry-After`` falls back to the old wording
(no bogus number, no crash), the exit stays non-zero, and the response body is
never printed.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr
from dataclasses import dataclass

import httpx

_SECRET = "SECRET-BODY-DO-NOT-PRINT"


def _run(retry_after: str | None) -> tuple[int, str]:
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"Retry-After": retry_after} if retry_after is not None else {}
        return httpx.Response(429, json={"detail": _SECRET}, headers=headers)

    from sidra_ai.api.ask_cli import main

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x")
    err = io.StringIO()
    with redirect_stderr(err):
        code = main(["質問"], client=client)
    return code, err.getvalue()


@dataclass(frozen=True)
class Cli429RetryResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_cli_429_names_retry_after() -> Cli429RetryResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    code_named, out_named = _run("37")

    # --- (A) the retry-after seconds are named (the number) ---
    add("37" in out_named, f"A: the retry-after seconds (37) were not named: {out_named!r}")

    # --- (B) they read as a duration, with the 秒 unit ---
    add("秒" in out_named, f"B: the retry-after had no 秒 unit: {out_named!r}")

    # --- (C) the HTTP 429 code is still shown (no regression) ---
    add("429" in out_named, f"C: the HTTP 429 code was dropped: {out_named!r}")

    # --- (D) a missing Retry-After falls back to the vague wording, no crash ---
    code_none, out_none = _run(None)
    add("少し待って" in out_none and "秒待って" not in out_none,
        f"D: a missing Retry-After did not fall back cleanly: {out_none!r}")

    # --- (E) a malformed Retry-After (an HTTP-date, say) shows no bogus number ---
    code_bad, out_bad = _run("Wed, 21 Oct 2026 07:28:00 GMT")
    add("少し待って" in out_bad and "秒待って" not in out_bad and "2026" not in out_bad,
        f"E: a malformed Retry-After leaked a bogus wait: {out_bad!r}")

    # --- (F) the exit stays non-zero and the response body is never printed ---
    add(code_named != 0 and code_none != 0 and code_bad != 0
        and _SECRET not in out_named and _SECRET not in out_none,
        f"F: a 429 mis-exited or leaked its body ({code_named},{code_none},{code_bad})")

    total = 6
    return Cli429RetryResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["Cli429RetryResult", "evaluate_cli_429_names_retry_after"]
