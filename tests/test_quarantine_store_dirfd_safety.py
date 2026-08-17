"""Filesystem safety regressions for the local Security quarantine store."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from sidra_ai.security.decisions import Decision, GateResult
from sidra_ai.security.gate import QuarantineStore


def _result() -> GateResult:
    return GateResult(
        decision=Decision.QUARANTINE,
        findings=(),
        content="[REDACTED:test]",
        original_length=12,
        redacted=True,
        reasons=("synthetic regression record",),
    )


def _record(store: QuarantineStore) -> None:
    store.record(
        safe_content="[REDACTED:test]",
        original_length=12,
        provenance=None,
        result=_result(),
    )


def _symlink_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks are unavailable in this environment: {exc}")


def test_regular_quarantine_file_remains_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "quarantine.jsonl"
    store = QuarantineStore(path)

    _record(store)

    entries = store.entries()
    assert len(entries) == 1
    assert entries[0]["content"] == "[REDACTED:test]"
    assert path.is_file()
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_quarantine_append_refuses_final_symlink_without_touching_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "unrelated.txt"
    target.write_text("sentinel\n", encoding="utf-8")
    if os.name != "nt":
        target.chmod(0o644)
    original_mode = stat.S_IMODE(target.stat().st_mode)

    link = tmp_path / "quarantine.jsonl"
    _symlink_or_skip(link, target)
    store = QuarantineStore(link)

    with pytest.raises(OSError):
        _record(store)

    assert target.read_text(encoding="utf-8") == "sentinel\n"
    assert stat.S_IMODE(target.stat().st_mode) == original_mode


def test_quarantine_read_refuses_final_symlink(tmp_path: Path) -> None:
    target = tmp_path / "unrelated.jsonl"
    target.write_text('{"private":"sentinel"}\n', encoding="utf-8")
    link = tmp_path / "quarantine.jsonl"
    _symlink_or_skip(link, target)

    with pytest.raises(OSError):
        QuarantineStore(link).entries()


def test_quarantine_append_refuses_symlinked_ancestor(tmp_path: Path) -> None:
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    linked_root = tmp_path / "linked-root"
    _symlink_or_skip(linked_root, real_root, directory=True)

    store = QuarantineStore(linked_root / "nested" / "quarantine.jsonl")
    with pytest.raises(OSError):
        _record(store)

    assert not (real_root / "nested" / "quarantine.jsonl").exists()


def test_quarantine_read_refuses_symlinked_ancestor(tmp_path: Path) -> None:
    real_root = tmp_path / "real-root"
    nested = real_root / "nested"
    nested.mkdir(parents=True)
    (nested / "quarantine.jsonl").write_text("{}\n", encoding="utf-8")
    linked_root = tmp_path / "linked-root"
    _symlink_or_skip(linked_root, real_root, directory=True)

    with pytest.raises(OSError):
        QuarantineStore(linked_root / "nested" / "quarantine.jsonl").entries()


def test_quarantine_path_refuses_explicit_parent_traversal(tmp_path: Path) -> None:
    path = tmp_path / "safe" / ".." / "escape" / "quarantine.jsonl"

    with pytest.raises(OSError, match="parent traversal"):
        _record(QuarantineStore(path))

    assert not (tmp_path / "escape" / "quarantine.jsonl").exists()


def test_quarantine_refuses_non_regular_target(tmp_path: Path) -> None:
    path = tmp_path / "quarantine.jsonl"
    path.mkdir()

    with pytest.raises(OSError):
        _record(QuarantineStore(path))


@pytest.mark.skipif(
    not QuarantineStore._supports_secure_dirfd(),
    reason="secure dir_fd walking is unavailable on this platform",
)
def test_posix_quarantine_uses_descriptor_relative_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fallback_must_not_run(path: Path) -> int:
        raise AssertionError(f"pathname fallback unexpectedly used for {path}")

    monkeypatch.setattr(
        QuarantineStore,
        "_open_regular_append_fallback",
        classmethod(lambda cls, path: _fallback_must_not_run(path)),
    )
    monkeypatch.setattr(
        QuarantineStore,
        "_open_regular_read_fallback",
        classmethod(lambda cls, path: _fallback_must_not_run(path)),
    )

    path = tmp_path / "nested" / "quarantine.jsonl"
    store = QuarantineStore(path)
    _record(store)

    assert len(store.entries()) == 1
