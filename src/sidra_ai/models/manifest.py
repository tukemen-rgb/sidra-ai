"""Strict local model manifest parsing for measured/conservative routing metadata.

The manifest is intentionally local-only and data-only. It never resolves a
model name over the network, never downloads weights, and never guesses memory
from a model name or parameter count. Callers can load one reviewed JSON file,
obtain explicit :class:`LocalModelCandidate` values, then pass those values to
the existing observed-VRAM router.
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sidra_ai.models.registry import available_backends
from sidra_ai.models.routing import LocalModelCandidate

MAX_MANIFEST_BYTES = 64 * 1024
MAX_MANIFEST_MODELS = 32
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ALLOWED_MODEL_KEYS = frozenset(
    {
        "backend",
        "model",
        "weights_vram_mib",
        "kv_cache_mib_per_1k_tokens",
        "max_context_tokens",
        "quantization",
        "priority",
        "license",
        "revision",
        "artifact_sha256",
    }
)


class ModelManifestError(ValueError):
    """Raised when local model metadata cannot be trusted for routing."""


@dataclass(frozen=True)
class ManifestModel:
    """One reviewed local model record plus provenance metadata."""

    backend: str
    model: str
    weights_vram_mib: int
    kv_cache_mib_per_1k_tokens: int
    max_context_tokens: int
    quantization: str
    priority: int
    license: str
    revision: str | None = None
    artifact_sha256: str | None = None

    def to_candidate(self) -> LocalModelCandidate:
        """Return the exact routing metadata without inference or mutation."""

        return LocalModelCandidate(
            backend=self.backend,
            model=self.model,
            weights_vram_mib=self.weights_vram_mib,
            kv_cache_mib_per_1k_tokens=self.kv_cache_mib_per_1k_tokens,
            max_context_tokens=self.max_context_tokens,
            quantization=self.quantization,
            priority=self.priority,
        )


@dataclass(frozen=True)
class LocalModelManifest:
    """Versioned, bounded collection of local model records."""

    version: int
    models: tuple[ManifestModel, ...]

    def candidates(self) -> tuple[LocalModelCandidate, ...]:
        return tuple(model.to_candidate() for model in self.models)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ModelManifestError(f"duplicate manifest key {key!r}")
        result[key] = value
    return result


def _required_text(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ModelManifestError(f"model field {key!r} must be a non-empty string")
    value = value.strip()
    if any(ord(char) < 32 for char in value):
        raise ModelManifestError(f"model field {key!r} contains control characters")
    return value


def _optional_text(record: dict[str, Any], key: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ModelManifestError(f"model field {key!r} must be null or non-empty text")
    value = value.strip()
    if any(ord(char) < 32 for char in value):
        raise ModelManifestError(f"model field {key!r} contains control characters")
    return value


def _int_field(record: dict[str, Any], key: str, *, minimum: int) -> int:
    value = record.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ModelManifestError(f"model field {key!r} must be an integer >= {minimum}")
    return value


def _parse_model(raw: Any, *, index: int) -> ManifestModel:
    if not isinstance(raw, dict):
        raise ModelManifestError(f"models[{index}] must be an object")

    unknown = set(raw) - _ALLOWED_MODEL_KEYS
    if unknown:
        raise ModelManifestError(
            f"models[{index}] contains unknown fields: {', '.join(sorted(unknown))}"
        )

    backend = _required_text(raw, "backend")
    if backend not in available_backends():
        raise ModelManifestError(
            f"models[{index}] backend {backend!r} is not in the local-only registry"
        )

    model = _required_text(raw, "model")
    if "://" in model:
        raise ModelManifestError("model identifiers must not be URLs")

    quantization = _required_text(raw, "quantization")
    if quantization.lower() == "unknown":
        raise ModelManifestError("quantization must be measured or explicitly identified")

    license_name = _required_text(raw, "license")
    revision = _optional_text(raw, "revision")
    artifact_sha256 = _optional_text(raw, "artifact_sha256")
    if revision is None and artifact_sha256 is None:
        raise ModelManifestError(
            "each model requires revision or artifact_sha256 provenance"
        )
    if artifact_sha256 is not None:
        normalized_digest = artifact_sha256.lower()
        if not _SHA256_RE.fullmatch(normalized_digest):
            raise ModelManifestError(
                "artifact_sha256 must use sha256:<64 lowercase-or-uppercase hex digits>"
            )
        artifact_sha256 = normalized_digest

    return ManifestModel(
        backend=backend,
        model=model,
        weights_vram_mib=_int_field(raw, "weights_vram_mib", minimum=1),
        kv_cache_mib_per_1k_tokens=_int_field(
            raw, "kv_cache_mib_per_1k_tokens", minimum=0
        ),
        max_context_tokens=_int_field(raw, "max_context_tokens", minimum=1),
        quantization=quantization,
        priority=_int_field(raw, "priority", minimum=0),
        license=license_name,
        revision=revision,
        artifact_sha256=artifact_sha256,
    )


def _assert_trusted_manifest_path(manifest_path: Path) -> None:
    """Best-effort ancestry check for platforms without secure dirfd walking."""

    if ".." in manifest_path.parts:
        raise ModelManifestError("model manifest parent traversal is not allowed")

    current = manifest_path
    while True:
        try:
            if current.is_symlink():
                raise ModelManifestError("model manifest symlinks are not allowed")
        except OSError as exc:
            raise ModelManifestError("model manifest path cannot be trusted") from exc

        parent = current.parent
        if parent == current:
            return
        current = parent


def _supports_secure_dirfd() -> bool:
    supports_dir_fd = getattr(os, "supports_dir_fd", ())
    return (
        os.name != "nt"
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and os.open in supports_dir_fd
    )


def _path_components(path: Path) -> tuple[str, ...]:
    if ".." in path.parts:
        raise ModelManifestError("model manifest parent traversal is not allowed")
    parts = path.parts[1:] if path.is_absolute() else path.parts
    components = tuple(part for part in parts if part not in {"", "."})
    if not components:
        raise ModelManifestError("model manifest path must name a file")
    return components


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _read_open_manifest(fd: int) -> bytes:
    file_stat = os.fstat(fd)
    if not stat.S_ISREG(file_stat.st_mode):
        raise ModelManifestError("model manifest must be a regular file")
    if file_stat.st_size <= 0 or file_stat.st_size > MAX_MANIFEST_BYTES:
        raise ModelManifestError("model manifest size is outside the allowed range")

    payload = os.read(fd, MAX_MANIFEST_BYTES + 1)
    if not payload or len(payload) > MAX_MANIFEST_BYTES:
        raise ModelManifestError("model manifest size is outside the allowed range")
    return payload


def _read_manifest_bytes_dirfd(manifest_path: Path) -> bytes:
    """Read a manifest by pinning every path component to directory descriptors."""

    components = _path_components(manifest_path)
    base = manifest_path.anchor if manifest_path.is_absolute() else "."
    try:
        parent_fd = os.open(base, _directory_flags())
    except OSError as exc:
        raise ModelManifestError("model manifest path cannot be trusted") from exc

    try:
        for component in components[:-1]:
            try:
                child_fd = os.open(
                    component,
                    _directory_flags(),
                    dir_fd=parent_fd,
                )
            except OSError as exc:
                raise ModelManifestError(
                    "model manifest symlinks are not allowed or path cannot be trusted"
                ) from exc
            os.close(parent_fd)
            parent_fd = child_fd

        flags = os.O_RDONLY
        flags |= getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(components[-1], flags, dir_fd=parent_fd)
        except OSError as exc:
            raise ModelManifestError(
                "model manifest symlinks are not allowed or manifest is not readable"
            ) from exc

        try:
            return _read_open_manifest(fd)
        except OSError as exc:
            raise ModelManifestError("model manifest is not readable") from exc
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _read_manifest_bytes_fallback(manifest_path: Path) -> bytes:
    """Read a manifest with best-effort symlink checks when dirfd walking is unavailable."""

    _assert_trusted_manifest_path(manifest_path)

    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)

    try:
        fd = os.open(manifest_path, flags)
    except OSError as exc:
        raise ModelManifestError("model manifest is not readable") from exc

    try:
        _assert_trusted_manifest_path(manifest_path)
        return _read_open_manifest(fd)
    except OSError as exc:
        raise ModelManifestError("model manifest is not readable") from exc
    finally:
        os.close(fd)


def _read_manifest_bytes(manifest_path: Path) -> bytes:
    """Read one bounded manifest without following untrusted path components."""

    if _supports_secure_dirfd():
        return _read_manifest_bytes_dirfd(manifest_path)
    return _read_manifest_bytes_fallback(manifest_path)


def load_local_model_manifest(path: str | Path) -> LocalModelManifest:
    """Load one reviewed JSON manifest from local disk, failing closed.

    On POSIX systems with secure ``dir_fd`` support, each path component is
    opened relative to an already-open parent directory with ``O_NOFOLLOW``.
    This prevents a reviewed manifest's ancestor directory from being swapped
    to a symlink between a pathname check and the final file open. Other
    platforms retain the existing fail-closed best-effort ancestry checks.

    The final file must be regular and bounded, decoded as strict UTF-8, parsed
    with duplicate-key detection, and may only name backends already present in
    SIDRA's local-only registry.
    """

    manifest_path = Path(path)
    payload = _read_manifest_bytes(manifest_path)
    try:
        text = payload.decode("utf-8", errors="strict")
        raw = json.loads(text, object_pairs_hook=_strict_object)
    except UnicodeDecodeError as exc:
        raise ModelManifestError("model manifest must be UTF-8 JSON") from exc
    except json.JSONDecodeError as exc:
        raise ModelManifestError("model manifest is invalid JSON") from exc

    if not isinstance(raw, dict):
        raise ModelManifestError("model manifest root must be an object")
    if set(raw) != {"version", "models"}:
        raise ModelManifestError("model manifest root must contain only version and models")
    if raw["version"] != 1 or isinstance(raw["version"], bool):
        raise ModelManifestError("unsupported model manifest version")

    models_raw = raw["models"]
    if not isinstance(models_raw, list) or not models_raw:
        raise ModelManifestError("model manifest models must be a non-empty list")
    if len(models_raw) > MAX_MANIFEST_MODELS:
        raise ModelManifestError("model manifest contains too many model records")

    models = tuple(_parse_model(item, index=index) for index, item in enumerate(models_raw))
    route_ids = [f"{item.backend}:{item.model}" for item in models]
    if len(route_ids) != len(set(route_ids)):
        raise ModelManifestError("model manifest contains duplicate backend/model routes")

    return LocalModelManifest(version=1, models=models)
