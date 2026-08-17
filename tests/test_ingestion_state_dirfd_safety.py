"""Race-resistant filesystem regressions for the ingestion cursor state."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path

import pytest

import sidra_ai.ingestion.state as state_module
from sidra_ai.ingestion.state import StateStore


REPOSITORY = "tukemen-rgb/site"


@pytest.mark.skipif(
    not StateStore._supports_secure_dirfd(),
    reason="secure dir_fd/O_NOFOLLOW walk unavailable",
)
def test_state_store_uses_descriptor_relative_path_when_supported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POSIX must not fall back to pathname check-then-open state operations."""

    def forbidden_read_fallback(self):  # noqa: ANN001
        raise AssertionError("pathname read fallback must not be used")

    def forbidden_lock_fallback(self):  # noqa: ANN001
        raise AssertionError("pathname lock fallback must not be used")

    def forbidden_save_fallback(self, state):  # noqa: ANN001, ARG001
        raise AssertionError("pathname save fallback must not be used")

    monkeypatch.setattr(
        StateStore,
        "_open_state_for_read_fallback",
        forbidden_read_fallback,
    )
    monkeypatch.setattr(
        StateStore,
        "_locked_update_fallback",
        forbidden_lock_fallback,
    )
    monkeypatch.setattr(
        StateStore,
        "_save_unlocked_fallback",
        forbidden_save_fallback,
    )

    path = tmp_path / "nested" / "state.json"
    store = StateStore(path)
    store.mark_ingested(
        REPOSITORY,
        commit_sha="a" * 40,
        document_count=3,
    )

    loaded = store.load()
    assert loaded.get(REPOSITORY).last_commit_sha == "a" * 40
    assert path.is_file()
    assert not path.with_name(path.name + ".lock").exists()
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(
    not StateStore._supports_secure_dirfd(),
    reason="secure dir_fd/O_NOFOLLOW walk unavailable",
)
def test_read_modify_write_stays_on_one_parent_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replacing the pathname after lock acquisition must not redirect cursors."""

    live = tmp_path / "live"
    live.mkdir()
    state_path = live / "state.json"
    StateStore(state_path).mark_ingested(
        REPOSITORY,
        commit_sha="a" * 40,
        document_count=1,
    )

    moved = tmp_path / "moved"
    original_state_lock = state_module.state_lock

    @contextmanager
    def swapping_state_lock(path: Path, **kwargs):  # noqa: ANN003
        with original_state_lock(path, **kwargs) as trusted:
            live.rename(moved)
            live.mkdir()
            decoy = {
                "version": 1,
                "repositories": {
                    REPOSITORY: {
                        "repository": REPOSITORY,
                        "last_commit_sha": "d" * 40,
                    }
                },
            }
            state_path.write_text(json.dumps(decoy), encoding="utf-8")
            yield trusted

    monkeypatch.setattr(state_module, "state_lock", swapping_state_lock)

    StateStore(state_path).mark_error(REPOSITORY, "synthetic failure")

    original = StateStore(moved / "state.json").load().get(REPOSITORY)
    decoy = StateStore(state_path).load().get(REPOSITORY)
    assert original.last_commit_sha == "a" * 40
    assert original.last_error == "synthetic failure"
    assert decoy.last_commit_sha == "d" * 40
    assert decoy.last_error == ""
