"""Filesystem-boundary regressions for the persisted ingestion cursor."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sidra_ai.ingestion.state import StateStore, StateStoreError


REPOSITORY = "tukemen-rgb/site"


def _symlink_or_skip(
    target: Path,
    link: Path,
    *,
    target_is_directory: bool = False,
) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (NotImplementedError, OSError) as exc:  # pragma: no cover - platform specific
        pytest.skip(f"symlink creation unavailable: {exc}")


def test_state_store_refuses_final_symlink_without_touching_target(tmp_path: Path) -> None:
    target = tmp_path / "unrelated.json"
    original = '{"version": 1, "repositories": {}}\n'
    target.write_text(original, encoding="utf-8")
    original_mode = target.stat().st_mode

    state_path = tmp_path / "state.json"
    _symlink_or_skip(target, state_path)
    store = StateStore(state_path)

    with pytest.raises(StateStoreError, match="target is a symlink"):
        store.load()
    with pytest.raises(StateStoreError, match="target is a symlink"):
        store.mark_ingested(
            REPOSITORY,
            commit_sha="a" * 40,
            document_count=1,
        )

    assert target.read_text(encoding="utf-8") == original
    assert target.stat().st_mode == original_mode
    assert state_path.is_symlink()
    assert not state_path.with_name(state_path.name + ".lock").exists()


def test_state_store_refuses_symlink_anywhere_in_parent_ancestry(tmp_path: Path) -> None:
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    linked_root = tmp_path / "linked-root"
    _symlink_or_skip(real_root, linked_root, target_is_directory=True)

    state_path = linked_root / "nested" / "state.json"
    store = StateStore(state_path)

    with pytest.raises(StateStoreError, match="parent ancestry contains a symlink"):
        store.mark_ingested(
            REPOSITORY,
            commit_sha="b" * 40,
            document_count=1,
        )

    assert not (real_root / "nested").exists()


def test_state_store_refuses_explicit_parent_traversal(tmp_path: Path) -> None:
    safe_root = tmp_path / "safe"
    safe_root.mkdir()
    state_path = safe_root / ".." / "outside" / "state.json"

    with pytest.raises(StateStoreError, match="explicit parent traversal"):
        StateStore(state_path).mark_ingested(
            REPOSITORY,
            commit_sha="c" * 40,
            document_count=1,
        )

    assert not (tmp_path / "outside").exists()


def test_state_store_refuses_non_regular_existing_target(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.mkdir()

    with pytest.raises(StateStoreError, match="not a regular file"):
        StateStore(state_path).load()


def test_state_store_refuses_symlinked_lock_path(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    unrelated = tmp_path / "unrelated-lock-dir"
    unrelated.mkdir()
    lock_path = state_path.with_name(state_path.name + ".lock")
    _symlink_or_skip(unrelated, lock_path, target_is_directory=True)

    with pytest.raises(StateStoreError, match="lock path is a symlink"):
        StateStore(state_path).mark_ingested(
            REPOSITORY,
            commit_sha="d" * 40,
            document_count=1,
        )

    assert unrelated.exists()
    assert list(unrelated.iterdir()) == []
    assert lock_path.is_symlink()
    assert not state_path.exists()


def test_state_store_persists_owner_only_file_when_supported(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    StateStore(state_path).mark_ingested(
        REPOSITORY,
        commit_sha="e" * 40,
        document_count=1,
    )

    if os.name == "posix":
        assert state_path.stat().st_mode & 0o777 == 0o600
