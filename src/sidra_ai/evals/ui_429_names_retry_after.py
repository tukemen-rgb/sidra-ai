"""Does the web UI tell the reader *how long* to wait on a rate limit?

C-1721. On a 429 the server sends ``Retry-After`` with the exact seconds until the
client may retry. The CLI names them (C-1718), but the web UI's ``explain(status)``
mapped 429 to a flat 「混み合っています。少し待ってからもう一度お試しください」 - it
never looked at the header, so the browser reader (the surface most operators use)
could not tell a 2-second wait from a 60-second one. ``explain`` now takes the
``Retry-After`` value and names the seconds when it is an integer count, and the
fetch call sites pass it.

The check extracts the real ``explain`` from the entry page and runs it in node:
the seconds are named for an integer Retry-After, a missing or non-integer value
falls back to the vague wording (no bogus number), the HTTP 429 code is still
shown, other statuses are unchanged, and the submit path is wired to pass the
header.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass


def _ask_page() -> str:
    from sidra_ai.api.ui import ASK_PAGE

    return ASK_PAGE


def _run_explain(cases: list[list]) -> list[str]:
    """Extract ``explain`` from the entry page and run it in node on ``cases``."""

    page = _ask_page()
    match = re.search(r"function explain\(.*?\n  \}", page, re.DOTALL)
    if not match:
        raise AssertionError("could not find the explain() function in ASK_PAGE")
    snippet = match.group(0)
    program = snippet + "\nconsole.log(JSON.stringify(" + json.dumps(cases) + ".map(function(a){return explain.apply(null,a);})));\n"
    out = subprocess.run(
        ["node", "-e", program], capture_output=True, text=True, timeout=30
    )
    if out.returncode != 0:
        raise AssertionError(f"node failed: {out.stderr[-300:]}")
    return json.loads(out.stdout.strip().splitlines()[-1])


@dataclass(frozen=True)
class Ui429RetryResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_429_names_retry_after() -> Ui429RetryResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # explain(429,"37"), explain(429,null), explain(429,<date>), explain(422,null), explain(500,null)
    date = "Wed, 21 Oct 2026 07:28:00 GMT"
    named, missing, malformed, r422, r500 = _run_explain(
        [[429, "37"], [429, None], [429, date], [422, None], [500, None]]
    )

    # --- (A) an integer Retry-After is named (the number) ---
    add("37" in named, f"A: the retry-after seconds were not named: {named!r}")

    # --- (B) it reads as a duration, with the 秒 unit ---
    add("秒" in named, f"B: the retry-after had no 秒 unit: {named!r}")

    # --- (C) the HTTP 429 code is still shown ---
    add("429" in named, f"C: the HTTP 429 code was dropped: {named!r}")

    # --- (D) a missing Retry-After falls back to the vague wording, no seconds ---
    add("少し待って" in missing and "秒待って" not in missing,
        f"D: a missing Retry-After did not fall back cleanly: {missing!r}")

    # --- (E) a non-integer Retry-After (an HTTP-date) shows no bogus number ---
    add("少し待って" in malformed and "2026" not in malformed and "秒待って" not in malformed,
        f"E: a non-integer Retry-After leaked a bogus wait: {malformed!r}")

    # --- (F) other statuses are unchanged and the submit path is wired ---
    wired = 'explain(response.status, response.headers.get("Retry-After"))' in _ask_page()
    add("短くして" in r422 and "サーバ" in r500 and wired,
        f"F: another status regressed or the header is not wired: 422={r422!r} 500={r500!r} wired={wired}")

    total = 6
    return Ui429RetryResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["Ui429RetryResult", "evaluate_ui_429_names_retry_after"]
