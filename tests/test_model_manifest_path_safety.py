"""Filesystem-boundary regressions for reviewed local model manifests."""

from __future__ import annotations

import json

import pytest

from sidra_ai.models.manifest import ModelManifestError, load_local_model_manifest


def _payload() -> dict[str, object]:
    return {
        "version": 1,
        "models": [
            {
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
        ],
    }


def _symlink_or_skip(link, target, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks are unavailable on this platform: {exc}")


def test_manifest_under_symlinked_parent_is_rejected(tmp_path) -> None:
    real_dir = tmp_path / "reviewed"
    real_dir.mkdir()
    manifest = real_dir / "model-manifest.json"
    manifest.write_text(json.dumps(_payload()), encoding="utf-8")

    linked_dir = tmp_path / "redirected"
    _symlink_or_skip(linked_dir, real_dir, directory=True)

    with pytest.raises(ModelManifestError, match="symlinks"):
        load_local_model_manifest(linked_dir / manifest.name)


def test_manifest_under_symlinked_grandparent_is_rejected(tmp_path) -> None:
    real_root = tmp_path / "real-root"
    nested = real_root / "nested"
    nested.mkdir(parents=True)
    manifest = nested / "model-manifest.json"
    manifest.write_text(json.dumps(_payload()), encoding="utf-8")

    linked_root = tmp_path / "linked-root"
    _symlink_or_skip(linked_root, real_root, directory=True)

    with pytest.raises(ModelManifestError, match="symlinks"):
        load_local_model_manifest(linked_root / "nested" / manifest.name)


def test_manifest_parent_traversal_is_rejected(tmp_path) -> None:
    reviewed = tmp_path / "reviewed"
    reviewed.mkdir()
    manifest = tmp_path / "model-manifest.json"
    manifest.write_text(json.dumps(_payload()), encoding="utf-8")

    traversal_path = reviewed / ".." / manifest.name
    with pytest.raises(ModelManifestError, match="parent traversal"):
        load_local_model_manifest(traversal_path)


def test_manifest_path_must_be_a_regular_file(tmp_path) -> None:
    directory = tmp_path / "model-manifest.json"
    directory.mkdir()

    with pytest.raises(ModelManifestError, match="regular file"):
        load_local_model_manifest(directory)


def test_normal_manifest_still_loads_through_descriptor_boundary(tmp_path) -> None:
    manifest = tmp_path / "model-manifest.json"
    manifest.write_text(json.dumps(_payload()), encoding="utf-8")

    loaded = load_local_model_manifest(manifest)

    assert loaded.models[0].model == "sidra-local-v0"
    assert loaded.models[0].quantization == "Q4_K_M"
