from __future__ import annotations

import subprocess

import pytest

from sidra_ai.models.hardware import HardwareProbeError
from sidra_ai.models.manifest import LocalModelManifest, ManifestModel
from sidra_ai.models.routing import NoLocalModelRouteError
from sidra_ai.models.runtime_route import (
    ConfiguredModelManifestError,
    route_configured_adapter_with_nvidia_probe,
)


def _model(
    model: str,
    *,
    weights_vram_mib: int,
    kv_cache_mib_per_1k_tokens: int = 100,
    priority: int = 10,
) -> ManifestModel:
    return ManifestModel(
        backend="ollama",
        model=model,
        weights_vram_mib=weights_vram_mib,
        kv_cache_mib_per_1k_tokens=kv_cache_mib_per_1k_tokens,
        max_context_tokens=4096,
        quantization="Q4_K_M",
        priority=priority,
        license="test-only",
        revision="local-test-r1",
    )


def _manifest(*models: ManifestModel) -> LocalModelManifest:
    return LocalModelManifest(version=1, models=tuple(models))


def _vram_runner(total_mib: int, free_mib: int):
    def run(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=f"{total_mib}, {free_mib}\n",
            stderr="",
        )

    return run


def test_configured_model_uses_exact_observed_vram_and_context_cap() -> None:
    routed = route_configured_adapter_with_nvidia_probe(
        _manifest(_model("local-q4", weights_vram_mib=1800)),
        backend="ollama",
        model="local-q4",
        planned_context_tokens=2000,
        runner=_vram_runner(6144, 3000),
        adapter_options={"endpoint": "http://127.0.0.1:11434"},
    )

    assert routed.decision.candidate.model == "local-q4"
    assert routed.decision.required_vram_mib == 2000
    assert routed.decision.usable_vram_mib == 2488
    assert routed.decision.planned_context_tokens == 2000
    assert getattr(routed.adapter, "max_context_tokens") == 2000
    assert routed.adapter.options["quantization"] == "Q4_K_M"
    assert routed.adapter.requires_paid_api is False


def test_adapter_options_cannot_override_reviewed_quantization() -> None:
    def forbidden_probe(*args, **kwargs):
        raise AssertionError("hardware probe must not run for conflicting provenance")

    with pytest.raises(
        ConfiguredModelManifestError,
        match="quantization must come from the reviewed manifest",
    ):
        route_configured_adapter_with_nvidia_probe(
            _manifest(_model("local-q4", weights_vram_mib=1800)),
            backend="ollama",
            model="local-q4",
            planned_context_tokens=2000,
            runner=forbidden_probe,
            adapter_options={
                "endpoint": "http://127.0.0.1:11434",
                "quantization": "Q8_0",
            },
        )


def test_missing_configured_model_fails_before_hardware_probe() -> None:
    def forbidden_probe(*args, **kwargs):
        raise AssertionError("hardware probe must not run without reviewed metadata")

    with pytest.raises(
        ConfiguredModelManifestError,
        match="not present in the reviewed manifest",
    ):
        route_configured_adapter_with_nvidia_probe(
            _manifest(_model("reviewed-q4", weights_vram_mib=1800)),
            backend="ollama",
            model="unreviewed-q4",
            planned_context_tokens=2000,
            runner=forbidden_probe,
            adapter_options={"endpoint": "http://127.0.0.1:11434"},
        )


def test_probe_failure_never_falls_back_to_static_six_gib_budget() -> None:
    def unavailable_probe(*args, **kwargs):
        raise FileNotFoundError("synthetic missing nvidia-smi")

    with pytest.raises(HardwareProbeError, match="probe unavailable"):
        route_configured_adapter_with_nvidia_probe(
            _manifest(_model("local-q4", weights_vram_mib=1800)),
            backend="ollama",
            model="local-q4",
            planned_context_tokens=2000,
            runner=unavailable_probe,
            adapter_options={"endpoint": "http://127.0.0.1:11434"},
        )


def test_configured_model_is_not_silently_replaced_by_smaller_candidate() -> None:
    manifest = _manifest(
        _model("configured-big", weights_vram_mib=2600, priority=1),
        _model("other-small", weights_vram_mib=1200, priority=2),
    )

    with pytest.raises(NoLocalModelRouteError, match="no local model candidate fits"):
        route_configured_adapter_with_nvidia_probe(
            manifest,
            backend="ollama",
            model="configured-big",
            planned_context_tokens=2000,
            runner=_vram_runner(6144, 3000),
            adapter_options={"endpoint": "http://127.0.0.1:11434"},
        )
