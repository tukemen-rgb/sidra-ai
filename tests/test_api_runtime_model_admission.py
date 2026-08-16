"""L5 regression coverage for the real SidraService model admission path."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sidra_ai.api.model_admission import build_runtime_model
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.models.base import ModelUnavailableError
from sidra_ai.models.echo import EchoModelAdapter
from sidra_ai.models.hardware import HardwareProbeError


def _ollama_settings(tmp_path: Path) -> Settings:
    return Settings(
        model_backend="ollama",
        model_name="local-reviewed-tag",
        model_endpoint="http://127.0.0.1:11434",
        data_dir=str(tmp_path),
    )


def _write_manifest(tmp_path: Path, *, max_context_tokens: int = 4096) -> None:
    payload = {
        "version": 1,
        "models": [
            {
                "backend": "ollama",
                "model": "local-reviewed-tag",
                "weights_vram_mib": 1800,
                "kv_cache_mib_per_1k_tokens": 100,
                "max_context_tokens": max_context_tokens,
                "quantization": "Q4_K_M",
                "priority": 10,
                "license": "test-license",
                "revision": "immutable-test-revision",
            }
        ],
    }
    (tmp_path / "model-manifest.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_echo_runtime_needs_no_manifest_or_gpu(tmp_path: Path) -> None:
    model, admission = build_runtime_model(
        Settings(model_backend="echo", data_dir=str(tmp_path)), data_dir=tmp_path
    )

    assert model.backend == "echo"
    assert admission is None
    assert not (tmp_path / "model-manifest.json").exists()


def test_non_echo_requires_manifest_before_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    def should_not_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("GPU admission ran before manifest validation")

    monkeypatch.setattr(
        "sidra_ai.api.model_admission.admit_configured_adapter_with_nvidia_probe",
        should_not_run,
    )

    with pytest.raises(ModelUnavailableError, match="reviewed-manifest/VRAM admission"):
        build_runtime_model(_ollama_settings(tmp_path), data_dir=tmp_path)

    assert called is False


def test_non_echo_uses_exact_manifest_context_and_local_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manifest(tmp_path, max_context_tokens=3072)
    captured: dict[str, object] = {}
    adapter = EchoModelAdapter("admission-test-double")
    fake_admission = SimpleNamespace(routed=SimpleNamespace(adapter=adapter))

    def admit(manifest, **kwargs):
        captured["manifest"] = manifest
        captured.update(kwargs)
        return fake_admission

    monkeypatch.setattr(
        "sidra_ai.api.model_admission.admit_configured_adapter_with_nvidia_probe",
        admit,
    )

    model, admission = build_runtime_model(
        _ollama_settings(tmp_path), data_dir=tmp_path
    )

    assert model is adapter
    assert admission is fake_admission
    assert captured["backend"] == "ollama"
    assert captured["model"] == "local-reviewed-tag"
    assert captured["planned_context_tokens"] == 3072
    assert captured["adapter_options"] == {
        "endpoint": "http://127.0.0.1:11434"
    }


def test_probe_or_route_failure_is_constant_and_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manifest(tmp_path)

    def fail_probe(*args, **kwargs):
        raise HardwareProbeError("private GPU diagnostic detail")

    monkeypatch.setattr(
        "sidra_ai.api.model_admission.admit_configured_adapter_with_nvidia_probe",
        fail_probe,
    )

    with pytest.raises(ModelUnavailableError) as exc_info:
        build_runtime_model(_ollama_settings(tmp_path), data_dir=tmp_path)

    assert str(exc_info.value) == (
        "configured local model failed reviewed-manifest/VRAM admission"
    )
    assert "private GPU" not in str(exc_info.value)


def test_sidra_service_uses_runtime_admission_when_model_not_injected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}
    adapter = EchoModelAdapter("service-admission-test-double")
    admission = object()

    def build(settings, *, data_dir):
        captured["settings"] = settings
        captured["data_dir"] = data_dir
        return adapter, admission

    monkeypatch.setattr("sidra_ai.api.service.build_runtime_model", build)
    settings = _ollama_settings(tmp_path)
    service = SidraService(settings=settings)

    assert service.model is adapter
    assert service.model_admission is admission
    assert captured == {"settings": settings, "data_dir": tmp_path}


def test_explicit_model_injection_remains_test_only_escape_hatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def should_not_run(*args, **kwargs):
        raise AssertionError("runtime admission should not run for explicit injection")

    monkeypatch.setattr("sidra_ai.api.service.build_runtime_model", should_not_run)
    injected = EchoModelAdapter("injected-test-double")
    service = SidraService(
        settings=Settings(data_dir=str(tmp_path)),
        model=injected,
    )

    assert service.model is injected
    assert service.model_admission is None
