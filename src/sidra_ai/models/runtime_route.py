"""Fail-closed runtime routing for one explicitly configured local model.

This module bridges the reviewed local model manifest to the existing observed
NVIDIA VRAM route without changing API/service composition yet. It preserves
current configuration semantics: a configured backend/model must exist exactly
in the reviewed manifest, and SIDRA never silently substitutes a different
model merely because another candidate would fit.

No network request or model generation is performed by this module. The only
hardware observation is the bounded local ``nvidia-smi`` probe. The admission
record intentionally retains both the reviewed manifest entry and the exact
VRAM snapshot that admitted the adapter so a later composition layer does not
have to reconstruct or re-probe those safety inputs.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any, Mapping

from sidra_ai.models.hardware import Runner, VramSnapshot, probe_nvidia_vram
from sidra_ai.models.manifest import LocalModelManifest, ManifestModel
from sidra_ai.models.routing import RoutedAdapter, route_and_create_adapter


class ConfiguredModelManifestError(RuntimeError):
    """Raised when runtime configuration is not backed by reviewed metadata."""


@dataclass(frozen=True)
class ConfiguredModelAdmission:
    """Immutable evidence for one admitted configured local-model route.

    ``manifest_entry`` preserves the reviewed quantization/license/revision or
    artifact digest metadata. ``snapshot`` is the single observed device state
    used for admission. ``routed`` contains the matching route decision and the
    adapter whose runtime context cap is enforced from that same decision.

    Keeping these values together avoids a later caller accidentally pairing an
    adapter with a different manifest record or a second VRAM sample.
    """

    manifest_entry: ManifestModel
    snapshot: VramSnapshot
    routed: RoutedAdapter


def _configured_manifest_entry(
    manifest: LocalModelManifest,
    *,
    backend: str,
    model: str,
) -> ManifestModel:
    backend_name = backend.strip()
    model_name = model.strip()
    if not backend_name or not model_name:
        raise ConfiguredModelManifestError(
            "configured backend and model must be non-empty"
        )

    matches = [
        entry
        for entry in manifest.models
        if entry.backend == backend_name and entry.model == model_name
    ]
    if len(matches) != 1:
        # LocalModelManifest rejects duplicate route IDs, so any value other
        # than one means the configured target is not backed by reviewed data.
        raise ConfiguredModelManifestError(
            "configured local model is not present in the reviewed manifest"
        )
    return matches[0]


def admit_configured_adapter_with_nvidia_probe(
    manifest: LocalModelManifest,
    *,
    backend: str,
    model: str,
    planned_context_tokens: int,
    device_index: int = 0,
    reserve_vram_mib: int = 512,
    timeout_s: float = 2.0,
    runner: Runner = subprocess.run,
    adapter_options: Mapping[str, Any] | None = None,
) -> ConfiguredModelAdmission:
    """Admit one configured adapter and retain the exact safety evidence.

    Manifest matching happens before the hardware probe, so configuration not
    backed by reviewed local metadata cannot trigger GPU observation or adapter
    construction. The GPU is then sampled exactly once. Probe failure is
    propagated and never falls back to the static 6 GiB budget.

    The returned record keeps the same manifest entry, VRAM snapshot and routed
    adapter together. This gives the future API/service composition path one
    object to audit without re-deriving provenance or re-sampling hardware.
    """

    entry = _configured_manifest_entry(manifest, backend=backend, model=model)
    snapshot = probe_nvidia_vram(
        device_index,
        timeout_s=timeout_s,
        runner=runner,
    )
    routed = route_and_create_adapter(
        [entry.to_candidate()],
        hardware=snapshot.to_hardware_budget(reserve_vram_mib=reserve_vram_mib),
        planned_context_tokens=planned_context_tokens,
        adapter_options=dict(adapter_options or {}),
    )
    return ConfiguredModelAdmission(
        manifest_entry=entry,
        snapshot=snapshot,
        routed=routed,
    )


def route_configured_adapter_with_nvidia_probe(
    manifest: LocalModelManifest,
    *,
    backend: str,
    model: str,
    planned_context_tokens: int,
    device_index: int = 0,
    reserve_vram_mib: int = 512,
    timeout_s: float = 2.0,
    runner: Runner = subprocess.run,
    adapter_options: Mapping[str, Any] | None = None,
) -> RoutedAdapter:
    """Compatibility wrapper returning only the routed adapter.

    New composition code should prefer
    :func:`admit_configured_adapter_with_nvidia_probe` so the reviewed manifest
    provenance and the exact observed VRAM snapshot remain attached to the
    route. This wrapper preserves the existing L4 interface while delegating to
    the same one-probe, fail-closed admission path.
    """

    return admit_configured_adapter_with_nvidia_probe(
        manifest,
        backend=backend,
        model=model,
        planned_context_tokens=planned_context_tokens,
        device_index=device_index,
        reserve_vram_mib=reserve_vram_mib,
        timeout_s=timeout_s,
        runner=runner,
        adapter_options=adapter_options,
    ).routed
