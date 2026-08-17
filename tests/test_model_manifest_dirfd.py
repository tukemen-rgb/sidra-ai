from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import sidra_ai.models.manifest as manifest_module
from sidra_ai.models.manifest import ModelManifestError, load_local_model_manifest


def _write_manifest(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "models": [
                    {
                        "backend": "ollama",
                        "model": "local-q4",
                        "weights_vram_mib": 3800,
                        "kv_cache_mib_per_1k_tokens": 96,
                        "max_context_tokens": 4096,
                        "quantization": "Q4_K_M",
                        "priority": 10,
                        "license": "test-only",
                        "revision": "local-reviewed-revision",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.skipif(
    not manifest_module._supports_secure_dirfd(),
    reason="secure dirfd walking is not available on this platform",
)
def test_manifest_loader_uses_dirfd_walk_instead_of_pathname_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested = tmp_path / "reviewed" / "models"
    nested.mkdir(parents=True)
    manifest_path = nested / "model-manifest.json"
    _write_manifest(manifest_path)

    def fail_fallback(path: Path) -> None:
        raise AssertionError(f"pathname fallback unexpectedly used for {path}")

    monkeypatch.setattr(
        manifest_module,
        "_assert_trusted_manifest_path",
        fail_fallback,
    )

    loaded = load_local_model_manifest(manifest_path)

    assert loaded.models[0].quantization == "Q4_K_M"
    assert loaded.models[0].weights_vram_mib == 3800


@pytest.mark.skipif(
    not manifest_module._supports_secure_dirfd(),
    reason="secure dirfd walking is not available on this platform",
)
def test_manifest_loader_opens_components_relative_to_pinned_parent_fds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested = tmp_path / "reviewed" / "models"
    nested.mkdir(parents=True)
    manifest_path = nested / "model-manifest.json"
    _write_manifest(manifest_path)

    real_open = os.open
    calls: list[tuple[object, int, int | None]] = []

    def recording_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        calls.append((path, flags, dir_fd))
        if dir_fd is None:
            return real_open(path, flags, mode)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(manifest_module.os, "open", recording_open)

    load_local_model_manifest(manifest_path)

    relative_calls = [call for call in calls if call[2] is not None]
    assert relative_calls
    assert all(flags & os.O_NOFOLLOW for _, flags, _ in relative_calls)
    assert any(
        path == "model-manifest.json" and dir_fd is not None
        for path, _, dir_fd in relative_calls
    )


@pytest.mark.skipif(
    not hasattr(os, "symlink"),
    reason="symlinks are not supported on this platform",
)
def test_manifest_loader_rejects_symlinked_ancestor(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    nested = actual / "models"
    nested.mkdir(parents=True)
    _write_manifest(nested / "model-manifest.json")

    linked = tmp_path / "linked"
    linked.symlink_to(actual, target_is_directory=True)

    with pytest.raises(ModelManifestError):
        load_local_model_manifest(linked / "models" / "model-manifest.json")


def test_manifest_loader_rejects_explicit_parent_traversal(tmp_path: Path) -> None:
    nested = tmp_path / "reviewed"
    nested.mkdir()
    manifest_path = nested / "model-manifest.json"
    _write_manifest(manifest_path)

    traversal = nested / ".." / "reviewed" / "model-manifest.json"
    assert ".." in traversal.parts

    with pytest.raises(ModelManifestError, match="parent traversal"):
        load_local_model_manifest(traversal)
