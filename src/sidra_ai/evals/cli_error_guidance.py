"""Does the ask CLI say what to do when a request fails?

C-1223: the web page maps each reachable HTTP status class to Japanese
guidance (C-1211/C-1218), but ``sidra-ask`` only special-cased 401 and 429.
A too-long question - the most common 422 a terminal user hits - printed a
bare 「API がエラーを返した: HTTP 422」 with no next step. The CLI now maps
403, 413/422 and 5xx to guidance as well, with the code still printed for
debugging and the response body still unread.

The checks drive ``main`` with a mock transport that returns each status and
a secret-bearing body, and confirm the guidance appears, the code is shown,
the exit is non-zero, and the body never reaches the operator.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr
from dataclasses import dataclass

import httpx

_SECRET = "SECRET-BODY-DO-NOT-PRINT"


def _run(status: int) -> tuple[int, str]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": _SECRET})

    from sidra_ai.api.ask_cli import main

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x")
    err = io.StringIO()
    with redirect_stderr(err):
        code = main(["質問"], client=client)
    return code, err.getvalue()


@dataclass(frozen=True)
class CliErrorGuidanceResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_cli_error_guidance() -> CliErrorGuidanceResult:
    checks = 0
    failures: list[str] = []

    cases = (
        (403, ("トークン", "権限"), "403"),
        (422, ("短く", "再送"), "422"),
        (413, ("短く", "再送"), "413"),
        (500, ("サーバ", "再試行"), "500"),
    )
    for status, needles, code in cases:
        rc, err = _run(status)
        if rc != 0:
            checks += 1
        else:
            failures.append(f"HTTP {status}: exit code was 0, not a failure")
        if any(n in err for n in needles):
            checks += 1
        else:
            failures.append(f"HTTP {status}: no guidance said what to do next")
        if code in err:
            checks += 1
        else:
            failures.append(f"HTTP {status}: the status code is not printed for debugging")
        if _SECRET not in err:
            checks += 1
        else:
            failures.append(f"HTTP {status}: the response body leaked to stderr")

    return CliErrorGuidanceResult(
        passed=not failures, checks_passed=checks, checks_total=len(cases) * 4,
        failures=tuple(failures),
    )
