"""Offline release-gate coverage for API CLI override semantics.

These evals exercise the real ``sidra-api`` composition path while replacing
only uvicorn's socket bind with an in-memory recorder. Explicit operator input
must never be silently discarded because it is falsey: invalid overrides must
fail before bind, while a valid override must be applied exactly.
"""

from __future__ import annotations

import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import patch

from sidra_ai.api import server
from sidra_ai.config.settings import Settings
from sidra_ai.evals.cases import EvalOutcome


def _invoke(
    settings: Settings,
    argv: list[str],
) -> tuple[int, list[tuple[str, int, bool]], str, str]:
    calls: list[tuple[str, int, bool]] = []
    fake_uvicorn = ModuleType("uvicorn")

    def _run(_app: object, *, host: str, port: int, proxy_headers: bool) -> None:
        calls.append((host, port, proxy_headers))

    fake_uvicorn.run = _run  # type: ignore[attr-defined]
    stdout = StringIO()
    stderr = StringIO()
    with (
        patch.object(server, "get_settings", return_value=settings),
        patch.dict(sys.modules, {"uvicorn": fake_uvicorn}),
        redirect_stdout(stdout),
        redirect_stderr(stderr),
    ):
        exit_code = server.main(argv)
    return exit_code, calls, stdout.getvalue(), stderr.getvalue()


def _explicit_zero_port_fails_prebind_case() -> EvalOutcome:
    failures: list[str] = []
    with TemporaryDirectory() as data_dir:
        settings = Settings(model_backend="echo", data_dir=data_dir)
        exit_code, bind_calls, stdout, stderr = _invoke(settings, ["--port", "0"])

    if exit_code != 2:
        failures.append(f"explicit --port 0 returned {exit_code}, expected 2")
    if bind_calls:
        failures.append(f"falsey port override was discarded before bind: {bind_calls!r}")
    if stdout.strip():
        failures.append("startup banner was emitted before invalid port rejection")
    if not stderr.strip():
        failures.append("invalid explicit port produced no refusal diagnostic")

    return EvalOutcome(
        case_name="api_cli_explicit_zero_port_fails_prebind",
        passed=not failures,
        detail="explicit falsey port must reach validation instead of falling back",
        failures=tuple(failures),
    )


def _explicit_empty_host_fails_prebind_case() -> EvalOutcome:
    failures: list[str] = []
    with TemporaryDirectory() as data_dir:
        settings = Settings(model_backend="echo", data_dir=data_dir)
        exit_code, bind_calls, stdout, stderr = _invoke(settings, ["--host", ""])

    if exit_code != 2:
        failures.append(f"explicit empty --host returned {exit_code}, expected 2")
    if bind_calls:
        failures.append(f"falsey host override was discarded before bind: {bind_calls!r}")
    if stdout.strip():
        failures.append("startup banner was emitted before invalid host rejection")
    if not stderr.strip():
        failures.append("invalid explicit host produced no refusal diagnostic")

    return EvalOutcome(
        case_name="api_cli_explicit_empty_host_fails_prebind",
        passed=not failures,
        detail="explicit falsey host must reach validation instead of falling back",
        failures=tuple(failures),
    )


def _valid_port_override_is_applied_case() -> EvalOutcome:
    failures: list[str] = []
    with TemporaryDirectory() as data_dir:
        settings = Settings(model_backend="echo", data_dir=data_dir)
        override_port = settings.port + 1
        exit_code, bind_calls, _stdout, stderr = _invoke(
            settings,
            ["--port", str(override_port)],
        )

    expected = [(settings.host, override_port, False)]
    if exit_code != 0:
        failures.append(f"valid CLI port override returned {exit_code}: {stderr.strip()}")
    if bind_calls != expected:
        failures.append(f"expected exact override bind {expected!r}, got {bind_calls!r}")

    return EvalOutcome(
        case_name="api_cli_valid_port_override_reaches_exact_bind",
        passed=not failures,
        detail="valid explicit CLI override must still be applied exactly with proxy rewriting disabled",
        failures=tuple(failures),
    )


def run_cli_override_safety_suite() -> list[EvalOutcome]:
    """Run falsey-override and exact-application regressions offline."""

    return [
        _explicit_zero_port_fails_prebind_case(),
        _explicit_empty_host_fails_prebind_case(),
        _valid_port_override_is_applied_case(),
    ]
