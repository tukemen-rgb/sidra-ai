"""Offline preflight checks for a SIDRA AI home-PC runtime.

This module is intentionally diagnostic-only.  It must not start a model,
open a socket, call GitHub, or print credentials.  It validates the same
local-first boundaries used by v0.1 and reports only non-secret aggregate
state that is useful before starting ``sidra-api``.
"""

from __future__ import annotations

import json
import sys
from importlib.metadata import distributions
from typing import Any

from sidra_ai.config.settings import Settings, UnsafeConfigurationError
from sidra_ai.models import (
    BackendNotRegisteredError,
    HardwareProbeError,
    ModelUnavailableError,
    adapter_from_settings,
    available_backends,
    probe_nvidia_vram,
)

MIN_PYTHON = (3, 11)

# Keep this aligned with the integration gate.  These packages are not needed
# by the verified v0.1 runtime and their presence in a dedicated SIDRA venv is
# treated as configuration drift rather than a reason to fall back to them.
BLOCKED_EXTERNAL_LLM_PROVIDER_SDKS: frozenset[str] = frozenset(
    {
        "anthropic",
        "cohere",
        "fireworks-ai",
        "google-generativeai",
        "google-genai",
        "groq",
        "litellm",
        "mistralai",
        "openai",
        "together",
    }
)


def _installed_distribution_names() -> set[str]:
    """Return normalized installed distribution names without importing them."""

    return {
        (dist.metadata.get("Name") or "").strip().lower().replace("_", "-")
        for dist in distributions()
    }


def collect_preflight() -> dict[str, Any]:
    """Collect an offline, secret-safe readiness report.

    ``ok`` means the process is using a supported Python version, the dedicated
    environment contains no blocked external-LLM provider SDK, the configured
    SIDRA settings validate, the API remains loopback-only, and the configured
    model backend can be constructed without contacting a model server.

    NVIDIA VRAM observation is optional: a missing/non-NVIDIA probe is reported
    as unavailable and does not turn an otherwise valid CPU/other-GPU setup red.
    """

    report: dict[str, Any] = {
        "ok": False,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "python_supported": sys.version_info[:2] >= MIN_PYTHON,
        "registered_backends": list(available_backends()),
        "external_llm_provider_sdks": "unchecked",
        "api_loopback_only": False,
        "configured_backend": "unknown",
        "backend_configuration": "unchecked",
        "gpu_probe": {"status": "unavailable"},
    }

    if not report["python_supported"]:
        report["reason"] = "unsupported_python"
        return report

    blocked = sorted(BLOCKED_EXTERNAL_LLM_PROVIDER_SDKS & _installed_distribution_names())
    if blocked:
        report["external_llm_provider_sdks"] = "blocked-present"
        report["blocked_provider_names"] = blocked
        report["reason"] = "external_llm_provider_sdk_installed"
        return report
    report["external_llm_provider_sdks"] = "clear"

    try:
        settings = Settings.from_env()
    except UnsafeConfigurationError:
        # Do not echo the exception: it can contain operator-supplied host/backend
        # text.  A fixed reason code is enough for the preflight boundary.
        report["reason"] = "unsafe_configuration"
        return report

    report["api_loopback_only"] = settings.is_localhost_only
    report["configured_backend"] = settings.model_backend
    if not settings.is_localhost_only:
        # The product can deliberately expose an authenticated non-loopback bind,
        # but the approved home-PC baseline remains loopback-only.
        report["reason"] = "home_runtime_requires_loopback"
        return report

    try:
        # Construction validates registry membership and HTTP endpoint locality.
        # It does not contact Ollama/llama.cpp or start a model.
        adapter_from_settings(settings)
    except (BackendNotRegisteredError, ModelUnavailableError, ValueError):
        report["backend_configuration"] = "rejected"
        report["reason"] = "backend_configuration_rejected"
        return report
    report["backend_configuration"] = "valid"

    try:
        snapshot = probe_nvidia_vram()
    except HardwareProbeError:
        report["gpu_probe"] = {"status": "unavailable"}
    else:
        report["gpu_probe"] = {
            "status": "available",
            "source": snapshot.source,
            "device_index": snapshot.device_index,
            "total_mib": snapshot.total_mib,
            "free_mib": snapshot.free_mib,
        }

    report["ok"] = True
    return report


def main() -> int:
    """Print the secret-safe report and return a shell-friendly status code."""

    report = collect_preflight()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("ok") is True else 2


if __name__ == "__main__":  # pragma: no cover - exercised as a CLI by operators
    raise SystemExit(main())
