"""Fail-closed runtime routing for one explicitly configured local model.

This module bridges the reviewed local model manifest to the existing observed
NVIDIA VRAM route without changing API/service composition yet.  It preserves
current configuration semantics: a configured backend/model must exist exactly
in the reviewed manifest, and SIDRA never silently substitutes a different
model merely because another candidate would fit.

No network request or model generation is performed by this module.  The only
hardware observation is the bounded local ``nvidia-smi`` probe delegated to
:func:`route_and_create_adapter_with_nvidia_probe`.
"""

from __future__ import annotations

import subprocess
from typing import Any, Mapping

from sidra_ai.models.hardware import Runner, route_and_create_adapter_with_nvidia_probe
from sidra_ai.models.manifest import LocalModelManifest
from sidra_ai.models.routing import RoutedAdapter


class ConfiguredModelManifestError(RuntimeError):
    """Raised when runtime configuration is not backed by reviewed metadata."""


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
    """Build the configured adapter only after manifest + observed-VRAM admission.

    The backend/model pair is matched exactly against the already validated
    local manifest.  Missing metadata fails *before* the GPU probe, and a model
    that does not fit the observed budget is rejected even if another manifest
    entry would fit.  This prevents configuration drift from turning routing
    into a silent model substitution.

    Probe failure is propagated by the hardware layer and never falls back to
    the static 6 GiB budget.  The returned adapter inherits the same planned
    context cap that was used to calculate KV-cache admission.
    """

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

    options = dict(adapter_options or {})
    return route_and_create_adapter_with_nvidia_probe(
        [matches[0].to_candidate()],
        planned_context_tokens=planned_context_tokens,
        device_index=device_index,
        reserve_vram_mib=reserve_vram_mib,
        timeout_s=timeout_s,
        runner=runner,
        adapter_options=options,
    )
