"""Does a CLI connection error name the knob the reader actually used?

C-1278: sidra-ask's ConnectError message always said 「SIDRA_HOST / SIDRA_PORT が
合っているか確認する」, even when the target came from ``--url``. Someone who
reached another port with ``--url`` was told to check env vars they never set.
The message now names ``--url`` when that flag was given and the env vars
otherwise; both keep the 「sidra-api を起動しているか」 check.

Measured by driving the real ``main`` with an injected client that raises
``httpx.ConnectError``, capturing stderr - the message the reader would see.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass


class _ConnectErrorClient:
    """Stands in for httpx.Client: every post fails to connect."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}

    def post(self, url: str, json=None):  # noqa: A002 - httpx's parameter name
        import httpx

        raise httpx.ConnectError("refused")


def _stderr_of(argv: list[str]) -> str:
    from sidra_ai.api.ask_cli import main

    buffer = io.StringIO()
    with contextlib.redirect_stderr(buffer):
        main(argv, client=_ConnectErrorClient())
    return buffer.getvalue()


@dataclass(frozen=True)
class CliConnectKnobResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_cli_connect_error_names_used_knob() -> CliConnectKnobResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --url given: the message names --url, not the env vars.
    with_url = _stderr_of(["質問", "--url", "http://127.0.0.1:8123/"])
    add("--url" in with_url, f"--url case: does not name --url in 「{with_url.strip()}」")
    add("SIDRA_HOST" not in with_url,
        f"--url case: still points at SIDRA_HOST/PORT in 「{with_url.strip()}」")
    add("接続できない" in with_url, f"--url case: not a connection error in 「{with_url.strip()}」")

    # default (no --url): the message names the env vars, not --url.
    default = _stderr_of(["質問"])
    add("SIDRA_HOST" in default and "SIDRA_PORT" in default,
        f"default case: does not name SIDRA_HOST/PORT in 「{default.strip()}」")
    add("--url" not in default,
        f"default case: names --url though it was not used in 「{default.strip()}」")

    total = 5
    return CliConnectKnobResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["CliConnectKnobResult", "evaluate_cli_connect_error_names_used_knob"]
