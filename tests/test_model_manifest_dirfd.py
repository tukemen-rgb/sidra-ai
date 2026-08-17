from __future__ import annotations

import json
from pathlib import Path

import pytest

import sidra_ai.models.manifest as manifest_module
from sidra_ai.models.manifest import load_local_model_manifest


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
def test_manifest_loader_uses_dirfd_reader_instead_of_pathname_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested = tmp_path / "reviewed" / "models"
    nested.mkdir(parents=True)
    manifest_path = nested / "model-manifest.json"
    _write_manifest(manifest_path)

    def fail_fallback(path: Path) -> bytes:
        raise AssertionError(f"pathname fallback unexpectedly used for {path}")

    monkeypatch.setattr(
        manifest_module,
        "_read_manifest_bytes_fallback",
        fail_fallback,
    )

    loaded = load_local_model_manifest(manifest_path)

    assert loaded.models[0].quantization == "Q4_K_M"
    assert loaded.models[0].weights_vram_mib == 3800
