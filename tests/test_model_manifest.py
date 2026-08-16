"""Fail-closed tests for reviewed local model routing manifests."""

from __future__ import annotations

import json

import pytest

from sidra_ai.models.manifest import (
    MAX_MANIFEST_BYTES,
    ModelManifestError,
    load_local_model_manifest,
)


def _record(**overrides):
    record = {
        "backend": "echo",
        "model": "sidra-local-v0",
        "weights_vram_mib": 2048,
        "kv_cache_mib_per_1k_tokens": 128,
        "max_context_tokens": 4096,
        "quantization": "Q4_K_M",
        "priority": 10,
        "license": "internal-test",
        "revision": "reviewed-local-1",
        "artifact_sha256": None,
    }
    record.update(overrides)
    return record


def _write(tmp_path, payload) -> object:
    path = tmp_path / "models.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_manifest_preserves_explicit_routing_and_provenance(tmp_path) -> None:
    path = _write(tmp_path, {"version": 1, "models": [_record()]})

    manifest = load_local_model_manifest(path)
    assert manifest.version == 1
    assert len(manifest.models) == 1
    model = manifest.models[0]
    assert model.backend == "echo"
    assert model.quantization == "Q4_K_M"
    assert model.revision == "reviewed-local-1"
    assert model.license == "internal-test"

    candidate = manifest.candidates()[0]
    assert candidate.model == "sidra-local-v0"
    assert candidate.weights_vram_mib == 2048
    assert candidate.kv_cache_mib_per_1k_tokens == 128
    assert candidate.max_context_tokens == 4096
    assert candidate.priority == 10


def test_manifest_rejects_non_registered_or_remote_model_references(tmp_path) -> None:
    unknown = _write(
        tmp_path,
        {"version": 1, "models": [_record(backend="openai")]},
    )
    with pytest.raises(ModelManifestError, match="local-only registry"):
        load_local_model_manifest(unknown)

    remote = _write(
        tmp_path,
        {"version": 1, "models": [_record(model="https://models.example/a.gguf")]},
    )
    with pytest.raises(ModelManifestError, match="must not be URLs"):
        load_local_model_manifest(remote)


def test_manifest_requires_memory_context_quantization_and_provenance(tmp_path) -> None:
    missing_kv = _record()
    del missing_kv["kv_cache_mib_per_1k_tokens"]
    with pytest.raises(ModelManifestError, match="kv_cache_mib_per_1k_tokens"):
        load_local_model_manifest(
            _write(tmp_path, {"version": 1, "models": [missing_kv]})
        )

    with pytest.raises(ModelManifestError, match="quantization"):
        load_local_model_manifest(
            _write(
                tmp_path,
                {"version": 1, "models": [_record(quantization="unknown")]},
            )
        )

    with pytest.raises(ModelManifestError, match="revision or artifact_sha256"):
        load_local_model_manifest(
            _write(
                tmp_path,
                {
                    "version": 1,
                    "models": [
                        _record(revision=None, artifact_sha256=None)
                    ],
                },
            )
        )


def test_manifest_accepts_and_normalizes_sha256_artifact_provenance(tmp_path) -> None:
    digest = "sha256:" + "A" * 64
    path = _write(
        tmp_path,
        {
            "version": 1,
            "models": [
                _record(revision=None, artifact_sha256=digest)
            ],
        },
    )

    manifest = load_local_model_manifest(path)
    assert manifest.models[0].artifact_sha256 == digest.lower()


def test_manifest_rejects_duplicate_keys_and_unknown_fields(tmp_path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"version":1,"version":1,"models":[]}',
        encoding="utf-8",
    )
    with pytest.raises(ModelManifestError, match="duplicate manifest key"):
        load_local_model_manifest(duplicate)

    with pytest.raises(ModelManifestError, match="unknown fields"):
        load_local_model_manifest(
            _write(
                tmp_path,
                {
                    "version": 1,
                    "models": [_record(endpoint="http://127.0.0.1:11434")],
                },
            )
        )


def test_manifest_is_bounded_and_rejects_symlink(tmp_path) -> None:
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"{" + b" " * MAX_MANIFEST_BYTES + b"}")
    with pytest.raises(ModelManifestError, match="size"):
        load_local_model_manifest(oversized)

    target = _write(tmp_path, {"version": 1, "models": [_record()]})
    link = tmp_path / "models-link.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")
    with pytest.raises(ModelManifestError, match="symlinks"):
        load_local_model_manifest(link)
