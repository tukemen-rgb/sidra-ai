from __future__ import annotations

import json

from sidra_ai import local_preflight
from sidra_ai.models import HardwareProbeError, VramSnapshot


def _safe_base_env(monkeypatch) -> None:
    for name in (
        "SIDRA_HOST",
        "SIDRA_PORT",
        "SIDRA_ALLOW_PUBLIC_BIND",
        "SIDRA_API_TOKEN",
        "SIDRA_MODEL_BACKEND",
        "SIDRA_MODEL_NAME",
        "SIDRA_MODEL_ENDPOINT",
        "SIDRA_GITHUB_TOKEN",
        "SIDRA_GITHUB_API_BASE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SIDRA_HOST", "127.0.0.1")
    monkeypatch.setenv("SIDRA_MODEL_BACKEND", "echo")


def test_preflight_echo_is_secret_safe_when_gpu_probe_is_unavailable(monkeypatch) -> None:
    _safe_base_env(monkeypatch)
    synthetic_api_token = "sidra-test-api-token-never-print"
    synthetic_github_token = "sidra-test-github-token-never-print"
    monkeypatch.setenv("SIDRA_API_TOKEN", synthetic_api_token)
    monkeypatch.setenv("SIDRA_GITHUB_TOKEN", synthetic_github_token)
    monkeypatch.setattr(local_preflight, "_installed_distribution_names", lambda: set())

    def unavailable_probe():
        raise HardwareProbeError("synthetic local test failure")

    monkeypatch.setattr(local_preflight, "probe_nvidia_vram", unavailable_probe)

    report = local_preflight.collect_preflight()
    serialized = json.dumps(report, sort_keys=True)

    assert report["ok"] is True
    assert report["api_loopback_only"] is True
    assert report["configured_backend"] == "echo"
    assert report["backend_configuration"] == "valid"
    assert report["external_llm_provider_sdks"] == "clear"
    assert report["gpu_probe"] == {"status": "unavailable"}
    assert "transformers" not in report["registered_backends"]
    assert synthetic_api_token not in serialized
    assert synthetic_github_token not in serialized


def test_preflight_rejects_remote_model_endpoint_without_echoing_it(monkeypatch) -> None:
    _safe_base_env(monkeypatch)
    remote_endpoint = "http://example.invalid:11434"
    synthetic_token = "sidra-test-api-token-never-print"
    monkeypatch.setenv("SIDRA_MODEL_BACKEND", "ollama")
    monkeypatch.setenv("SIDRA_MODEL_ENDPOINT", remote_endpoint)
    monkeypatch.setenv("SIDRA_API_TOKEN", synthetic_token)
    monkeypatch.setattr(local_preflight, "_installed_distribution_names", lambda: set())

    report = local_preflight.collect_preflight()
    serialized = json.dumps(report, sort_keys=True)

    assert report["ok"] is False
    assert report["reason"] == "backend_configuration_rejected"
    assert report["backend_configuration"] == "rejected"
    assert remote_endpoint not in serialized
    assert synthetic_token not in serialized


def test_preflight_reports_only_aggregate_nvidia_vram(monkeypatch) -> None:
    _safe_base_env(monkeypatch)
    monkeypatch.setattr(local_preflight, "_installed_distribution_names", lambda: set())
    monkeypatch.setattr(
        local_preflight,
        "probe_nvidia_vram",
        lambda: VramSnapshot(total_mib=6144, free_mib=4872, device_index=0),
    )

    report = local_preflight.collect_preflight()

    assert report["ok"] is True
    assert report["gpu_probe"] == {
        "status": "available",
        "source": "nvidia-smi",
        "device_index": 0,
        "total_mib": 6144,
        "free_mib": 4872,
    }


def test_preflight_rejects_external_llm_provider_sdk_in_dedicated_env(monkeypatch) -> None:
    _safe_base_env(monkeypatch)
    monkeypatch.setattr(
        local_preflight,
        "_installed_distribution_names",
        lambda: {"fastapi", "openai"},
    )

    report = local_preflight.collect_preflight()

    assert report["ok"] is False
    assert report["reason"] == "external_llm_provider_sdk_installed"
    assert report["blocked_provider_names"] == ["openai"]


def test_home_preflight_requires_loopback_even_if_public_bind_is_authenticated(monkeypatch) -> None:
    _safe_base_env(monkeypatch)
    monkeypatch.setenv("SIDRA_HOST", "0.0.0.0")
    monkeypatch.setenv("SIDRA_ALLOW_PUBLIC_BIND", "true")
    monkeypatch.setenv("SIDRA_API_TOKEN", "synthetic-public-bind-token")
    monkeypatch.setattr(local_preflight, "_installed_distribution_names", lambda: set())

    report = local_preflight.collect_preflight()

    assert report["ok"] is False
    assert report["reason"] == "home_runtime_requires_loopback"
