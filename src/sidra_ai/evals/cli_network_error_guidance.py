"""Does the ask CLI say what to do when the *transport* fails, not just HTTP?

C-1233: the CLI maps every reachable HTTP status to Japanese guidance
(C-1223) and gives specific advice for a refused connection and a timeout,
but the catch-all for every other transport failure printed 「要求に失敗した:
RemoteProtocolError」 - a raw English exception class name, with no next step.
A general user whose server drops mid-answer (the local model crashes, the
connection resets) or who mistypes ``--url ftp://…`` (UnsupportedProtocol)
got only the class name. It was the last unmapped failure class in the CLI.

The checks drive ``main`` with a transport that raises each error and confirm
the guidance appears and the exit is non-zero, while the still-specific
ConnectError and timeout branches keep their own advice.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr
from dataclasses import dataclass

import httpx


def _run_raising(exc: Exception) -> tuple[int, str]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    from sidra_ai.api.ask_cli import main

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x")
    err = io.StringIO()
    with redirect_stderr(err):
        code = main(["質問"], client=client)
    return code, err.getvalue()


@dataclass(frozen=True)
class CliNetworkErrorGuidanceResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_cli_network_error_guidance() -> CliNetworkErrorGuidanceResult:
    checks = 0
    failures: list[str] = []

    req = httpx.Request("POST", "http://x/v1/chat")

    # The catch-all failure classes: a peer that closed mid-response, a bad
    # --url scheme, and a lower-level protocol error. Each must get actionable
    # Japanese guidance, not a bare English class name, and a non-zero exit.
    catch_all = (
        ("RemoteProtocolError", httpx.RemoteProtocolError("peer closed", request=req)),
        ("UnsupportedProtocol", httpx.UnsupportedProtocol("bad scheme", request=req)),
        ("ProtocolError", httpx.ProtocolError("protocol", request=req)),
    )
    for name, exc in catch_all:
        rc, err = _run_raising(exc)
        if rc != 0:
            checks += 1
        else:
            failures.append(f"{name}: exit code was 0, not a failure")
        if "確認する" in err:
            checks += 1
        else:
            failures.append(f"{name}: no Japanese guidance said what to do next")

    # Regression: the two classes that already had their own advice keep it -
    # the catch-all reword must not swallow them.
    rc, err = _run_raising(httpx.ConnectError("refused", request=req))
    if rc != 0 and "接続できない" in err:
        checks += 1
    else:
        failures.append("ConnectError lost its specific guidance")

    rc, err = _run_raising(httpx.ConnectTimeout("slow", request=req))
    if rc != 0 and "応答が無かった" in err:
        checks += 1
    else:
        failures.append("timeout lost its specific guidance")

    return CliNetworkErrorGuidanceResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=8,
        failures=tuple(failures),
    )
