from __future__ import annotations

import subprocess

import pytest

from sidra_ai.models.hardware import HardwareProbeError
from sidra_ai.models.manifest import LocalModelManifest, ManifestModel
from sidra_ai.models.runtime_route import (
    ConfiguredModelManifestError,
    admit_configured_adapter_with_nvidia_probe,
    route_configured_adapter_with_nvidia_probe,
)


def _manifest() -> LocalModelManifest:
    return LocalModelManifest(
        version=1,
        models=(
            ManifestModel(
                backend="echo",
                model="echo-safe",
                weights_vram_mib=2000,
                kv_cache_mib_per_1k_tokens=100,
                max_context_tokens=4096,
                quantization="q4-test",
                priority=0,
                license="test-only",
                revision="local-rev-1",
                artifact_sha256="sha256:" + "a" * 64,
            ),
        ),
    )


class _ProbeRunner:
    def __init__(self, *, returncode: int = 0, stdout: str = "6144, 4096\n") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.calls = 0

    def __call__(self, argv, **kwargs):
        self.calls += 1
        return subprocess.CompletedProcess(
            args=argv,
            returncode=self.returncode,
            stdout=self.stdout,
            stderr="driver details must not leak",
        )


def test_admission_retains_manifest_and_exact_vram_snapshot() -> None:
    manifest = _manifest()
    runner = _ProbeRunner()

    admission = admit_configured_adapter_with_nvidia_probe(
        manifest,
        backend="echo",
        model="echo-safe",
        planned_context_tokens=2000,
        runner=runner,
    )

    assert runner.calls == 1
    assert admission.manifest_entry is manifest.models[0]
    assert admission.manifest_entry.revision == "local-rev-1"
    assert admission.manifest_entry.artifact_sha256 == "sha256:" + "a" * 64
    assert admission.snapshot.total_mib == 6144
    assert admission.snapshot.free_mib == 4096
    assert admission.snapshot.device_index == 0
    assert admission.routed.decision.required_vram_mib == 2200
    assert admission.routed.decision.usable_vram_mib == 3584
    assert admission.routed.decision.planned_context_tokens == 2000
    assert admission.routed.adapter.max_context_tokens == 2000


def test_compatibility_wrapper_uses_same_one_probe_admission_path() -> None:
    runner = _ProbeRunner()

    routed = route_configured_adapter_with_nvidia_probe(
        _manifest(),
        backend="echo",
        model="echo-safe",
        planned_context_tokens=2000,
        runner=runner,
    )

    assert runner.calls == 1
    assert routed.decision.candidate.route_id == "echo:echo-safe"
    assert routed.decision.usable_vram_mib == 3584
    assert routed.adapter.max_context_tokens == 2000


def test_missing_manifest_route_fails_before_hardware_probe() -> None:
    runner = _ProbeRunner()

    with pytest.raises(ConfiguredModelManifestError):
        admit_configured_adapter_with_nvidia_probe(
            _manifest(),
            backend="echo",
            model="not-reviewed",
            planned_context_tokens=2000,
            runner=runner,
        )

    assert runner.calls == 0


def test_probe_failure_never_falls_back_to_static_vram_budget() -> None:
    runner = _ProbeRunner(returncode=1)

    with pytest.raises(HardwareProbeError):
        admit_configured_adapter_with_nvidia_probe(
            _manifest(),
            backend="echo",
            model="echo-safe",
            planned_context_tokens=2000,
            runner=runner,
        )

    assert runner.calls == 1
