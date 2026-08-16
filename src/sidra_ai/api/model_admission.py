"""Fail-closed model assembly for the real API composition path.

The model layer owns manifest parsing, observed-VRAM probing and routing policy.
This module is the L5 bridge that decides when the real API runtime must use
that admission path instead of constructing a configured adapter directly.

The dependency-free ``echo`` backend remains the baseline and requires no GPU
or manifest. Every other v0.1 backend must be backed by the reviewed local
manifest stored under SIDRA's data directory and must pass a fresh NVIDIA VRAM
observation before an adapter is returned.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.config.settings import Settings
from sidra_ai.models.base import LocalModelAdapter, ModelUnavailableError
from sidra_ai.models.hardware import HardwareProbeError
from sidra_ai.models.manifest import (
    LocalModelManifest,
    ManifestModel,
    ModelManifestError,
    load_local_model_manifest,
)
from sidra_ai.models.registry import BackendNotRegisteredError, adapter_from_settings
from sidra_ai.models.routing import NoLocalModelRouteError
from sidra_ai.models.runtime_route import (
    ConfiguredModelAdmission,
    ConfiguredModelManifestError,
    admit_configured_adapter_with_nvidia_probe,
)

MODEL_MANIFEST_FILENAME = "model-manifest.json"


def _matching_manifest_entry(
    manifest: LocalModelManifest,
    *,
    backend: str,
    model: str,
) -> ManifestModel:
    matches = [
        entry
        for entry in manifest.models
        if entry.backend == backend and entry.model == model
    ]
    if len(matches) != 1:
        raise ConfiguredModelManifestError(
            "configured local model is not present in the reviewed manifest"
        )
    return matches[0]


def build_runtime_model(
    settings: Settings,
    *,
    data_dir: Path,
) -> tuple[LocalModelAdapter, ConfiguredModelAdmission | None]:
    """Build the API runtime model without bypassing local admission.

    ``echo`` stays dependency-free and never probes a GPU. For Ollama and
    llama.cpp, the configured backend/model must match one reviewed manifest
    entry exactly. The manifest entry's declared maximum context is used as the
    v0.1 admission plan. This is intentionally conservative: until a shared,
    separately reviewed planned-context setting exists, SIDRA only starts a
    real model when the full reviewed context window fits the freshly observed
    VRAM budget.

    Any manifest, hardware, route or local-endpoint failure is collapsed to one
    constant ``ModelUnavailableError`` so server startup can fail before socket
    bind without leaking local paths, model identifiers or endpoint details.
    """

    if settings.model_backend == "echo":
        return adapter_from_settings(settings), None

    try:
        manifest = load_local_model_manifest(Path(data_dir) / MODEL_MANIFEST_FILENAME)
        entry = _matching_manifest_entry(
            manifest,
            backend=settings.model_backend,
            model=settings.model_name,
        )
        adapter_options: dict[str, object] = {}
        if settings.model_endpoint:
            adapter_options["endpoint"] = settings.model_endpoint

        admission = admit_configured_adapter_with_nvidia_probe(
            manifest,
            backend=settings.model_backend,
            model=settings.model_name,
            planned_context_tokens=entry.max_context_tokens,
            adapter_options=adapter_options,
        )
    except (
        BackendNotRegisteredError,
        ConfiguredModelManifestError,
        HardwareProbeError,
        ModelManifestError,
        ModelUnavailableError,
        NoLocalModelRouteError,
        ValueError,
    ) as exc:
        raise ModelUnavailableError(
            "configured local model failed reviewed-manifest/VRAM admission"
        ) from exc

    return admission.routed.adapter, admission
