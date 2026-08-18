"""Offline release regressions for real-model runtime admission.

These evals exercise the actual ``sidra-api`` composition boundary introduced
for reviewed local models.  Only uvicorn's socket bind and the hardware
admission result are replaced with in-memory test doubles, so the suite can
prove that non-echo startup cannot bypass the manifest/observed-VRAM gate
without opening a socket, starting a model, or touching the network.
"""

from __future__ import annotations

import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from sidra_ai.api import server
from sidra_ai.config.settings import Settings
from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.models.hardware import HardwareProbeError


def _write_manifest(data_dir: Path, *, max_context_tokens: int = 3072) -> None:
    payload = {
        "version": 1,
        "models": [
            {
                "backend": "ollama",
                "model": "reviewed-local-tag",
                "weights_vram_mib": 1800,
                "kv_cache_mib_per_1k_tokens": 100,
                "max_context_tokens": max_context_tokens,
                "quantization": "Q4_K_M",
                "priority": 10,
                "license": "synthetic-test-license",
                "revision": "synthetic-immutable-revision",
            }
        ],
    }
    (data_dir / "model-manifest.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _settings(data_dir: Path) -> Settings:
    return Settings(
        model_backend="ollama",
        model_name="reviewed-local-tag",
        model_endpoint="http://127.0.0.1:11434",
        data_dir=str(data_dir),
    )


def _invoke_with_fake_uvicorn(
    settings: Settings,
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
        exit_code = server.main([])
    return exit_code, calls, stdout.getvalue(), stderr.getvalue()


def _missing_manifest_blocks_before_bind_case() -> EvalOutcome:
    failures: list[str] = []
    with TemporaryDirectory() as raw_dir:
        data_dir = Path(raw_dir)
        settings = _settings(data_dir)
        exit_code, bind_calls, stdout, stderr = _invoke_with_fake_uvicorn(settings)

    if exit_code != 2:
        failures.append(f"expected exit code 2, got {exit_code}")
    if bind_calls:
        failures.append(f"uvicorn.run was called without a reviewed manifest: {bind_calls!r}")
    if stdout.strip():
        failures.append("startup banner was emitted before manifest admission completed")
    for sensitive in (settings.model_name, settings.model_endpoint, "model-manifest.json"):
        if sensitive and sensitive in stderr:
            failures.append("startup refusal leaked local model admission details")

    return EvalOutcome(
        case_name="runtime_model_admission_missing_manifest_prebind",
        passed=not failures,
        detail="non-echo startup must require reviewed manifest before socket bind",
        failures=tuple(failures),
    )


def _hardware_failure_blocks_before_bind_case() -> EvalOutcome:
    failures: list[str] = []
    private_detail = "synthetic private GPU diagnostic /dev/nvidia0"
    with TemporaryDirectory() as raw_dir:
        data_dir = Path(raw_dir)
        _write_manifest(data_dir)
        settings = _settings(data_dir)
        with patch(
            "sidra_ai.api.model_admission.admit_configured_adapter_with_nvidia_probe",
            side_effect=HardwareProbeError(private_detail),
        ):
            exit_code, bind_calls, stdout, stderr = _invoke_with_fake_uvicorn(settings)

    if exit_code != 2:
        failures.append(f"expected exit code 2, got {exit_code}")
    if bind_calls:
        failures.append(f"uvicorn.run was called after VRAM admission failure: {bind_calls!r}")
    if stdout.strip():
        failures.append("startup banner was emitted before VRAM admission completed")
    for sensitive in (private_detail, settings.model_name, settings.model_endpoint):
        if sensitive and sensitive in stderr:
            failures.append("startup refusal leaked model or hardware admission details")

    return EvalOutcome(
        case_name="runtime_model_admission_hardware_failure_prebind",
        passed=not failures,
        detail="observed-VRAM admission failure must stop startup before socket bind",
        failures=tuple(failures),
    )


def _successful_admission_is_required_before_bind_case() -> EvalOutcome:
    failures: list[str] = []
    captured: dict[str, object] = {}
    adapter = EchoModelAdapter("runtime-admission-eval-double")
    fake_admission = SimpleNamespace(routed=SimpleNamespace(adapter=adapter))

    def _admit(manifest, **kwargs):
        captured["manifest"] = manifest
        captured.update(kwargs)
        return fake_admission

    with TemporaryDirectory() as raw_dir:
        data_dir = Path(raw_dir)
        _write_manifest(data_dir, max_context_tokens=3072)
        settings = _settings(data_dir)
        with patch(
            "sidra_ai.api.model_admission.admit_configured_adapter_with_nvidia_probe",
            side_effect=_admit,
        ):
            exit_code, bind_calls, _stdout, stderr = _invoke_with_fake_uvicorn(settings)

    if exit_code != 0:
        failures.append(f"admitted local model startup returned {exit_code}: {stderr.strip()}")
    expected_bind = [(settings.host, settings.port, False)]
    if bind_calls != expected_bind:
        failures.append(f"expected exactly one post-admission bind {expected_bind!r}, got {bind_calls!r}")
    if captured.get("backend") != "ollama":
        failures.append("configured backend did not pass through reviewed admission")
    if captured.get("model") != "reviewed-local-tag":
        failures.append("configured model did not pass through reviewed admission")
    if captured.get("planned_context_tokens") != 3072:
        failures.append("runtime admission did not use the reviewed manifest context cap")
    if captured.get("adapter_options") != {"endpoint": "http://127.0.0.1:11434"}:
        failures.append("runtime admission did not preserve the configured loopback endpoint")

    return EvalOutcome(
        case_name="runtime_model_admission_success_precedes_bind",
        passed=not failures,
        detail="real-model bind is reachable only after reviewed admission succeeds with proxy rewriting disabled",
        failures=tuple(failures),
    )


def run_runtime_model_admission_suite() -> list[EvalOutcome]:
    """Run real-model composition regressions without network or model startup."""

    return [
        _missing_manifest_blocks_before_bind_case(),
        _hardware_failure_blocks_before_bind_case(),
        _successful_admission_is_required_before_bind_case(),
    ]
