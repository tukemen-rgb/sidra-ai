"""Offline release gate for API audit-storage startup privacy.

This suite exercises the real ``sidra-api`` composition path while replacing
only uvicorn's socket bind and the local audit sink constructor. It verifies
that an audit-storage failure is absorbed by the same context-free pre-bind
startup boundary as other local storage failures.
"""

from __future__ import annotations

import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import patch

from sidra_ai.api import app as api_app_module
from sidra_ai.api import server
from sidra_ai.config.settings import Settings
from sidra_ai.evals.cases import EvalOutcome


def _audit_storage_failure_prebind_privacy_case() -> EvalOutcome:
    failures: list[str] = []
    sensitive_path = "/private/operator/sidra/api_audit.jsonl"
    diagnostic = f"permission denied: {sensitive_path}"
    bind_calls: list[tuple[str, int]] = []

    fake_uvicorn = ModuleType("uvicorn")

    def _run(_app: object, *, host: str, port: int) -> None:
        bind_calls.append((host, port))

    fake_uvicorn.run = _run  # type: ignore[attr-defined]

    class FailingAuditLog:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise OSError(diagnostic)

    stdout = StringIO()
    stderr = StringIO()
    with TemporaryDirectory() as data_dir:
        settings = Settings(model_backend="echo", data_dir=data_dir)
        with (
            patch.object(server, "get_settings", return_value=settings),
            patch.object(api_app_module, "ApiAuditLog", FailingAuditLog),
            patch.dict(sys.modules, {"uvicorn": fake_uvicorn}),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = server.main([])

    expected_error = "refusing to start: local SIDRA storage is unavailable or unsafe"
    if exit_code != 2:
        failures.append(f"expected exit code 2, got {exit_code}")
    if bind_calls:
        failures.append(f"uvicorn.run was called after audit storage failure: {bind_calls!r}")
    if stdout.getvalue().strip():
        failures.append("startup banner was emitted after audit storage initialization failed")
    if stderr.getvalue().strip() != expected_error:
        failures.append("audit storage startup failure did not use the fixed public diagnostic")
    if sensitive_path in stderr.getvalue() or "permission denied" in stderr.getvalue():
        failures.append("audit storage startup refusal leaked filesystem details")

    return EvalOutcome(
        case_name="api_startup_audit_storage_failure_prebind_privacy",
        passed=not failures,
        detail="audit storage errors must fail before bind without leaking paths",
        failures=tuple(failures),
    )


def run_audit_startup_privacy_suite() -> list[EvalOutcome]:
    """Run the audit-storage startup privacy regression without opening a socket."""

    return [_audit_storage_failure_prebind_privacy_case()]
