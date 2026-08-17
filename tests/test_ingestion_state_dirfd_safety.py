"""Race-resistant filesystem regressions for the ingestion cursor state."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sidra_ai.ingestion.state import StateStore


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
        "tukemen-rgb/site",
        commit_sha="a" * 40,
        document_count=3,
    )

    loaded = store.load()
    assert loaded.get("tukemen-rgb/site").last_commit_sha == "a" * 40
    assert path.is_file()
    assert not path.with_name(path.name + ".lock").exists()
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
