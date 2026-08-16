"""Offline release gate for strict local-model manifest safety.

This suite protects the metadata boundary that feeds observed-VRAM routing. It
uses temporary local JSON files only: no socket, model process, weights, or
network access is required.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.models.manifest import ModelManifestError, load_local_model_manifest


def _base_record() -> dict[str, Any]:
    return {
        "backend": "echo",
        "model": "sidra-eval-local-model",
        "weights_vram_mib": 2048,
        "kv_cache_mib_per_1k_tokens": 128,
        "max_context_tokens": 4096,
        "quantization": "Q4_K_M",
        "priority": 10,
        "license": "test-only",
        "revision": "eval-revision-1",
        "artifact_sha256": "sha256:" + "a" * 64,
    }


def _write_manifest(directory: Path, record: dict[str, Any], *, name: str) -> Path:
    path = directory / f"{name}.json"
    payload = {"version": 1, "models": [record]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _rejection_outcome(
    directory: Path,
    *,
    case_name: str,
    record: dict[str, Any],
    expected_fragment: str,
) -> EvalOutcome:
    path = _write_manifest(directory, record, name=case_name)
    try:
        load_local_model_manifest(path)
    except ModelManifestError as exc:
        message = str(exc)
        failures = () if expected_fragment in message else (
            f"manifest failed closed for the wrong reason: {message}",
        )
        return EvalOutcome(
            case_name=case_name,
            passed=not failures,
            detail="rejected",
            failures=failures,
        )
    return EvalOutcome(
        case_name=case_name,
        passed=False,
        detail="accepted",
        failures=("unsafe/incomplete manifest was accepted",),
    )


def run_model_manifest_safety_suite() -> list[EvalOutcome]:
    """Verify the local manifest cannot silently broaden model trust."""

    outcomes: list[EvalOutcome] = []
    with TemporaryDirectory(prefix="sidra-manifest-eval-") as temp_dir:
        directory = Path(temp_dir)

        valid_path = _write_manifest(directory, _base_record(), name="valid")
        failures: list[str] = []
        try:
            manifest = load_local_model_manifest(valid_path)
            model = manifest.models[0]
            candidate = manifest.candidates()[0]
            if manifest.version != 1:
                failures.append("manifest version changed unexpectedly")
            if candidate.weights_vram_mib != 2048:
                failures.append("weights VRAM metadata was not preserved exactly")
            if candidate.kv_cache_mib_per_1k_tokens != 128:
                failures.append("KV-cache metadata was not preserved exactly")
            if candidate.max_context_tokens != 4096:
                failures.append("context limit metadata was not preserved exactly")
            if model.artifact_sha256 != "sha256:" + "a" * 64:
                failures.append("artifact provenance digest was lost or changed")
            if model.revision != "eval-revision-1":
                failures.append("model revision provenance was lost or changed")
        except Exception as exc:  # pragma: no cover - surfaced as an eval failure
            failures.append(f"valid local manifest was rejected: {type(exc).__name__}: {exc}")
        outcomes.append(
            EvalOutcome(
                case_name="local_model_manifest_preserves_measured_metadata",
                passed=not failures,
                detail="loaded" if not failures else "failed",
                failures=tuple(failures),
            )
        )

        remote = _base_record()
        remote["model"] = "https://models.example.invalid/model.gguf"
        outcomes.append(
            _rejection_outcome(
                directory,
                case_name="local_model_manifest_rejects_remote_model_reference",
                record=remote,
                expected_fragment="must not be URLs",
            )
        )

        unknown_cost = _base_record()
        unknown_cost.pop("kv_cache_mib_per_1k_tokens")
        outcomes.append(
            _rejection_outcome(
                directory,
                case_name="local_model_manifest_rejects_unknown_resource_cost",
                record=unknown_cost,
                expected_fragment="kv_cache_mib_per_1k_tokens",
            )
        )

        no_provenance = _base_record()
        no_provenance.pop("revision")
        no_provenance.pop("artifact_sha256")
        outcomes.append(
            _rejection_outcome(
                directory,
                case_name="local_model_manifest_requires_artifact_provenance",
                record=no_provenance,
                expected_fragment="requires revision or artifact_sha256 provenance",
            )
        )

    return outcomes
