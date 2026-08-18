"""Offline regressions for API startup capability boundaries.

These evals exercise the real ``sidra-api`` composition path while replacing
only uvicorn's socket binding with an in-memory recorder. They therefore prove
that unsafe/unavailable local-model configurations fail before the server can
listen, without network access or model weights.
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


def _invoke_with_fake_uvicorn(
    settings: Settings,
    argv: list[str] | None = None,
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
        exit_code = server.main(argv or [])
    return exit_code, calls, stdout.getvalue(), stderr.getvalue()


def _unregistered_backend_prebind_case() -> EvalOutcome:
    failures: list[str] = []
    with TemporaryDirectory() as data_dir:
        settings = Settings(
            model_backend="transformers",
            model_name="synthetic-remote-looking-model",
            data_dir=data_dir,
        )
        exit_code, bind_calls, stdout, stderr = _invoke_with_fake_uvicorn(settings)

    if exit_code != 2:
        failures.append(f"expected exit code 2, got {exit_code}")
    if bind_calls:
        failures.append(f"uvicorn.run was called before backend rejection: {bind_calls!r}")
    if stdout.strip():
        failures.append("startup banner was emitted before backend preflight completed")
    for sensitive in (settings.model_backend, settings.model_name):
        if sensitive and sensitive in stderr:
            failures.append("startup refusal leaked configured backend/model details")

    return EvalOutcome(
        case_name="api_startup_unregistered_backend_prebind",
        passed=not failures,
        detail="unregistered local backend must fail before socket bind",
        failures=tuple(failures),
    )


def _remote_endpoint_prebind_case() -> EvalOutcome:
    failures: list[str] = []
    remote_endpoint = "https://example.invalid:11434"
    with TemporaryDirectory() as data_dir:
        settings = Settings(
            model_backend="ollama",
            model_name="synthetic-local-model",
            model_endpoint=remote_endpoint,
            data_dir=data_dir,
        )
        exit_code, bind_calls, stdout, stderr = _invoke_with_fake_uvicorn(settings)

    if exit_code != 2:
        failures.append(f"expected exit code 2, got {exit_code}")
    if bind_calls:
        failures.append(f"uvicorn.run was called for a non-loopback model endpoint: {bind_calls!r}")
    if stdout.strip():
        failures.append("startup banner was emitted before endpoint preflight completed")
    if remote_endpoint in stderr or "example.invalid" in stderr:
        failures.append("startup refusal leaked the rejected remote endpoint")

    return EvalOutcome(
        case_name="api_startup_remote_endpoint_prebind",
        passed=not failures,
        detail="non-loopback inference endpoint must fail before socket bind",
        failures=tuple(failures),
    )


def _unsafe_cli_public_bind_prebind_case() -> EvalOutcome:
    failures: list[str] = []
    with TemporaryDirectory() as data_dir:
        settings = Settings(model_backend="echo", data_dir=data_dir)
        exit_code, bind_calls, stdout, _stderr = _invoke_with_fake_uvicorn(
            settings,
            ["--host", "0.0.0.0"],
        )

    if exit_code != 2:
        failures.append(f"expected exit code 2, got {exit_code}")
    if bind_calls:
        failures.append(f"uvicorn.run was called for unsafe CLI public bind: {bind_calls!r}")
    if stdout.strip():
        failures.append("startup banner was emitted before CLI bind validation completed")

    return EvalOutcome(
        case_name="api_startup_unsafe_cli_public_bind_prebind",
        passed=not failures,
        detail="unsafe CLI host override must fail before socket bind",
        failures=tuple(failures),
    )


def _storage_failure_prebind_privacy_case() -> EvalOutcome:
    failures: list[str] = []
    sensitive_path = "/private/operator/sidra/quarantine.jsonl"
    diagnostic = f"permission denied: {sensitive_path}"

    with TemporaryDirectory() as data_dir:
        settings = Settings(model_backend="echo", data_dir=data_dir)

        class FailingService:
            def __init__(self, *, settings: Settings) -> None:
                raise OSError(diagnostic)

        with patch.object(server, "SidraService", FailingService):
            exit_code, bind_calls, stdout, stderr = _invoke_with_fake_uvicorn(settings)

    expected_error = "refusing to start: local SIDRA storage is unavailable or unsafe"
    if exit_code != 2:
        failures.append(f"expected exit code 2, got {exit_code}")
    if bind_calls:
        failures.append(f"uvicorn.run was called after storage failure: {bind_calls!r}")
    if stdout.strip():
        failures.append("startup banner was emitted after storage initialization failed")
    if stderr.strip() != expected_error:
        failures.append("storage startup failure did not use the fixed public diagnostic")
    if sensitive_path in stderr or "permission denied" in stderr:
        failures.append("storage startup refusal leaked filesystem details")

    return EvalOutcome(
        case_name="api_startup_storage_failure_prebind_privacy",
        passed=not failures,
        detail="local storage errors must fail before bind without leaking paths",
        failures=tuple(failures),
    )


def _safe_echo_reaches_bind_case() -> EvalOutcome:
    failures: list[str] = []
    with TemporaryDirectory() as data_dir:
        settings = Settings(model_backend="echo", data_dir=data_dir)
        exit_code, bind_calls, _stdout, stderr = _invoke_with_fake_uvicorn(settings)

    expected_bind = [(settings.host, settings.port, False)]
    if exit_code != 0:
        failures.append(f"safe echo startup returned {exit_code}: {stderr.strip()}")
    if bind_calls != expected_bind:
        failures.append(f"expected exactly one loopback bind {expected_bind!r}, got {bind_calls!r}")

    return EvalOutcome(
        case_name="api_startup_safe_echo_reaches_bind",
        passed=not failures,
        detail="safe local backend must reach bind with proxy rewriting disabled",
        failures=tuple(failures),
    )


def run_startup_safety_suite() -> list[EvalOutcome]:
    """Run API pre-bind startup regressions without opening a socket."""

    return [
        _unregistered_backend_prebind_case(),
        _remote_endpoint_prebind_case(),
        _unsafe_cli_public_bind_prebind_case(),
        _storage_failure_prebind_privacy_case(),
        _safe_echo_reaches_bind_case(),
    ]
