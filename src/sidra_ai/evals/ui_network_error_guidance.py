"""Does a request that never reaches the server say so in the operator's language?

C-1218: C-1211 taught the page to translate HTTP status codes, but a fetch
that gets no response at all - the loopback server crashed, was never
started, the connection dropped - rejects with a ``TypeError`` whose
message is an English browser string (「Failed to fetch」/「Load failed」).
The catch blocks showed that string verbatim: 「失敗: Failed to fetch」 in
an otherwise all-Japanese UI, with no hint that the fix is to start the
server. ``reason(error)`` now maps the network-level rejection to Japanese
guidance while our own HTTP-status errors (already Japanese) pass through.

Checks on the page source: ``reason`` exists and branches on ``TypeError``,
its message is Japanese and names the server, non-network errors keep their
own message, and every catch site routes through it. The end-to-end proof
(the real page aborting its ``/v1/chat`` shows the Japanese guidance) ran at
fix time and is recorded in the loop log.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UiNetworkErrorGuidanceResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_network_error_guidance() -> UiNetworkErrorGuidanceResult:
    from sidra_ai.api.ui import ASK_PAGE

    checks = 0
    failures: list[str] = []

    if "function reason(error)" in ASK_PAGE:
        checks += 1
    else:
        failures.append("no reason() helper for thrown errors")

    if "error instanceof TypeError" in ASK_PAGE:
        checks += 1
    else:
        failures.append("network rejections (TypeError) are not distinguished")

    if "サーバーに接続できません" in ASK_PAGE and "sidra-api" in ASK_PAGE:
        checks += 1
    else:
        failures.append("network guidance is missing or does not name the server")

    if "return error.message;" in ASK_PAGE:
        checks += 1
    else:
        failures.append("non-network errors lost their own message")

    # Every catch block that used to print a raw error.message must route
    # through reason(); none may show error.message directly again.
    if "+ error.message" not in ASK_PAGE:
        checks += 1
    else:
        failures.append("a catch site still shows the raw error.message")

    if ASK_PAGE.count("+ reason(error)") >= 5:
        checks += 1
    else:
        failures.append("fewer than five catch sites route through reason()")

    return UiNetworkErrorGuidanceResult(
        passed=not failures, checks_passed=checks, checks_total=6,
        failures=tuple(failures),
    )
