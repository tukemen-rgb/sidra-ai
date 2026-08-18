"""Filesystem-boundary regressions for optional RAG JSONL persistence."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
from sidra_ai.retrieval.search import BM25Retriever
from sidra_ai.retrieval.store import DocumentStore, PersistencePathError
from sidra_ai.security.gate import SecurityGate


def _document(content: str, *, commit_sha: str = "a" * 40) -> Document:
    return Document(
        content=content,
        provenance=Provenance(
            source="github",
            repository="tukemen-rgb/site",
            path="docs/persistence.md",
            commit_sha=commit_sha,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license="MIT",
        ),
    )


def _symlink_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks are unavailable in this test environment: {exc}")


def test_existing_persistence_file_is_tightened_to_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "index.jsonl"
    path.write_text("", encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o644)

    store = DocumentStore(SecurityGate(), path=path)
    store.add(_document("persisted marker"))

    assert "persisted marker" in path.read_text(encoding="utf-8")
    if os.name == "posix":
        assert (path.stat().st_mode & 0o777) == 0o600


def test_symlinked_persistence_target_fails_before_index_mutation(tmp_path: Path) -> None:
    path = tmp_path / "index.jsonl"
    store = DocumentStore(SecurityGate(), path=path)
    store.add(_document("old_unique_marker", commit_sha="a" * 40))

    saved_log = tmp_path / "index.saved.jsonl"
    path.replace(saved_log)
    unrelated = tmp_path / "unrelated.txt"
    unrelated.write_text("KEEP\n", encoding="utf-8")
    mode_before = unrelated.stat().st_mode
    _symlink_or_skip(path, unrelated)

    with pytest.raises(PersistencePathError):
        store.add(_document("new_unique_marker", commit_sha="b" * 40))

    assert unrelated.read_text(encoding="utf-8") == "KEEP\n"
    assert unrelated.stat().st_mode == mode_before
    assert len(store) == 1
    assert BM25Retriever(store).search("old_unique_marker", top_k=1)
    assert BM25Retriever(store).search("new_unique_marker") == []


def test_symlinked_persistence_parent_is_rejected(tmp_path: Path) -> None:
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    _symlink_or_skip(linked_parent, real_parent, directory=True)

    store = DocumentStore(SecurityGate(), path=linked_parent / "index.jsonl")

    with pytest.raises(PersistencePathError):
        store.add(_document("must_not_escape_parent"))

    assert not (real_parent / "index.jsonl").exists()
    assert len(store) == 0


def test_symlinked_persistence_grandparent_is_rejected(tmp_path: Path) -> None:
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    linked_root = tmp_path / "linked-root"
    _symlink_or_skip(linked_root, real_root, directory=True)

    nested = linked_root / "nested"
    store = DocumentStore(SecurityGate(), path=nested / "index.jsonl")

    with pytest.raises(PersistencePathError):
        store.add(_document("must_not_escape_ancestor"))

    assert not (real_root / "nested" / "index.jsonl").exists()
    assert len(store) == 0


def test_parent_traversal_component_is_rejected(tmp_path: Path) -> None:
    store = DocumentStore(
        SecurityGate(),
        path=tmp_path / "child" / ".." / "index.jsonl",
    )

    with pytest.raises(PersistencePathError):
        store.add(_document("must_not_use_parent_traversal"))

    assert not (tmp_path / "index.jsonl").exists()
    assert len(store) == 0


def test_non_regular_persistence_target_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "index.jsonl"
    path.mkdir()
    store = DocumentStore(SecurityGate(), path=path)

    with pytest.raises(PersistencePathError):
        store.add(_document("must_not_write_to_directory"))

    assert len(store) == 0


def test_posix_secure_dirfd_path_does_not_use_pathname_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not DocumentStore._supports_secure_dirfd():
        pytest.skip("secure dirfd walking is unavailable on this platform")

    def _fallback_must_not_run(path: Path) -> None:
        raise AssertionError(f"pathname fallback used unexpectedly for {path}")

    monkeypatch.setattr(
        DocumentStore,
        "_assert_no_symlink_ancestors",
        staticmethod(_fallback_must_not_run),
    )

    path = tmp_path / "nested" / "index.jsonl"
    store = DocumentStore(SecurityGate(), path=path)
    store.add(_document("dirfd_only_marker"))

    assert "dirfd_only_marker" in path.read_text(encoding="utf-8")
