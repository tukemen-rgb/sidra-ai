"""Concurrency guarantees for the persisted GitHub ingestion cursor."""

from __future__ import annotations

import os
import threading
import time

from sidra_ai.ingestion.state import StateStore


REPO_A = "tukemen-rgb/site"
REPO_B = "tukemen-rgb/Fg"


def test_state_updates_are_serialized_across_store_instances(tmp_path, monkeypatch) -> None:
    """Two workers must not overwrite each other's repository cursor state."""

    path = tmp_path / "state.json"
    first = StateStore(path)
    second = StateStore(path)

    first_entered_save = threading.Event()
    release_first_save = threading.Event()
    second_finished = threading.Event()
    errors: list[BaseException] = []

    original_save = first._save_unlocked

    def slow_first_save(state) -> None:
        first_entered_save.set()
        if not release_first_save.wait(timeout=2):
            raise RuntimeError("test timed out waiting to release first writer")
        original_save(state)

    monkeypatch.setattr(first, "_save_unlocked", slow_first_save)

    def write_first() -> None:
        try:
            first.mark_ingested(REPO_A, commit_sha="a" * 40, document_count=1)
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    def write_second() -> None:
        try:
            second.mark_ingested(REPO_B, commit_sha="b" * 40, document_count=2)
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)
        finally:
            second_finished.set()

    first_thread = threading.Thread(target=write_first)
    second_thread = threading.Thread(target=write_second)

    first_thread.start()
    assert first_entered_save.wait(timeout=1)

    second_thread.start()
    time.sleep(0.05)
    assert not second_finished.is_set(), "second writer bypassed the state lock"

    release_first_save.set()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert errors == []

    state = StateStore(path).load()
    assert state.get(REPO_A).last_commit_sha == "a" * 40
    assert state.get(REPO_B).last_commit_sha == "b" * 40
    assert not path.with_name(path.name + ".lock").exists()


def test_stale_state_lock_is_recovered_without_losing_state(tmp_path) -> None:
    """A crashed writer's empty lock directory must not wedge ingestion forever."""

    path = tmp_path / "state.json"
    store = StateStore(path)
    store.mark_ingested(REPO_A, commit_sha="a" * 40, document_count=1)

    lock_path = path.with_name(path.name + ".lock")
    lock_path.mkdir()
    stale = time.time() - (store._LOCK_STALE_SECONDS + 1)
    os.utime(lock_path, (stale, stale))

    store.mark_ingested(REPO_B, commit_sha="b" * 40, document_count=2)

    state = store.load()
    assert state.get(REPO_A).last_commit_sha == "a" * 40
    assert state.get(REPO_B).last_commit_sha == "b" * 40
    assert not lock_path.exists()
