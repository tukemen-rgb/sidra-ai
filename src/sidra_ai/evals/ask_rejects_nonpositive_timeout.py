"""Does ``sidra-ask`` reject a non-positive ``--timeout`` cleanly?

C-1673. ``--timeout`` was passed to ``httpx.Client`` unvalidated. A negative
value makes the request raise ``ValueError: Timeout value out of range`` before
it even connects - which the CLI's try/except (only
``ConnectError``/``TimeoutException``/``HTTPError``) does not catch, so
``sidra-ask --timeout -5`` crashed with a raw Python traceback instead of the
Japanese guidance every other bad input gets. ``--timeout 0`` made every request
time out immediately and reported "cannot connect", misdirecting the reader.
``main`` now rejects ``--timeout <= 0`` client-side with exit 2.

The negative-timeout check runs against a real httpx client (no injected client,
no server needed - the ValueError is raised before any connection), so it
reproduces the actual crash. The zero/positive/default checks use a mock client
to see whether the request is refused before being sent.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass

import httpx


def _run_real(extra_argv):
    """main() with its own real httpx client; return (code, stderr, crashed)."""
    from sidra_ai.api import ask_cli
    from sidra_ai.config.settings import reset_settings_cache

    err = io.StringIO()
    crashed = None
    code: object = None
    try:
        reset_settings_cache()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            try:
                # A real client + an unused local URL: a negative timeout raises
                # ValueError before any connection, so no server is needed.
                code = ask_cli.main(
                    ["会社の休みは？", "--url", "http://127.0.0.1:9", *extra_argv]
                )
            except SystemExit as exc:
                code = exc.code
            except BaseException as exc:  # noqa: BLE001 - the bug is an uncaught raise
                crashed = f"{type(exc).__name__}: {exc}"
    finally:
        reset_settings_cache()
    return code, err.getvalue(), crashed


def _run_mock(extra_argv):
    """main() with a mock client; return (code, stderr, sent, crashed)."""
    from sidra_ai.api import ask_cli
    from sidra_ai.config.settings import reset_settings_cache

    sent = {"hit": False}

    def handler(request):
        sent["hit"] = True
        return httpx.Response(
            200,
            json={"answer": "月曜が定休です。", "refused": False, "citations": [],
                  "model": {"backend": "ollama"}, "creation": {"intent": "qa"}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    err = io.StringIO()
    crashed = None
    code: object = None
    try:
        reset_settings_cache()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            try:
                code = ask_cli.main(["会社の休みは？", *extra_argv], client=client)
            except SystemExit as exc:
                code = exc.code
            except BaseException as exc:  # noqa: BLE001
                crashed = f"{type(exc).__name__}: {exc}"
    finally:
        client.close()
        reset_settings_cache()
    return code, err.getvalue(), sent["hit"], crashed


@dataclass(frozen=True)
class AskTimeoutResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ask_rejects_nonpositive_timeout() -> AskTimeoutResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) a negative timeout is refused cleanly, not crashed (real client) ---
    code, err, crashed = _run_real(["--timeout", "-5"])
    add(crashed is None, f"A: --timeout -5 raised uncaught: {crashed}")
    add(code == 2, f"A: exit {code!r}, expected 2")
    add("--timeout" in err, f"A: guidance did not name --timeout: {err!r}")

    # --- (B) a zero timeout is refused before the request (mock client) ---
    code, err, sent, crashed = _run_mock(["--timeout", "0"])
    add(code == 2 and not sent and crashed is None,
        f"B: --timeout 0 not refused cleanly: exit {code!r}, sent {sent}, {crashed}")

    # --- (C) a positive timeout still reaches the request ---
    code, err, sent, crashed = _run_mock(["--timeout", "10"])
    add(sent and crashed is None, f"C: a positive timeout was blocked: {err!r} {crashed}")

    # --- (D) the default (no --timeout) still reaches the request ---
    code, err, sent, crashed = _run_mock([])
    add(sent and crashed is None, f"D: the default timeout was blocked: {err!r} {crashed}")

    total = 6
    return AskTimeoutResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["AskTimeoutResult", "evaluate_ask_rejects_nonpositive_timeout"]
